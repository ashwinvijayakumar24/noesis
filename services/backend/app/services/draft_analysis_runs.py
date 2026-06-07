"""Run-isolated publishing helpers for draft analysis."""

from __future__ import annotations

import datetime
import copy
from typing import Any

from app.core.logging_config import get_logger
from app.core.privacy import safe_exception
from app.core.supabase_client import supabase

logger = get_logger(__name__)


ARTIFACT_TABLES = (
    "draft_analysis",
    "draft_claims",
    "coverage_gaps",
    "reviewer_feedback",
    "reviewer_panel_outputs",
    "meta_reviews",
    "citation_suggestions",
    "draft_revision_tasks",
)

LEGACY_DRAFT_UNIQUE_TABLES = {
    "draft_revision_tasks",
    "reviewer_panel_outputs",
    "meta_reviews",
}


def create_analysis_run(
    *,
    draft_id: str,
    project_id: str,
    user_id: str,
    attempt_number: int = 1,
    forced_route: str | None = None,
) -> str:
    payload = {
        "draft_id": draft_id,
        "project_id": project_id,
        "user_id": user_id,
        "status": "running",
        "attempt_number": attempt_number,
        "forced_route": forced_route,
        "started_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }
    res = supabase.table("draft_analysis_runs").insert(payload).execute()
    if not res.data:
        raise RuntimeError("Failed to create draft analysis run")
    return res.data[0]["id"]


def mark_analysis_run(
    run_id: str,
    *,
    status: str,
    manuscript_profile: dict[str, Any] | None = None,
    quality_gate_results: dict[str, Any] | None = None,
    source_safety_metrics: dict[str, Any] | None = None,
    failure_reason: str | None = None,
    reroute_from: str | None = None,
    reroute_to: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "status": status,
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }
    if status in {"failed", "rerouted", "passed", "published"}:
        payload["completed_at"] = datetime.datetime.utcnow().isoformat()
    if manuscript_profile is not None:
        payload["manuscript_profile"] = manuscript_profile
    if quality_gate_results is not None:
        payload["quality_gate_results"] = quality_gate_results
    if source_safety_metrics is not None:
        payload["source_safety_metrics"] = source_safety_metrics
    if failure_reason:
        payload["failure_reason"] = failure_reason
    if reroute_from:
        payload["reroute_from"] = reroute_from
    if reroute_to:
        payload["reroute_to"] = reroute_to
    supabase.table("draft_analysis_runs").update(payload).eq("id", run_id).execute()


def _with_run(row: dict[str, Any], run_id: str, *, published: bool = False) -> dict[str, Any]:
    return {
        **row,
        "analysis_run_id": run_id,
        "is_published": published,
    }


def _insert_rows(table: str, rows: list[dict[str, Any]], run_id: str) -> int:
    if not rows:
        return 0
    payload = [_with_run(row, run_id, published=False) for row in rows]
    if table == "draft_analysis":
        draft_id = payload[0].get("draft_id")
        update_res = supabase.table(table).update(payload[0]).eq("draft_id", draft_id).execute()
        if not update_res.data:
            supabase.table(table).insert(payload[0]).execute()
    else:
        supabase.table(table).insert(payload).execute()
    return len(payload)


def publish_analysis_artifacts(
    *,
    run_id: str,
    draft_id: str,
    artifacts: dict[str, list[dict[str, Any]]],
) -> dict[str, int]:
    """
    Publish a validated run.

    Rows are inserted as unpublished first. The frontend only reads rows for
    drafts.active_analysis_run_id, so partial inserts remain invisible if any
    insert fails before activation.
    """
    inserted: dict[str, int] = {}
    previous_draft_analysis: dict[str, Any] | None = None
    previous_legacy_rows: dict[str, list[dict[str, Any]]] = {}
    draft_analysis_upserted = False
    replaced_legacy_tables: set[str] = set()
    try:
        previous_res = (
            supabase.table("draft_analysis")
            .select("*")
            .eq("draft_id", draft_id)
            .limit(1)
            .execute()
        )
        previous_draft_analysis = copy.deepcopy(previous_res.data[0]) if previous_res.data else None

        # Some deployed databases still have legacy draft-scoped unique
        # constraints. Until the DB migrations that make these tables run-aware
        # are applied, replace old rows as a unit so reanalysis can publish.
        for table in LEGACY_DRAFT_UNIQUE_TABLES:
            if not artifacts.get(table):
                continue
            existing_res = (
                supabase.table(table)
                .select("*")
                .eq("draft_id", draft_id)
                .execute()
            )
            previous_legacy_rows[table] = copy.deepcopy(existing_res.data or [])
            supabase.table(table).delete().eq("draft_id", draft_id).execute()
            replaced_legacy_tables.add(table)

        for table in ARTIFACT_TABLES:
            if table == "draft_analysis":
                continue
            inserted[table] = _insert_rows(table, artifacts.get(table, []), run_id)
        inserted["draft_analysis"] = 0

        for table in ARTIFACT_TABLES:
            if table == "draft_analysis":
                continue
            supabase.table(table).update({"is_published": True}).eq("draft_id", draft_id).eq("analysis_run_id", run_id).execute()

        draft_analysis_rows = artifacts.get("draft_analysis", [])
        if draft_analysis_rows:
            inserted["draft_analysis"] = _insert_rows("draft_analysis", draft_analysis_rows, run_id)
            draft_analysis_upserted = True
            supabase.table("draft_analysis").update({"is_published": True}).eq("draft_id", draft_id).eq("analysis_run_id", run_id).execute()

        supabase.table("drafts").update({
            "active_analysis_run_id": run_id,
            "status": "analyzed",
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }).eq("id", draft_id).execute()

        for table in ARTIFACT_TABLES:
            supabase.table(table).update({"is_published": False}).eq("draft_id", draft_id).neq("analysis_run_id", run_id).execute()

        mark_analysis_run(run_id, status="published")
        return inserted
    except Exception as exc:
        logger.error("[DraftAnalysisRuns] Publish failed run_id=%s: %s", run_id, safe_exception(exc))
        try:
            for table in ARTIFACT_TABLES:
                if table == "draft_analysis" and draft_analysis_upserted and previous_draft_analysis:
                    restore_res = (
                        supabase.table("draft_analysis")
                        .update(previous_draft_analysis)
                        .eq("draft_id", draft_id)
                        .execute()
                    )
                    if not restore_res.data:
                        supabase.table("draft_analysis").insert(previous_draft_analysis).execute()
                    continue
                supabase.table(table).delete().eq("analysis_run_id", run_id).execute()
                if table in replaced_legacy_tables and previous_legacy_rows.get(table):
                    supabase.table(table).insert(previous_legacy_rows[table]).execute()
            mark_analysis_run(run_id, status="failed", failure_reason=f"Publish failed: {safe_exception(exc)}")
        except Exception as cleanup_exc:
            logger.warning("[DraftAnalysisRuns] Publish cleanup failed: %s", safe_exception(cleanup_exc))
        raise


def active_run_filter(query, active_run_id: str | None):
    """Apply the active-run visibility filter to a Supabase query builder."""
    if active_run_id:
        return query.eq("analysis_run_id", active_run_id).eq("is_published", True)
    return query.eq("is_published", True)


def assert_active_run_rows(
    *,
    table: str,
    draft_id: str,
    active_run_id: str | None,
    rows: list[dict[str, Any]] | None,
    require_active_run: bool = True,
) -> None:
    """Fail closed if an API/export payload contains rows from another run.

    This is deliberately strict for analyzed drafts: once a draft has an active
    run, every analysis artifact shown to a user must belong to that exact run
    and be published.
    """
    rows = rows or []
    if require_active_run and not active_run_id:
        if rows:
            raise ValueError(f"{table} returned rows without an active analysis run")
        return

    for row in rows:
        row_draft_id = row.get("draft_id")
        row_run_id = row.get("analysis_run_id")
        row_published = row.get("is_published")
        if row_draft_id and str(row_draft_id) != str(draft_id):
            raise ValueError(
                f"{table} isolation violation: row draft_id={row_draft_id} expected {draft_id}"
            )
        if active_run_id and str(row_run_id) != str(active_run_id):
            raise ValueError(
                f"{table} isolation violation: row analysis_run_id={row_run_id} expected {active_run_id}"
            )
        if row_published is not True:
            raise ValueError(
                f"{table} isolation violation: row is_published={row_published} expected true"
            )
