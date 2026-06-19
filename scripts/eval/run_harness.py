"""
Headless eval harness: upload a draft PDF + optional corpus → run full LangGraph
pipeline → export complete JSON to scripts/eval/results/.

Must run INSIDE the backend container (has app code, env, Supabase, OpenAI):
    docker exec noesis-backend python scripts/eval/run_harness.py --draft pdfs/draft3.pdf --corpus corpus_a
    docker exec noesis-backend python scripts/eval/run_harness.py --draft pdfs/draft3.pdf --no-corpus

Or from repo root via the Makefile target (see Makefile).
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
import uuid
from pathlib import Path

# Inside container: /app/app exists, sys.path needs /app
# Outside container: sys.path needs <repo>/services/backend
if Path("/app/app").exists():
    REPO_ROOT = Path("/app")
    if "/app" not in sys.path:
        sys.path.insert(0, "/app")
else:
    REPO_ROOT = Path(__file__).resolve().parent.parent.parent
    _svc = str(REPO_ROOT / "services" / "backend")
    if _svc not in sys.path:
        sys.path.insert(0, _svc)

from app.core.supabase_client import supabase
from app.services.draft_processing import ingest_draft
from app.services.draft_analysis_langgraph import analyze_draft_with_langgraph
from app.services.rag_ingest import ingest_document

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"
CORPORA_DIR = EVAL_DIR / "corpora"

# Fixed eval user/project — set EVAL_PROJECT_ID + EVAL_USER_ID in env to pin;
# otherwise a fresh throwaway project is created each run and cleaned up.
EVAL_PROJECT_ID_ENV = os.environ.get("EVAL_PROJECT_ID", "")


def _get_eval_user_id() -> str:
    """Use EVAL_USER_ID env var, or fall back to the first real user in DB."""
    env_uid = os.environ.get("EVAL_USER_ID", "")
    if env_uid:
        return env_uid
    r = supabase.table("projects").select("user_id").limit(1).execute()
    if r.data:
        uid = r.data[0]["user_id"]
        print(f"[harness] Using existing user_id={uid} (set EVAL_USER_ID env var to pin)")
        return uid
    raise RuntimeError("No existing user_id found. Set EVAL_USER_ID env var to a valid Supabase auth user UUID.")


def _now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds").replace(":", "-")


def _ensure_eval_project(project_id: str | None, user_id: str) -> str:
    if project_id:
        r = supabase.table("projects").select("id").eq("id", project_id).limit(1).execute()
        if r.data:
            return project_id
    pid = str(uuid.uuid4())
    supabase.table("projects").insert({
        "id": pid,
        "user_id": user_id,
        "title": f"[EVAL] {_now()}",
        "description": "Throwaway eval project — safe to delete",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }).execute()
    print(f"[harness] Created eval project {pid}")
    return pid


def _ingest_corpus(corpus_name: str, project_id: str, user_id: str = "") -> list[str]:
    corpus_dir = CORPORA_DIR / corpus_name
    if not corpus_dir.exists():
        print(f"[harness] Corpus dir not found: {corpus_dir} — skipping corpus ingest")
        return []

    pdfs = list(corpus_dir.glob("*.pdf")) + list(corpus_dir.glob("*.txt"))
    if not pdfs:
        print(f"[harness] No PDFs/TXTs in {corpus_dir} — skipping corpus ingest")
        return []

    doc_ids: list[str] = []
    for pdf_path in pdfs:
        doc_id = str(uuid.uuid4())
        file_bytes = pdf_path.read_bytes()
        file_ext = pdf_path.suffix.lstrip(".")
        storage_path = f"{user_id}/corpus/{doc_id}.{file_ext}"
        content_type = "application/pdf" if file_ext == "pdf" else "text/plain"

        print(f"[harness] Uploading corpus doc: {pdf_path.name}")
        supabase.storage.from_("documents").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type},
        )
        file_url = supabase.storage.from_("documents").get_public_url(storage_path)

        supabase.table("documents").insert({
            "id": doc_id,
            "user_id": user_id,
            "project_id": project_id,
            "title": pdf_path.stem,
            "file_url": file_url,
            "file_type": file_ext,
            "status": "processing",
            "source_type": "manual_upload",
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }).execute()

        print(f"[harness] Ingesting corpus doc {doc_id} …")
        asyncio.get_event_loop().run_until_complete(ingest_document(doc_id, project_id))
        print(f"[harness] ✓ Corpus doc ingested: {pdf_path.name}")
        doc_ids.append(doc_id)

    print(f"[harness] Corpus '{corpus_name}' ingested: {len(doc_ids)} docs")
    return doc_ids


def _upload_draft(draft_path: Path, project_id: str, user_id: str = "") -> str:
    draft_id = str(uuid.uuid4())
    file_bytes = draft_path.read_bytes()
    file_ext = draft_path.suffix.lstrip(".")
    storage_path = f"{user_id}/{draft_id}.{file_ext}"
    content_type = {"pdf": "application/pdf", "txt": "text/plain", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(file_ext, "application/octet-stream")

    print(f"[harness] Uploading draft: {draft_path.name}")
    supabase.storage.from_("drafts").upload(
        path=storage_path,
        file=file_bytes,
        file_options={"content-type": content_type},
    )
    file_url = supabase.storage.from_("drafts").get_public_url(storage_path)

    supabase.table("drafts").insert({
        "id": draft_id,
        "user_id": user_id,
        "project_id": project_id,
        "title": f"[EVAL] {draft_path.stem}",
        "version": 1,
        "file_url": file_url,
        "file_type": file_ext,
        "file_size": len(file_bytes),
        "paper_type": "journal_article",
        "citation_style": "auto",
        "status": "processing",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }).execute()

    print(f"[harness] Draft row created: {draft_id}")
    return draft_id


def _export_result(draft_id: str, project_id: str, draft_stem: str, corpus_name: str) -> dict:
    # Import helpers only — use app's already-initialized supabase, not the export script's own client
    from scripts.export_latest_draft_analysis import (  # type: ignore[import]
        safe_select, select_related, draft_by_id,
        latest_analysis_row, sanitize_analysis_row_for_export,
        parser_metrics, project_literature_summary, table_count,
    )
    client = supabase  # app.core.supabase_client instance (already has env)

    draft = draft_by_id(client, draft_id)
    analysis_run_id = draft.get("active_analysis_run_id")
    analysis = sanitize_analysis_row_for_export(latest_analysis_row(client, draft_id, analysis_run_id))
    metadata = analysis.get("analysis_metadata") or {}
    profile = metadata.get("manuscript_profile") or {}

    parse_artifacts = safe_select(client, "draft_parse_artifacts", draft_id=draft_id)
    parse_artifact = parse_artifacts[0] if parse_artifacts else {}
    durable_revision_tasks = select_related(client, "draft_revision_tasks", draft_id, analysis_run_id)
    project_documents = safe_select(client, "documents", project_id=project_id)
    literature_summary = project_literature_summary(project_documents, profile)

    payload = {
        "eval_metadata": {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "draft_file": draft_stem,
            "corpus": corpus_name,
            "draft_id": draft_id,
            "project_id": project_id,
            "analysis_run_id": analysis_run_id,
        },
        "draft": draft,
        "analysis": analysis,
        "analysis_run": safe_select(client, "draft_analysis_runs", id=analysis_run_id)[0] if analysis_run_id else {},
        "parser_metadata": parser_metrics(parse_artifact, analysis),
        "durable_revision_tasks": durable_revision_tasks,
        "claims": select_related(client, "draft_claims", draft_id, analysis_run_id),
        "coverage_gaps": select_related(client, "coverage_gaps", draft_id, analysis_run_id),
        "reviewer_feedback": select_related(client, "reviewer_feedback", draft_id, analysis_run_id),
        "reviewer_panel_outputs": select_related(client, "reviewer_panel_outputs", draft_id, analysis_run_id),
        "meta_reviews": select_related(client, "meta_reviews", draft_id, analysis_run_id),
        "citation_suggestions": select_related(client, "citation_suggestions", draft_id, analysis_run_id),
        "project_literature_summary": literature_summary,
    }
    payload["summary_counts"] = {
        "durable_revision_tasks": table_count(payload["durable_revision_tasks"]),
        "claims": table_count(payload["claims"]),
        "coverage_gaps": table_count(payload["coverage_gaps"]),
        "reviewer_feedback": table_count(payload["reviewer_feedback"]),
        "reviewer_panel_outputs": table_count(payload["reviewer_panel_outputs"]),
        "meta_reviews": table_count(payload["meta_reviews"]),
        "citation_suggestions": table_count(payload["citation_suggestions"]),
    }
    return payload


def _cleanup_eval_rows(draft_id: str) -> None:
    for table in (
        "reviewer_panel_outputs", "meta_reviews", "reviewer_feedback",
        "draft_revision_tasks", "draft_claims", "coverage_gaps",
        "citation_suggestions", "draft_analysis", "draft_analysis_runs",
        "draft_parse_artifacts", "draft_chunks",
    ):
        try:
            supabase.table(table).delete().eq("draft_id", draft_id).execute()
        except Exception:
            pass
    try:
        supabase.table("drafts").delete().eq("id", draft_id).execute()
    except Exception:
        pass


def run(draft_path: Path, corpus_name: str | None, keep: bool = False) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    user_id = _get_eval_user_id()
    project_id = _ensure_eval_project(EVAL_PROJECT_ID_ENV or None, user_id)

    # Ingest corpus
    if corpus_name:
        _ingest_corpus(corpus_name, project_id, user_id)

    # Upload + create draft row
    draft_id = _upload_draft(draft_path, project_id, user_id)

    try:
        # Ingest draft (parse, chunk, embed) — mirrors _run_draft_analysis_task exactly
        print(f"[harness] Ingesting draft …")
        ingest_result = loop.run_until_complete(ingest_draft(draft_id, project_id))
        draft_content = ingest_result.get("full_text") or ""
        initial_structure = ingest_result.get("structure") or {}
        parser_quality = ingest_result.get("parser_quality") or {}
        parse_artifact = ingest_result.get("parse_artifact") or {"id": ingest_result.get("parse_artifact_id"), "parser_quality": parser_quality}
        print(f"[harness] ✓ Draft ingested, chars={len(draft_content)}")

        # Run full LangGraph workflow
        print(f"[harness] Running LangGraph workflow …")
        loop.run_until_complete(
            analyze_draft_with_langgraph(
                draft_id=draft_id,
                project_id=project_id,
                user_id=user_id,
                draft_content=draft_content,
                initial_structure=initial_structure,
                parse_artifact=parse_artifact,
                parser_quality=parser_quality,
            )
        )
        print(f"[harness] ✓ Workflow complete")

        # Export
        corpus_label = corpus_name or "no-corpus"
        ts = _now()
        out_stem = f"{draft_path.stem}__{corpus_label}__{ts}"
        payload = _export_result(draft_id, project_id, draft_path.stem, corpus_label)
        out_path = RESULTS_DIR / f"{out_stem}.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str))

        counts = payload["summary_counts"]
        print(f"[harness] ✓ Export: {out_path}")
        print(f"[harness]   tasks={counts['durable_revision_tasks']}  claims={counts['claims']}  gaps={counts['coverage_gaps']}  reviewers={counts['reviewer_panel_outputs']}")
        return out_path

    finally:
        if not keep:
            _cleanup_eval_rows(draft_id)
            print(f"[harness] Cleaned up eval rows for draft {draft_id}")
        loop.close()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Headless Noesis eval harness")
    p.add_argument("--draft", required=True, help="Path to draft PDF/TXT (relative to repo root)")
    p.add_argument("--corpus", default=None, help="Corpus name under scripts/eval/corpora/")
    p.add_argument("--no-corpus", action="store_true", help="Skip corpus ingest")
    p.add_argument("--keep", action="store_true", help="Do not delete eval DB rows after run")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    draft_path = (REPO_ROOT / args.draft).resolve()
    if not draft_path.exists():
        print(f"[harness] ERROR: Draft not found: {draft_path}")
        sys.exit(1)
    corpus_name = None if args.no_corpus else args.corpus
    run(draft_path, corpus_name, keep=args.keep)
