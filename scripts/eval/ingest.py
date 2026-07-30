"""Ingest the eval corpus PDFs into the LOCAL pgvector database.

WHY THIS EXISTS
    scripts/eval/retrieval/ can measure recall@k, MRR and NDCG, but only against
    chunks that actually exist in a database. Production ingestion
    (app/services/rag_ingest.ingest_document) is unusable here: it reads the
    document row from Supabase, downloads bytes from Supabase Storage, and writes
    back through PostgREST. This module does the same *work* against local files
    and local Postgres, while importing the production chunker and the production
    embedding call so the eval measures the product rather than a lookalike.

WHAT IS REUSED FROM PRODUCTION (do not reimplement)
    app.services.rag_chunking.get_chunking_strategy  -- page-count tiers, cost ceiling
    app.services.rag_ingest.chunk_text               -- the actual token chunker
    app.services.rag_ingest.embed_chunks             -- text-embedding-3-large @ dim=1536

WHAT DELIBERATELY DIFFERS FROM PRODUCTION (and is recorded per document)
    PDF text extraction. Production tries Docling -> GROBID -> PyMuPDF. GROBID and
    Docling are heavy containers and are not assumed to be running, so this path
    uses PyMuPDF only. That matters: without GROBID sections, production itself
    falls back to *basic* adaptive chunking (rag_ingest step 6), which is exactly
    the arm reproduced here. The manifest records extractor="pymupdf" and
    chunking_method="basic" on every row so no downstream number can silently be
    attributed to the section-aware arm.

PROJECT SCOPING
    Every chunk is written under one fixed project id, EVAL_PROJECT_ID below, so
    the retrieval harness can query the entire corpus with a single
    match_document_chunks(embedding, EVAL_PROJECT_ID, k) call. It is a constant,
    not a random UUID, so a harness run started in a different process still finds
    the corpus.

DOCUMENT IDENTITY / IDEMPOTENCY
    document_id = uuid5(EVAL_DOC_NAMESPACE, sha256(pdf bytes)). Stable across
    machines and runs, and identical for two copies of the same PDF filed under
    different corpus directories -- so the 39 corpus files collapse to their
    unique-document count on purpose.

    A run skips any document whose ingest *fingerprint* (content hash + splitter +
    chunk size/overlap + embedding model + dimensions + extractor) matches the
    recorded state AND whose chunk rows are still present in the database. If the
    fingerprint changed, its rows are deleted and it is re-ingested -- stale chunks
    from an older chunker setting must never linger in the same project.

COST
    Embedding is the only spend. `--dry-run` reports chunk and token counts and
    calls nothing. Real runs honour NOESIS_LLM_KILL_SWITCH / EVAL_REPLAY_ONLY /
    NOESIS_LLM_MAX_CALLS via app.core.llm_budget.check_llm_allowed, and record
    usage via record_usage. Token counts come from tiktoken cl100k_base (the
    encoding text-embedding-3-* uses); the embeddings endpoint response carries no
    per-request usage through embed_chunks' return value.

USAGE
    python3 scripts/eval/ingest.py --dry-run
    python3 scripts/eval/ingest.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

EVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = EVAL_DIR.parent.parent
BACKEND_DIR = REPO_ROOT / "services" / "backend"

for _path in (str(BACKEND_DIR), str(EVAL_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _load_backend_env() -> None:
    """Populate OPENAI_API_KEY et al. from services/backend/.env.

    app.core.config uses env_file=".env" relative to the *process* cwd, so the
    settings object is empty when this script runs from anywhere else. Existing
    environment variables always win.
    """
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_backend_env()

import fitz  # PyMuPDF  # noqa: E402
import tiktoken  # noqa: E402

import db as eval_db  # noqa: E402  (scripts/eval/db.py)

from app.core.llm_budget import (  # noqa: E402
    check_llm_allowed,
    estimate_usd,
    record_usage,
)
from app.services.rag_chunking import get_chunking_strategy  # noqa: E402
from app.services.rag_ingest import chunk_text, embed_chunks  # noqa: E402

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# The one project every eval chunk lives under. Fixed, documented, never random.
EVAL_PROJECT_ID = "e7a1c0b0-0000-4000-8000-000000000001"

# Namespace for deriving a stable document id from PDF content.
EVAL_DOC_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")

EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = eval_db.EMBEDDING_DIM  # 1536
EXTRACTOR = "pymupdf"
CHUNKING_METHOD = "basic"  # no GROBID sections available; see module docstring

DEFAULT_CORPORA_DIR = EVAL_DIR / "corpora"
DEFAULT_MANIFEST = EVAL_DIR / "cache" / "ingest_manifest.jsonl"
DEFAULT_STATE = EVAL_DIR / "cache" / "ingest_state.json"

USAGE_LABEL = "eval_ingest_embed"

_ENCODER = None


def _encoder():
    global _ENCODER
    if _ENCODER is None:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    return _ENCODER


def count_tokens(text: str) -> int:
    return len(_encoder().encode(text))


# --------------------------------------------------------------------------
# Discovery / extraction
# --------------------------------------------------------------------------


def iter_corpus_pdfs(corpora_dir: Path) -> List[Path]:
    """Every PDF under corpora/, sorted. New corpus dirs are picked up for free."""
    if not corpora_dir.exists():
        return []
    return sorted(p for p in corpora_dir.rglob("*.pdf") if p.is_file())


class ExtractionError(RuntimeError):
    """The PDF could not be opened or yielded no text layer."""


def extract_pdf(path: Path) -> Tuple[str, int, int]:
    """Return (full_text, page_count, nul_chars_stripped) using PyMuPDF.

    Raises ExtractionError for an unreadable file or a PDF with no text layer
    (i.e. a scan). Callers record the failure rather than aborting the run.

    NUL STRIPPING: some PDFs in the corpus carry U+0000 in their text layer (bad
    embedded font encodings). PostgreSQL `text` cannot store a NUL, so the insert
    dies with `ValueError: A string literal cannot contain NUL`. Production hits
    the same wall through PostgREST, it just fails the document instead. NULs are
    dropped here and the count is recorded per document, because a silent content
    edit upstream of chunking is exactly the kind of thing that must not be
    invisible when a retrieval number looks off.
    """
    try:
        doc = fitz.open(str(path))
    except Exception as exc:  # corrupt / not a PDF / encrypted
        raise ExtractionError(f"cannot open: {type(exc).__name__}: {exc}") from exc

    try:
        page_count = len(doc)
        text = "".join(page.get_text() for page in doc)
    except Exception as exc:
        raise ExtractionError(f"cannot read pages: {type(exc).__name__}: {exc}") from exc
    finally:
        doc.close()

    nul_count = text.count("\x00")
    if nul_count:
        text = text.replace("\x00", "")

    if not text.strip():
        raise ExtractionError(
            f"no text layer ({page_count} pages) -- likely a scanned image PDF"
        )
    return text, page_count, nul_count


def chunk_document_text(text: str, page_count: int) -> Tuple[List[str], Dict[str, Any]]:
    """Chunk with the PRODUCTION strategy + PRODUCTION chunker. No local logic."""
    total_tokens = count_tokens(text)
    strategy = get_chunking_strategy(page_count=page_count, total_tokens=total_tokens)
    chunks = chunk_text(
        text,
        max_tokens=strategy["chunk_size"],
        overlap_tokens=strategy["overlap"],
    )
    return chunks, strategy


# --------------------------------------------------------------------------
# Planning
# --------------------------------------------------------------------------


def splitter_mode() -> str:
    return (os.getenv("CHUNKING_SPLITTER", "pysbd").strip().lower() or "pysbd")


@dataclass
class DocumentPlan:
    """Everything known about one source PDF before any money is spent."""

    source_path: str
    content_sha256: str
    doc_id: str
    extractor: str = EXTRACTOR
    page_count: int = 0
    chunk_count: int = 0
    token_count: int = 0
    embedding_model: str = EMBEDDING_MODEL
    embedding_dimensions: int = EMBEDDING_DIMENSIONS
    chunking_splitter: str = ""
    chunking_method: str = CHUNKING_METHOD
    tier: str = ""
    chunk_size: int = 0
    chunk_overlap: int = 0
    cost_ceiling_applied: bool = False
    nul_chars_stripped: int = 0
    error: Optional[str] = None
    chunks: List[str] = field(default_factory=list, repr=False)

    @property
    def ok(self) -> bool:
        return self.error is None and self.chunk_count > 0

    def fingerprint(self) -> str:
        """Content + every setting that changes what lands in the database."""
        payload = "|".join(
            str(x)
            for x in (
                self.content_sha256,
                self.extractor,
                self.chunking_splitter,
                self.chunking_method,
                self.chunk_size,
                self.chunk_overlap,
                self.embedding_model,
                self.embedding_dimensions,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def manifest_record(self, **extra: Any) -> Dict[str, Any]:
        record = {k: v for k, v in asdict(self).items() if k != "chunks"}
        record["fingerprint"] = self.fingerprint()
        record.update(extra)
        return record


def document_id_for(content_sha256: str) -> str:
    return str(uuid.uuid5(EVAL_DOC_NAMESPACE, content_sha256))


def plan_document(path: Path) -> DocumentPlan:
    """Parse + chunk one PDF. Never raises: failures come back as plan.error."""
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    plan = DocumentPlan(
        source_path=str(path),
        content_sha256=sha,
        doc_id=document_id_for(sha),
        chunking_splitter=splitter_mode(),
    )
    try:
        text, page_count, nul_count = extract_pdf(path)
    except ExtractionError as exc:
        plan.error = str(exc)
        return plan

    plan.page_count = page_count
    plan.nul_chars_stripped = nul_count
    chunks, strategy = chunk_document_text(text, page_count)
    if not chunks:
        plan.error = "chunking produced no chunks"
        return plan

    plan.chunks = chunks
    plan.chunk_count = len(chunks)
    plan.token_count = sum(count_tokens(c) for c in chunks)
    plan.tier = strategy["tier"]
    plan.chunk_size = strategy["chunk_size"]
    plan.chunk_overlap = strategy["overlap"]
    plan.cost_ceiling_applied = bool(strategy["was_adjusted"])
    return plan


def plan_corpus(corpora_dir: Path) -> List[DocumentPlan]:
    """One plan per UNIQUE document. Duplicate PDFs are collapsed by content hash."""
    plans: List[DocumentPlan] = []
    seen: Dict[str, DocumentPlan] = {}
    for path in iter_corpus_pdfs(corpora_dir):
        plan = plan_document(path)
        if plan.content_sha256 in seen:
            continue
        seen[plan.content_sha256] = plan
        plans.append(plan)
    return plans


# --------------------------------------------------------------------------
# State + manifest
# --------------------------------------------------------------------------


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def append_manifest(path: Path, records: Iterable[Dict[str, Any]]) -> None:
    """Append-only JSONL. Never truncates: a run's history is the whole point."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


