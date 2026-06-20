"""
Build a literature corpus for eval by auto-downloading the draft's own cited papers.

Pipeline (mirrors what happens in the real UI):
  1. Ingest the draft PDF via GROBID → extract reference list (same path as ingest_draft)
  2. Resolve each ref against OpenAlex → find open-access PDF URL
  3. Download OA PDFs → scripts/eval/corpora/<draft_stem>/

Then run the harness with --corpus <draft_stem>:
  python scripts/eval/run_harness.py --draft pdfs/draft1.pdf --corpus draft1

Usage (inside backend container):
  python scripts/eval/build_corpus.py --draft pdfs/draft1.pdf
  python scripts/eval/build_corpus.py --all               # all PDFs in scripts/eval/pdfs/
  python scripts/eval/build_corpus.py --draft pdfs/draft1.pdf --max-papers 15
  python scripts/eval/build_corpus.py --draft pdfs/draft1.pdf --force  # re-download existing

Corpus dir is created automatically. Script is idempotent (skips already-downloaded files).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import re
import sys
import time
import uuid
from pathlib import Path

if Path("/app/app").exists():
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _svc = str(REPO_ROOT / "services" / "backend")
    if _svc not in sys.path:
        sys.path.insert(0, _svc)

import aiohttp

EVAL_DIR = Path(__file__).resolve().parent
CORPORA_DIR = EVAL_DIR / "corpora"
PDFS_DIR = EVAL_DIR / "pdfs"

_OA_BASE = "https://api.openalex.org"
_OA_EMAIL = "contact@noesis.is"
# Fetch oa_url in addition to the standard fields used by draft_reference_extraction
_OA_FIELDS = (
    "id,display_name,title,authorships,publication_year,doi,"
    "abstract_inverted_index,open_access,primary_location"
)

MAX_PAPERS_DEFAULT = 20
DOWNLOAD_TIMEOUT = 30  # seconds per PDF
RATE_DELAY = 0.12       # ~8 req/s — within OpenAlex polite-pool limit


# ─────────────────────────────────────────────────────────────────────────────
# OpenAlex helpers (extended from draft_reference_extraction — adds oa_url)
# ─────────────────────────────────────────────────────────────────────────────

def _polite(extra: dict | None = None) -> dict:
    params = {"mailto": _OA_EMAIL, "select": _OA_FIELDS}
    if extra:
        params.update(extra)
    return params


def _title_match(a: str, b: str) -> bool:
    def words(s: str) -> set[str]:
        return {w.lower() for w in re.findall(r"\w+", s) if len(w) > 3}
    wa, wb = words(a), words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) / min(len(wa), len(wb)) >= 0.6


def _extract_oa_url(work: dict) -> str | None:
    oa = work.get("open_access") or {}
    url = oa.get("oa_url") or ""
    if url and url.lower().endswith(".pdf"):
        return url
    # Fallback: primary_location pdf_url
    pl = work.get("primary_location") or {}
    return pl.get("pdf_url") or (url if url else None)


async def _by_doi(session: aiohttp.ClientSession, doi: str) -> dict | None:
    doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
    try:
        async with session.get(
            f"{_OA_BASE}/works/https://doi.org/{doi_clean}",
            params=_polite(),
            timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        pass
    return None


async def _by_title(session: aiohttp.ClientSession, title: str) -> dict | None:
    try:
        async with session.get(
            f"{_OA_BASE}/works",
            params=_polite({"search": title[:200], "per-page": 5}),
            timeout=aiohttp.ClientTimeout(total=12),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                for work in data.get("results") or []:
                    candidate = work.get("display_name") or work.get("title") or ""
                    if _title_match(title, candidate):
                        return work
    except Exception:
        pass
    return None


async def _resolve_ref(session: aiohttp.ClientSession, ref: dict) -> tuple[dict, str | None]:
    """Return (ref, oa_pdf_url | None). Tries DOI first, then title search."""
    await asyncio.sleep(RATE_DELAY)
    doi = ref.get("doi") or ""
    title = ref.get("title") or ""
    work = None
    if doi:
        work = await _by_doi(session, doi)
    if not work and title:
        work = await _by_title(session, title)
    if not work:
        return ref, None
    return ref, _extract_oa_url(work)


async def _download_pdf(session: aiohttp.ClientSession, url: str, dest: Path) -> bool:
    """Download a PDF to dest. Returns True on success."""
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                return False
            ct = resp.headers.get("content-type", "")
            if "pdf" not in ct and not url.lower().endswith(".pdf"):
                # Not actually a PDF — skip
                return False
            data = await resp.read()
            if len(data) < 5000:
                return False  # suspiciously small
            dest.write_bytes(data)
            return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Reference extraction from draft (via ingest_draft → parse_artifact)
# ─────────────────────────────────────────────────────────────────────────────

def _safe_stem(text: str, max_len: int = 60) -> str:
    """Convert text to a filesystem-safe stem."""
    stem = re.sub(r"[^\w\s-]", "", (text or "").lower())
    stem = re.sub(r"[\s_-]+", "_", stem).strip("_")
    return stem[:max_len] or "ref"


async def _extract_refs_from_draft(draft_path: Path) -> list[dict]:
    """Ingest draft through GROBID via the existing ingest_draft service, return raw refs."""
    from app.core.supabase_client import supabase
    from app.services.draft_processing import ingest_draft
    from app.services.draft_reference_extraction import extract_refs_from_parse_artifact

    # Create a throwaway project + user
    try:
        r = supabase.table("projects").select("user_id").limit(1).execute()
        user_id = r.data[0]["user_id"] if r.data else ""
    except Exception:
        user_id = ""

    if not user_id:
        print("[build-corpus] ERROR: no user found in DB. Set EVAL_USER_ID or run harness first.")
        return []

    draft_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())

    # Minimal project row
    supabase.table("projects").insert({
        "id": project_id, "user_id": user_id,
        "title": f"[EVAL-CORPUS-BUILD] {draft_path.stem}",
        "description": "Throwaway — safe to delete",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }).execute()

    # Upload draft bytes to storage
    file_bytes = draft_path.read_bytes()
    file_ext = draft_path.suffix.lstrip(".")
    storage_path = f"{user_id}/{draft_id}.{file_ext}"
    supabase.storage.from_("drafts").upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": "application/pdf"},
    )
    file_url = supabase.storage.from_("drafts").get_public_url(storage_path)

    supabase.table("drafts").insert({
        "id": draft_id, "user_id": user_id, "project_id": project_id,
        "title": draft_path.stem, "version": 1,
        "file_url": file_url, "file_type": file_ext,
        "file_size": len(file_bytes), "paper_type": "journal_article",
        "citation_style": "auto", "status": "processing",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }).execute()

    refs: list[dict] = []
    try:
        print(f"[build-corpus] Ingesting {draft_path.name} via GROBID …")
        ingest_result = await ingest_draft(draft_id, project_id)
        # extracted_refs is the raw GROBID reference list returned directly from
        # ingest_draft — more reliable than going through parse_artifact.parser_metadata
        refs = ingest_result.get("extracted_refs") or []
        if not refs:
            # fallback: try parse_artifact path (older container builds)
            parse_artifact = ingest_result.get("parse_artifact") or {}
            refs = extract_refs_from_parse_artifact(parse_artifact)
        print(f"[build-corpus] GROBID extracted {len(refs)} references")
    finally:
        # Clean up all throwaway rows
        for tbl in ("draft_parse_artifacts", "draft_chunks", "draft_analysis", "drafts"):
            try:
                supabase.table(tbl).delete().eq("draft_id", draft_id).execute()
            except Exception:
                pass
        try:
            supabase.table("projects").delete().eq("id", project_id).execute()
        except Exception:
            pass
        try:
            supabase.storage.from_("drafts").remove([storage_path])
        except Exception:
            pass

    return refs


# ─────────────────────────────────────────────────────────────────────────────
# Main build function
# ─────────────────────────────────────────────────────────────────────────────

async def build_corpus_for_draft(
    draft_path: Path,
    max_papers: int = MAX_PAPERS_DEFAULT,
    force: bool = False,
) -> int:
    """Build corpus for a single draft. Returns count of PDFs downloaded."""
    corpus_dir = CORPORA_DIR / draft_path.stem
    corpus_dir.mkdir(parents=True, exist_ok=True)

    if not force and list(corpus_dir.glob("*.pdf")):
        existing = len(list(corpus_dir.glob("*.pdf")))
        print(f"[build-corpus] {draft_path.stem}: corpus already has {existing} PDFs (use --force to re-download)")
        return existing

    # Step 1: Extract refs via GROBID
    refs = await _extract_refs_from_draft(draft_path)
    if not refs:
        print(f"[build-corpus] {draft_path.stem}: no references extracted — corpus will be empty")
        return 0

    # Step 2: Resolve refs → OA PDF URLs
    print(f"[build-corpus] Resolving {min(len(refs), max_papers)} refs against OpenAlex …")
    resolved: list[tuple[dict, str]] = []  # (ref, oa_url)

    async with aiohttp.ClientSession(headers={"User-Agent": f"Noesis-eval/1.0 (mailto:{_OA_EMAIL})"}) as session:
        tasks = [_resolve_ref(session, ref) for ref in refs[:max_papers]]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                continue
            ref, oa_url = r
            if oa_url:
                resolved.append((ref, oa_url))

    print(f"[build-corpus] {len(resolved)}/{min(len(refs), max_papers)} refs have OA PDFs")

    # Step 3: Download PDFs
    downloaded = 0
    async with aiohttp.ClientSession(headers={"User-Agent": f"Noesis-eval/1.0 (mailto:{_OA_EMAIL})"}) as session:
        for ref, oa_url in resolved:
            title = ref.get("title") or "unknown"
            year = ref.get("year") or ""
            authors = ref.get("authors") or []
            first_author = _safe_stem(authors[0].split()[-1] if authors else "")
            filename = _safe_stem(f"{first_author}_{year}_{title}", max_len=80) + ".pdf"
            dest = corpus_dir / filename

            if dest.exists() and not force:
                print(f"[build-corpus]   skip (exists): {filename}")
                downloaded += 1
                continue

            print(f"[build-corpus]   downloading: {filename}")
            ok = await _download_pdf(session, oa_url, dest)
            if ok:
                print(f"[build-corpus]   ✓ {filename} ({dest.stat().st_size // 1024}KB)")
                downloaded += 1
            else:
                print(f"[build-corpus]   ✗ failed: {oa_url[:80]}")

    print(f"[build-corpus] {draft_path.stem}: {downloaded} PDFs in {corpus_dir}")
    return downloaded


def _update_config_yaml(draft_stems: list[str]) -> None:
    """Add corpus entries to config.yaml for each draft stem that has a corpus dir."""
    config_path = EVAL_DIR / "config.yaml"
    if not config_path.exists():
        return
    text = config_path.read_text()

    for stem in draft_stems:
        corpus_dir = CORPORA_DIR / stem
        if not corpus_dir.exists() or not list(corpus_dir.glob("*.pdf")):
            continue
        if f"  - {stem}" in text:
            continue  # already present
        # Insert after the `corpora:` line
        text = text.replace(
            "\ncorpora:",
            f"\ncorpora:",
        )
        # Append under corpora block
        lines = text.splitlines()
        new_lines = []
        in_corpora = False
        inserted = False
        for line in lines:
            new_lines.append(line)
            if line.strip() == "corpora:":
                in_corpora = True
            elif in_corpora and not inserted and (not line.startswith("  ") or line.strip().startswith("#")):
                new_lines.insert(-1, f"  - {stem}")
                inserted = True
                in_corpora = False
        if not inserted and in_corpora:
            new_lines.append(f"  - {stem}")
        text = "\n".join(new_lines) + "\n"

    config_path.write_text(text)
    print(f"[build-corpus] config.yaml updated with corpus entries")


async def main(args: argparse.Namespace) -> int:
    if args.all:
        draft_paths = sorted(PDFS_DIR.glob("*.pdf"))
        if not draft_paths:
            print(f"[build-corpus] No PDFs found in {PDFS_DIR}")
            return 1
        print(f"[build-corpus] Building corpora for {len(draft_paths)} drafts …")
    else:
        draft_paths = [(REPO_ROOT / args.draft).resolve()]

    stems_built: list[str] = []
    for draft_path in draft_paths:
        if not draft_path.exists():
            print(f"[build-corpus] ERROR: not found: {draft_path}")
            continue
        count = await build_corpus_for_draft(draft_path, max_papers=args.max_papers, force=args.force)
        if count > 0:
            stems_built.append(draft_path.stem)

    if stems_built and not args.no_config_update:
        # config.yaml uses auto_corpus: true — no need to add to corpora list.
        # _update_config_yaml(stems_built) intentionally skipped.

    print(f"\n[build-corpus] Done. Corpora built for: {stems_built or 'none'}")
    print(f"[build-corpus] Run eval with: python scripts/eval/run_eval.py")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build eval corpus by downloading cited papers from OpenAlex")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--draft", help="Path to draft PDF (relative to repo root), e.g. pdfs/draft1.pdf")
    g.add_argument("--all", action="store_true", help="Build corpora for all PDFs in scripts/eval/pdfs/")
    p.add_argument("--max-papers", type=int, default=MAX_PAPERS_DEFAULT, help=f"Max OA PDFs to download per draft (default: {MAX_PAPERS_DEFAULT})")
    p.add_argument("--force", action="store_true", help="Re-download even if corpus already exists")
    p.add_argument("--no-config-update", action="store_true", help="Don't update config.yaml with new corpus entries")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
