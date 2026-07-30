"""
Build a literature corpus for eval by auto-downloading the draft's own cited papers.

Pipeline (mirrors what happens in the real UI):
  1. Ingest the draft PDF via GROBID → extract reference list (same path as ingest_draft)
  2. Resolve each ref against OpenAlex → find open-access PDF URL
  3. Download OA PDFs → scripts/eval/corpora/<draft_stem>/

Then run the harness with --corpus <draft_stem>:
  python scripts/eval/run_harness.py --draft pdfs/draft1.pdf --corpus draft1

OpenReview mode (no GROBID / no DB): references are parsed straight out of the
manuscript PDF, so a corpus can be built on the host with nothing running.

  python scripts/eval/build_corpus.py --openreview rhgIgTSSxW
  python scripts/eval/build_corpus.py --openreview-all

Usage (inside backend container):
  python scripts/eval/build_corpus.py --draft pdfs/draft1.pdf
  python scripts/eval/build_corpus.py --all               # all PDFs in scripts/eval/pdfs/
  python scripts/eval/build_corpus.py --draft pdfs/draft1.pdf --max-papers 15
  python scripts/eval/build_corpus.py --draft pdfs/draft1.pdf --force  # re-download existing

Every corpus dir gets a ``references.json`` sidecar recording *every* reference
that was attempted, with its resolution outcome. Without it the resolution
denominator is unrecoverable and scripts/eval/retrieval/labels.py refuses to
report a rate (resolved/resolved is 100% by construction).

Corpus dir is created automatically. Script is idempotent (skips already-downloaded
files and refs that already have a recorded outcome in the sidecar).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import os
import re
import ssl
import sys
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
OPENREVIEW_DIR = EVAL_DIR / "openreview"

#: Sidecar consumed by scripts/eval/retrieval/labels.py. One entry per attempted
#: reference, resolved or not — this is the recall denominator.
REFERENCES_SIDECAR = "references.json"
#: Bumped when the PDF reference parser changes, so stale sidecars rebuild.
EXTRACTOR_VERSION = "pdf-refs-1"

# Resolution outcomes. These are the states the pipeline actually distinguishes.
STATUS_RESOLVED = "resolved"              # OA PDF downloaded into the corpus
STATUS_NO_OPENALEX = "no_openalex_match"  # OpenAlex knows nothing by DOI or title
STATUS_NO_OA_PDF = "no_oa_pdf"            # found in OpenAlex, no open-access PDF url
STATUS_DOWNLOAD_FAILED = "download_failed"  # had a url; fetch 404'd / wasn't a PDF
STATUS_SKIPPED = "skipped_max_papers"     # truncated by --max-papers, never attempted
STATUS_PENDING = "pending"                # budget ran out before this ref was tried

_OA_BASE = "https://api.openalex.org"
_OA_EMAIL = os.environ.get("OPENALEX_EMAIL") or os.environ.get("UNPAYWALL_EMAIL") or "contact@noesis.is"
# Fetch oa_url in addition to the standard fields used by draft_reference_extraction
_OA_FIELDS = (
    "id,display_name,title,authorships,publication_year,doi,"
    "abstract_inverted_index,open_access,primary_location"
)

MAX_PAPERS_DEFAULT = 20
DOWNLOAD_TIMEOUT = 30  # seconds per PDF
RATE_DELAY = 0.12       # ~8 req/s — within OpenAlex polite-pool limit
OA_CONCURRENCY = 4
OA_MAX_RETRIES = 4
#: Longest 429 backoff worth waiting out in-process. OpenAlex is metered as of
#: 2026 ($0.10/day free, ~100 searches); when the daily budget is gone it returns
#: Retry-After ~= seconds until midnight UTC, which is not a wait, it is a stop.
OA_MAX_BACKOFF = 120.0


class OpenAlexBudgetExhausted(RuntimeError):
    """OpenAlex refused the request until its daily budget resets.

    Raised rather than swallowed: returning "no match" here would write a false
    ``no_openalex_match`` into the sidecar, permanently mislabelling a reference
    that was never actually looked up.
    """
USER_AGENT = f"Noesis-eval-corpus-builder/1.0 (+https://noesis.is; mailto:{_OA_EMAIL})"


class _Throttle:
    """Serialises request *starts* to one every ``delay`` seconds.

    The previous code slept ``RATE_DELAY`` inside each coroutine before an
    ``asyncio.gather`` of all of them, so every request slept concurrently and
    then fired at once. This actually spaces them.
    """

    def __init__(self, delay: float = RATE_DELAY) -> None:
        self._delay = delay
        self._lock = asyncio.Lock()
        self._next = 0.0

    async def wait(self) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            if now < self._next:
                await asyncio.sleep(self._next - now)
                now = loop.time()
            self._next = now + self._delay


_throttle = _Throttle()


def _client_session() -> aiohttp.ClientSession:
    """Session with a descriptive UA and an explicit CA bundle.

    macOS framework Pythons ship without a populated system trust store, so
    every https call fails handshake and — because the resolver swallows
    exceptions — silently looks like "OpenAlex has never heard of this paper".
    """
    connector = None
    try:
        import certifi

        connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=certifi.where()))
    except ImportError:  # pragma: no cover - certifi is present in practice
        pass
    return aiohttp.ClientSession(headers={"User-Agent": USER_AGENT}, connector=connector)


async def _oa_get(session: aiohttp.ClientSession, url: str, params: dict) -> dict | None:
    """GET against OpenAlex with throttling and backoff on 429/5xx."""
    delay = 1.0
    for attempt in range(OA_MAX_RETRIES):
        await _throttle.wait()
        try:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 404:
                    return None
                if resp.status == 429 or resp.status >= 500:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if (retry_after or "").isdigit() else delay
                    if wait > OA_MAX_BACKOFF:
                        raise OpenAlexBudgetExhausted(
                            f"OpenAlex returned {resp.status} with Retry-After={wait:.0f}s "
                            f"(remaining budget ${resp.headers.get('X-RateLimit-Remaining-USD', '?')}). "
                            "Daily budget is spent; re-run after it resets (midnight UTC) — "
                            "the build resumes where it stopped."
                        )
                    print(f"[build-corpus]   OpenAlex {resp.status} — backing off {wait:.0f}s")
                    await asyncio.sleep(wait)
                    delay = min(delay * 2, OA_MAX_BACKOFF)
                    continue
                return None
        except asyncio.TimeoutError:
            await asyncio.sleep(delay)
            delay = min(delay * 2, OA_MAX_BACKOFF)
        except OpenAlexBudgetExhausted:
            raise
        except Exception:
            return None
    return None


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
    data = await _oa_get(session, f"{_OA_BASE}/works/https://doi.org/{doi_clean}", _polite())
    return data if isinstance(data, dict) and data.get("id") else None


async def _by_title(session: aiohttp.ClientSession, title: str) -> dict | None:
    data = await _oa_get(
        session, f"{_OA_BASE}/works", _polite({"search": title[:200], "per-page": 5})
    )
    if not isinstance(data, dict):
        return None
    for work in data.get("results") or []:
        if not isinstance(work, dict):
            continue
        candidate = work.get("display_name") or work.get("title") or ""
        if _title_match(title, candidate):
            return work
    return None


async def _resolve_ref(session: aiohttp.ClientSession, ref: dict) -> tuple[dict, dict | None]:
    """Return (ref, openalex_work | None). Tries DOI first, then title search."""
    doi = ref.get("doi") or ""
    title = ref.get("title") or ""
    work = None
    if doi:
        work = await _by_doi(session, doi)
    if not work and title:
        work = await _by_title(session, title)
    return ref, work


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


# ─────────────────────────────────────────────────────────────────────────────
# Reference extraction straight from the PDF (no GROBID, no DB)
#
# Used by --openreview: the OpenReview manuscripts are on disk, but GROBID and
# Supabase are not necessarily running, and OpenAlex has no reference list for
# them (they are unindexed conference submissions — referenced_works_count is 0
# for the handful that are indexed at all). So the bibliography is parsed out of
# the PDF text directly.
# ─────────────────────────────────────────────────────────────────────────────

_REF_HEADING = re.compile(
    r"(?mi)^[ \t]*(R\s?E\s?F\s?E\s?R\s?E\s?N\s?C\s?E\s?S|References|Bibliography)[ \t]*$"
)
_REF_STOP = re.compile(r"(?mi)^[ \t]*(A\s?P\s?P\s?E\s?N\s?D\s?I\s?X|Appendix\b|Supplementary Material)")
_YEAR = re.compile(r"(?:19|20)\d{2}")
_NUMBERED = re.compile(r"^\[\d{1,3}\]\s*")
_ENTRY_START = re.compile(
    r"^(?:\[\d{1,3}\]\s*)?("
    r"(?:[A-Z]\.\s*){1,4}(?:-[A-Z]\.\s*)?[A-Z][\w'’\-]+"      # T. Akiba
    r"|[A-Z][\w'’\-]+,\s*(?:[A-Z]\.|[A-Z][a-z]+)"             # Akiba, Takuya
    r"|[A-Z][\w'’\-]+\s+[A-Z][\w'’\-]+,"                      # Takuya Akiba,
    r"|[A-Z][\w'’\-]+\s+[A-Z]\.\s*[A-Z][\w'’\-]+"             # Jimmy L. Ba
    r")"
)
_DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s,;)\]\"’”]+)")
_ARXIV_RE = re.compile(r"arXiv[:\s]*(?:preprint\s+arXiv[:\s]*)?(\d{4}\.\d{4,5})", re.I)
_QUOTED_RE = re.compile(r"[“”\"](.{15,300}?)[.,]?[“”\"]")
#: A token that can appear inside an author list but not inside a title.
_AUTHOR_TOKEN = re.compile(
    r"^(?:[A-Z]\.?(?:-[A-Z]\.?)*[,.]?"          # initials: J.  J.-P.  J,
    r"|[A-ZÀ-Ý][\wÀ-ÿ'’\-]*[,.]?"                # capitalised surname
    r"|and|&|de|del|della|da|di|do|van|von|der|den|ten|ter|la|le|el|bin|ibn|dos"
    r"|Jr\.?|Sr\.?|et|al\.?)[,.]?$"
)


def _bibliography_text(pdf_path: Path) -> str:
    """Return the raw text of the manuscript's reference section, or ""."""
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PyMuPDF is required to parse references out of a PDF "
            "(pip install pymupdf), or use --draft with GROBID available."
        ) from exc

    with fitz.open(pdf_path) as doc:
        text = "\n".join(page.get_text() for page in doc)

    headings = list(_REF_HEADING.finditer(text))
    if not headings:
        return ""
    # The last heading with substantial text after it: papers often mention
    # "References" in a running header before the actual bibliography.
    chosen = headings[0]
    for cand in reversed(headings):
        if len(text) - cand.end() > 1500:
            chosen = cand
            break
    tail = text[chosen.end():]
    stop = _REF_STOP.search(tail)
    if stop and stop.start() > 500:
        tail = tail[: stop.start()]
    return tail