# --------------------------------------------------------------------------
# Database writes
# --------------------------------------------------------------------------


def existing_chunk_count(conn, doc_id: str, project_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM document_chunks WHERE document_id = %s::uuid AND project_id = %s::uuid",
            (doc_id, project_id),
        )
        return int(cur.fetchone()[0])


def delete_document(conn, doc_id: str, project_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM document_chunks WHERE document_id = %s::uuid AND project_id = %s::uuid",
            (doc_id, project_id),
        )
        cur.execute("DELETE FROM documents WHERE id = %s::uuid", (doc_id,))


def write_document(conn, plan: DocumentPlan, embeddings: List[Any], project_id: str) -> int:
    """Insert the documents row and every chunk. Caller commits."""
    title = Path(plan.source_path).stem
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO documents (id, title, project_id) VALUES (%s::uuid, %s, %s::uuid)
            ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, project_id = EXCLUDED.project_id
            """,
            (plan.doc_id, title, project_id),
        )
        for index, (content, emb) in enumerate(zip(plan.chunks, embeddings)):
            vector = eval_db.format_vector(emb.embedding)
            cur.execute(
                """
                INSERT INTO document_chunks
                    (document_id, project_id, chunk_index, content, embedding, content_tsvector)
                VALUES (%s::uuid, %s::uuid, %s, %s, %s::vector, to_tsvector('english', %s))
                """,
                (plan.doc_id, project_id, index, content, vector, content),
            )
    return len(embeddings)


def embed_plan(plan: DocumentPlan) -> List[Any]:
    """Guarded, accounted call to the PRODUCTION embedding function."""
    check_llm_allowed(USAGE_LABEL)
    embeddings = embed_chunks(plan.chunks, model=plan.embedding_model)
    record_usage(
        model=plan.embedding_model,
        prompt_tokens=plan.token_count,
        label=USAGE_LABEL,
    )
    if len(embeddings) != plan.chunk_count:
        raise RuntimeError(
            f"embedding count {len(embeddings)} != chunk count {plan.chunk_count} "
            f"for {plan.source_path}"
        )
    return embeddings


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def format_cost(tokens: int, model: str = EMBEDDING_MODEL) -> str:
    """Dollar figure when pricing is known; an explicit 'unknown' when it is not.

    app.core.llm_budget deliberately leaves prices as None rather than guessing,
    so this must never print $0.00 for an unpriced model.
    """
    usd = estimate_usd(model, tokens, 0)
    if usd is None:
        return f"unknown (no price recorded for {model} in llm_budget.MODEL_PRICING_USD_PER_1M)"
    return f"${usd:.4f}"


def run_ingest(
    corpora_dir: Path = DEFAULT_CORPORA_DIR,
    project_id: str = EVAL_PROJECT_ID,
    manifest_path: Path = DEFAULT_MANIFEST,
    state_path: Path = DEFAULT_STATE,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    started = time.time()
    plans = plan_corpus(corpora_dir)
    usable = [p for p in plans if p.ok]
    failed = [p for p in plans if not p.ok]

    summary: Dict[str, Any] = {
        "corpora_dir": str(corpora_dir),
        "project_id": project_id,
        "documents_found": len(plans),
        "documents_failed": len(failed),
        "documents_ingested": 0,
        "documents_skipped": 0,
        "chunks_inserted": 0,
        "tokens_embedded": 0,
        "dry_run": dry_run,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "extractor": EXTRACTOR,
        "chunking_splitter": splitter_mode(),
        "failures": [
            {"source_path": p.source_path, "error": p.error} for p in failed
        ],
    }

    if dry_run:
        pending_chunks = sum(p.chunk_count for p in usable)
        pending_tokens = sum(p.token_count for p in usable)
        summary["chunks_pending"] = pending_chunks
        summary["tokens_pending"] = pending_tokens
        summary["estimated_cost"] = format_cost(pending_tokens)
        summary["elapsed_seconds"] = round(time.time() - started, 2)
        if verbose:
            _print_summary(summary, plans)
        return summary

    state = load_state(state_path)
    records: List[Dict[str, Any]] = []

    with eval_db.get_connection() as conn:
        for plan in failed:
            records.append(plan.manifest_record(action="failed"))

        for plan in usable:
            fingerprint = plan.fingerprint()
            prior = state.get(plan.doc_id)
            db_count = existing_chunk_count(conn, plan.doc_id, project_id)

            up_to_date = (
                not force
                and prior is not None
                and prior.get("fingerprint") == fingerprint
                and db_count == plan.chunk_count
            )
            if up_to_date:
                summary["documents_skipped"] += 1
                records.append(plan.manifest_record(action="skipped", rows_inserted=0))
                continue

            if db_count or prior is not None:
                # Settings changed, or a partial write is present. Stale chunks in
                # this project would silently pollute every retrieval number.
                delete_document(conn, plan.doc_id, project_id)

            embeddings = embed_plan(plan)
            inserted = write_document(conn, plan, embeddings, project_id)
            conn.commit()

            state[plan.doc_id] = {
                "fingerprint": fingerprint,
                "source_path": plan.source_path,
                "chunk_count": plan.chunk_count,
                "token_count": plan.token_count,
                "ingested_at": time.time(),
            }
            save_state(state_path, state)

            summary["documents_ingested"] += 1
            summary["chunks_inserted"] += inserted
            summary["tokens_embedded"] += plan.token_count
            records.append(plan.manifest_record(action="ingested", rows_inserted=inserted))
            if verbose:
                print(
                    f"  ingested {Path(plan.source_path).name}: "
                    f"{inserted} chunks, {plan.token_count} tokens "
                    f"({plan.tier} tier, size={plan.chunk_size}/overlap={plan.chunk_overlap})"
                )

    append_manifest(manifest_path, records)
    summary["actual_cost"] = format_cost(summary["tokens_embedded"])
    summary["manifest_path"] = str(manifest_path)
    summary["state_path"] = str(state_path)
    summary["elapsed_seconds"] = round(time.time() - started, 2)
    if verbose:
        _print_summary(summary, plans)
    return summary


def _print_summary(summary: Dict[str, Any], plans: List[DocumentPlan]) -> None:
    print()
    print("=" * 70)
    print("DRY RUN — nothing embedded, nothing written" if summary["dry_run"] else "INGEST COMPLETE")
    print("=" * 70)
    print(f"corpora dir        : {summary['corpora_dir']}")
    print(f"eval project id    : {summary['project_id']}")
    print(f"unique documents   : {summary['documents_found']} ({summary['documents_failed']} unusable)")
    if summary["dry_run"]:
        print(f"chunks to embed    : {summary['chunks_pending']}")
        print(f"tokens to embed    : {summary['tokens_pending']}")
        print(f"estimated cost     : {summary['estimated_cost']}")
    else:
        print(f"documents ingested : {summary['documents_ingested']}")
        print(f"documents skipped  : {summary['documents_skipped']} (unchanged)")
        print(f"chunk rows inserted: {summary['chunks_inserted']}")
        print(f"tokens embedded    : {summary['tokens_embedded']}")
        print(f"actual cost        : {summary['actual_cost']}")
        print(f"manifest           : {summary['manifest_path']}")
    print(f"extractor          : {summary['extractor']}")
    print(f"embedding          : {summary['embedding_model']} @ dim={summary['embedding_dimensions']}")
    print(f"CHUNKING_SPLITTER  : {summary['chunking_splitter']}")
    print(f"wall clock         : {summary['elapsed_seconds']}s")
    if summary["failures"]:
        print("\nUNUSABLE DOCUMENTS (skipped, recorded in manifest):")
        for failure in summary["failures"]:
            print(f"  - {Path(failure['source_path']).name}: {failure['error']}")
    usable = [p for p in plans if p.ok]
    if usable:
        shortest = min(usable, key=lambda p: p.token_count)
        longest = max(usable, key=lambda p: p.token_count)
        ceilinged = [p for p in usable if p.cost_ceiling_applied]
        nul_docs = [p for p in usable if p.nul_chars_stripped]
        print(
            f"\ntoken range        : {shortest.token_count} ({Path(shortest.source_path).name}) "
            f"-> {longest.token_count} ({Path(longest.source_path).name})"
        )
        print(f"cost ceiling hit   : {len(ceilinged)} document(s)")
        if nul_docs:
            print(
                f"NUL chars stripped : {len(nul_docs)} document(s) "
                f"({sum(p.nul_chars_stripped for p in nul_docs)} chars) — bad font encodings"
            )
            for plan in nul_docs:
                print(f"  - {Path(plan.source_path).name}: {plan.nul_chars_stripped}")
    print()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpora", type=Path, default=DEFAULT_CORPORA_DIR)
    parser.add_argument("--project-id", default=EVAL_PROJECT_ID)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report chunks/tokens/cost that WOULD be embedded; makes no API call",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-embed every document even if its fingerprint is unchanged",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not eval_db.healthcheck():
        print(
            "local pgvector unreachable. Start it with:\n"
            "  cd infra && docker compose --profile core up -d pgvector",
            file=sys.stderr,
        )
        return 2

    run_ingest(
        corpora_dir=args.corpora,
        project_id=args.project_id,
        manifest_path=args.manifest,
        state_path=args.state,
        dry_run=args.dry_run,
        force=args.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