def _split_entries(bibliography: str) -> list[str]:
    """Group bibliography lines into one string per reference."""
    lines = [l.strip() for l in bibliography.splitlines() if l.strip()]
    numbered = sum(1 for l in lines if _NUMBERED.match(l))
    out: list[str] = []
    cur: list[str] = []
    for line in lines:
        if numbered >= 5:
            starts = bool(_NUMBERED.match(line))
        else:
            # A reference nearly always ends with a year, so an author-looking
            # line only starts a new entry once the current one has one. This is
            # what stops long author lists being split into several references.
            starts = bool(_ENTRY_START.match(line)) and bool(_YEAR.search(" ".join(cur)))
        if starts and cur:
            out.append(" ".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        out.append(" ".join(cur))

    entries = []
    for raw in out:
        raw = _NUMBERED.sub("", re.sub(r"\s+", " ", raw).strip())
        raw = re.sub(r"(?<=[a-z])-\s+(?=[a-z])", "", raw)  # de-hyphenate line breaks
        if len(raw) > 25 and _YEAR.search(raw):
            entries.append(raw)
    return entries


def _guess_title(entry: str) -> str:
    """Pull the title out of a raw citation string.

    Heuristic, and only ever used as an OpenAlex *query* — a wrong guess costs a
    lookup, never a wrong label, because matches are verified by title overlap.
    """
    quoted = _QUOTED_RE.search(entry)
    if quoted:
        return quoted.group(1).strip()

    # Author lists are entirely initials, capitalised surnames and particles.
    # Take the *last* sentence break whose prefix still looks like one: the
    # title starts immediately after it.
    cut = None
    for m in re.finditer(r"\.\s+", entry[:1200]):
        prefix = entry[: m.start()]
        tokens = prefix.split()
        if len(tokens) >= 2 and all(_AUTHOR_TOKEN.match(t) for t in tokens):
            cut = m.end()
    if cut is None:
        return entry[:150].strip(" .,")

    rest = entry[cut:]
    end = re.search(r"\.\s+(?=[A-Z(]|arXiv|In\b)", rest)
    title = (rest[: end.start()] if end else rest).strip(" .,")
    return title[:300]


def _extract_refs_from_pdf(pdf_path: Path) -> list[dict]:
    """Parse a manuscript's bibliography into ``{title, doi, raw}`` dicts."""
    entries = _split_entries(_bibliography_text(pdf_path))
    refs: list[dict] = []
    seen: set[str] = set()
    for raw in entries:
        doi_match = _DOI_RE.search(raw)
        doi = doi_match.group(1).rstrip(".") if doi_match else None
        if not doi:
            arxiv = _ARXIV_RE.search(raw)
            if arxiv:
                doi = f"10.48550/arXiv.{arxiv.group(1)}"
        title = _guess_title(raw)
        key = (title or raw)[:120].lower()
        if key in seen:
            continue
        seen.add(key)
        year = _YEAR.findall(raw)
        refs.append({
            "title": title,
            "doi": doi,
            "raw": raw,
            "year": year[-1] if year else "",
            "authors": [],
        })
    return refs


# ─────────────────────────────────────────────────────────────────────────────
# references.json sidecar — the resolution denominator
# ─────────────────────────────────────────────────────────────────────────────

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sidecar(corpus_dir: Path) -> dict | None:
    path = corpus_dir / REFERENCES_SIDECAR
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def write_sidecar(corpus_dir: Path, source: Path, references: list[dict]) -> Path:
    """Persist every attempted reference and its outcome.

    Schema is the one scripts/eval/retrieval/labels.py reads: a dict with a
    ``references`` list whose entries carry ``title`` and ``doi``.
    """
    payload = {
        "corpus": corpus_dir.name,
        "source_pdf": source.name,
        "source_sha256": _sha256_file(source) if source.exists() else "",
        "extractor_version": EXTRACTOR_VERSION,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "references_attempted": len(references),
        "references_resolved": sum(1 for r in references if r["status"] == STATUS_RESOLVED),
        "references": references,
    }
    corpus_dir.mkdir(parents=True, exist_ok=True)
    path = corpus_dir / REFERENCES_SIDECAR
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def _sidecar_entry(ref: dict, status: str, work: dict | None = None,
                   filename: str | None = None, oa_url: str | None = None) -> dict:
    doi = (work or {}).get("doi") or ref.get("doi")
    if isinstance(doi, str):
        doi = doi.replace("https://doi.org/", "") or None
    title = ((work or {}).get("display_name") or (work or {}).get("title")
             or ref.get("title") or "")
    return {
        "openalex_id": (work or {}).get("id"),
        "title": title,
        "doi": doi,
        "status": status,
        "filename": filename,
        "oa_url": oa_url,
        "raw": ref.get("raw") or "",
    }


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

def _corpus_filename(ref: dict, work: dict | None, taken: set[str]) -> str:
    """``<lastname>_<year>_<slug title>.pdf`` — the form labels.py matches on."""
    work = work or {}
    title = work.get("display_name") or work.get("title") or ref.get("title") or "unknown"
    year = str(work.get("publication_year") or ref.get("year") or "")
    authorships = work.get("authorships") or []
    author = ""
    if authorships:
        author = ((authorships[0].get("author") or {}).get("display_name") or "")
    elif ref.get("authors"):
        author = ref["authors"][0]
    first_author = _safe_stem(author.split()[-1] if author else "")
    stem = _safe_stem(f"{first_author}_{year}_{title}", max_len=80)
    filename = f"{stem}.pdf"
    n = 2
    while filename in taken:
        filename = f"{stem}_{n}.pdf"
        n += 1
    taken.add(filename)
    return filename


def _resume_index(corpus_dir: Path, source: Path) -> dict[str, dict]:
    """Prior outcomes keyed by raw citation string, for resumable re-runs.

    Discarded when the source PDF or the extractor changed, since the reference
    list itself would then be different.
    """
    prior = load_sidecar(corpus_dir)
    if not prior:
        return {}
    if prior.get("extractor_version") != EXTRACTOR_VERSION:
        return {}
    if prior.get("source_sha256") and source.exists():
        if prior["source_sha256"] != _sha256_file(source):
            return {}
    out = {}
    for entry in prior.get("references") or []:
        if not isinstance(entry, dict):
            continue
        key = entry.get("raw") or entry.get("title") or ""
        if key:
            out[key] = entry
    return out


async def build_corpus_from_refs(
    corpus_name: str,
    source_pdf: Path,
    refs: list[dict],
    max_papers: int = MAX_PAPERS_DEFAULT,
    force: bool = False,
) -> tuple[int, list[dict]]:
    """Resolve + download ``refs``, writing the references.json sidecar.

    Returns ``(n_downloaded, sidecar_entries)``. Every reference gets an entry,
    resolved or not: that list is the resolution denominator.
    """
    corpus_dir = CORPORA_DIR / corpus_name
    corpus_dir.mkdir(parents=True, exist_ok=True)

    if not refs:
        print(f"[build-corpus] {corpus_name}: no references extracted — corpus will be empty")
        write_sidecar(corpus_dir, source_pdf, [])
        return 0, []

    prior = {} if force else _resume_index(corpus_dir, source_pdf)
    limit = len(refs) if max_papers <= 0 else max_papers

    attempt: list[dict] = []
    entries: list[dict] = []
    taken: set[str] = {p.name for p in corpus_dir.glob("*.pdf")}

    for i, ref in enumerate(refs):
        key = ref.get("raw") or ref.get("title") or ""
        done = prior.get(key)
        if done and done.get("status") == STATUS_RESOLVED and done.get("filename") \
                and (corpus_dir / done["filename"]).exists():
            entries.append(done)
            continue
        if done and done.get("status") in {STATUS_NO_OPENALEX, STATUS_NO_OA_PDF, STATUS_DOWNLOAD_FAILED}:
            entries.append(done)
            continue
        if i >= limit:
            entries.append(_sidecar_entry(ref, STATUS_SKIPPED))
            continue
        attempt.append(ref)

    if not attempt:
        print(f"[build-corpus] {corpus_name}: all {len(refs)} refs already recorded — nothing to do")
        write_sidecar(corpus_dir, source_pdf, entries)
        return sum(1 for e in entries if e["status"] == STATUS_RESOLVED), entries

    print(f"[build-corpus] {corpus_name}: resolving {len(attempt)}/{len(refs)} refs against OpenAlex …")
    sem = asyncio.Semaphore(OA_CONCURRENCY)

    async def _guarded(session, ref):
        async with sem:
            return await _resolve_ref(session, ref)

    async with _client_session() as session:
        results = await asyncio.gather(
            *[_guarded(session, ref) for ref in attempt], return_exceptions=True
        )

    budget_exhausted = any(isinstance(r, OpenAlexBudgetExhausted) for r in results)
    pending: list[tuple[dict, dict, str]] = []  # (ref, work, oa_url)
    for ref, result in zip(attempt, results):
        if isinstance(result, OpenAlexBudgetExhausted):
            # Never looked up. Counted in the denominator, retried next run.
            entries.append(_sidecar_entry(ref, STATUS_PENDING))
            continue
        if isinstance(result, Exception):
            entries.append(_sidecar_entry(ref, STATUS_NO_OPENALEX))
            continue
        _, work = result
        if not work:
            entries.append(_sidecar_entry(ref, STATUS_NO_OPENALEX))
            continue
        oa_url = _extract_oa_url(work)
        if not oa_url:
            entries.append(_sidecar_entry(ref, STATUS_NO_OA_PDF, work))
            continue
        pending.append((ref, work, oa_url))

    print(f"[build-corpus] {corpus_name}: {len(pending)}/{len(attempt)} refs have an OA url")

    downloaded = 0
    async with _client_session() as session:
        for ref, work, oa_url in pending:
            filename = _corpus_filename(ref, work, taken)
            dest = corpus_dir / filename
            ok = dest.exists() and not force
            if not ok:
                ok = await _download_pdf(session, oa_url, dest)
            if ok:
                downloaded += 1
                entries.append(_sidecar_entry(ref, STATUS_RESOLVED, work, filename, oa_url))
                print(f"[build-corpus]   ✓ {filename} ({dest.stat().st_size // 1024}KB)")
            else:
                taken.discard(filename)
                entries.append(_sidecar_entry(ref, STATUS_DOWNLOAD_FAILED, work, None, oa_url))
                print(f"[build-corpus]   ✗ {oa_url[:80]}")

    resolved_total = sum(1 for e in entries if e["status"] == STATUS_RESOLVED)
    write_sidecar(corpus_dir, source_pdf, entries)
    print(f"[build-corpus] {corpus_name}: {resolved_total}/{len(entries)} references resolved → {corpus_dir}")
    if budget_exhausted:
        n_pending = sum(1 for e in entries if e["status"] == STATUS_PENDING)
        raise OpenAlexBudgetExhausted(
            f"{corpus_name}: OpenAlex daily budget exhausted with {n_pending} references "
            f"still unlooked-up (recorded as '{STATUS_PENDING}'). Re-run after midnight UTC."
        )
    return resolved_total, entries


async def build_corpus_for_draft(
    draft_path: Path,
    max_papers: int = MAX_PAPERS_DEFAULT,
    force: bool = False,
) -> int:
    """Build corpus for a single draft (references via GROBID)."""
    corpus_dir = CORPORA_DIR / draft_path.stem
    if not force and list(corpus_dir.glob("*.pdf")) and (corpus_dir / REFERENCES_SIDECAR).exists():
        existing = len(list(corpus_dir.glob("*.pdf")))
        print(f"[build-corpus] {draft_path.stem}: corpus already has {existing} PDFs (use --force to re-download)")
        return existing

    refs = await _extract_refs_from_draft(draft_path)
    count, _ = await build_corpus_from_refs(
        draft_path.stem, draft_path, refs, max_papers=max_papers, force=force
    )
    return count


async def build_corpus_for_openreview(
    paper_id: str,
    max_papers: int = MAX_PAPERS_DEFAULT,
    force: bool = False,
) -> int:
    """Build corpus for an OpenReview submission (references parsed from the PDF)."""
    matches = sorted(OPENREVIEW_DIR.glob(f"*/{paper_id}.pdf"))
    if not matches:
        print(f"[build-corpus] ERROR: no PDF for OpenReview id {paper_id} under {OPENREVIEW_DIR}")
        return 0
    pdf_path = matches[0]
    refs = _extract_refs_from_pdf(pdf_path)
    print(f"[build-corpus] {paper_id}: parsed {len(refs)} references from {pdf_path.name}")
    count, _ = await build_corpus_from_refs(
        paper_id, pdf_path, refs, max_papers=max_papers, force=force
    )
    return count


def openreview_ids_with_claims(exports_dir: Path | None = None) -> list[str]:
    """OpenReview ids that have both a PDF on disk and cached claims (= queries)."""
    exports = exports_dir or (EVAL_DIR / "cache" / "exports")
    topics: set[str] = set()
    for path in sorted(exports.glob("*.json")):
        try:
            payload = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        draft_file = (payload.get("eval_metadata") or {}).get("draft_file")
        if not isinstance(draft_file, str) or not (payload.get("claims") or []):
            continue
        topics.add(Path(draft_file).stem)
    return sorted(t for t in topics if list(OPENREVIEW_DIR.glob(f"*/{t}.pdf")))


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
    stems_built: list[str] = []

    if args.openreview or args.openreview_all:
        ids = [args.openreview] if args.openreview else openreview_ids_with_claims()
        if not ids:
            print("[build-corpus] No OpenReview papers with cached claims found")
            return 1
        print(f"[build-corpus] Building corpora for {len(ids)} OpenReview papers …")
        for paper_id in ids:
            try:
                count = await build_corpus_for_openreview(
                    paper_id, max_papers=args.max_papers, force=args.force
                )
            except OpenAlexBudgetExhausted as exc:
                print(f"\n[build-corpus] STOPPING: {exc}")
                print(f"[build-corpus] Not started: {', '.join(ids[ids.index(paper_id) + 1:]) or 'none'}")
                print(f"[build-corpus] Corpora completed this run: {stems_built or 'none'}")
                return 2
            if count > 0:
                stems_built.append(paper_id)
    else:
        if args.all:
            draft_paths = sorted(PDFS_DIR.glob("*.pdf"))
            if not draft_paths:
                print(f"[build-corpus] No PDFs found in {PDFS_DIR}")
                return 1
            print(f"[build-corpus] Building corpora for {len(draft_paths)} drafts …")
        else:
            draft_paths = [(REPO_ROOT / args.draft).resolve()]

        for draft_path in draft_paths:
            if not draft_path.exists():
                print(f"[build-corpus] ERROR: not found: {draft_path}")
                continue
            count = await build_corpus_for_draft(draft_path, max_papers=args.max_papers, force=args.force)
            if count > 0:
                stems_built.append(draft_path.stem)

    # config.yaml uses auto_corpus: true — no need to add to the corpora list,
    # so _update_config_yaml() is intentionally not called.
    print(f"\n[build-corpus] Done. Corpora built for: {stems_built or 'none'}")
    print(f"[build-corpus] Run eval with: python scripts/eval/run_eval.py")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build eval corpus by downloading cited papers from OpenAlex")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--draft", help="Path to draft PDF (relative to repo root), e.g. pdfs/draft1.pdf")
    g.add_argument("--all", action="store_true", help="Build corpora for all PDFs in scripts/eval/pdfs/")
    g.add_argument("--openreview", metavar="ID", help="Build corpus for one OpenReview submission id")
    g.add_argument("--openreview-all", action="store_true",
                   help="Build corpora for every OpenReview paper that has cached claims")
    p.add_argument("--max-papers", type=int, default=MAX_PAPERS_DEFAULT,
                   help=f"Max refs to attempt per paper, 0 = all (default: {MAX_PAPERS_DEFAULT})")
    p.add_argument("--force", action="store_true", help="Re-download even if corpus already exists")
    p.add_argument("--no-config-update", action="store_true", help="Deprecated; config.yaml is never written")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main(parse_args())))
