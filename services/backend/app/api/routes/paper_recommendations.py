"""
Paper Recommendations API Endpoints

Provides endpoints for discovering and managing paper recommendations from external sources.
"""

import logging
import os
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from pydantic import BaseModel

from app.core.security_middleware import SecureAuthValidator
from app.core.supabase_client import supabase

router = APIRouter()
logger = logging.getLogger(__name__)


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"  # Don't expose environment details
        )

    # Use secure token validator
    token = SecureAuthValidator.validate_bearer_token(authorization)

    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


def _get_redis_client():
    import redis as redis_lib
    return redis_lib.Redis(
        host=os.getenv('REDIS_HOST', 'redis'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=int(os.getenv('REDIS_DB', 0)),
        decode_responses=True
    )

DAILY_DISCOVER_LIMITS = {
    "free": 5,
    "pro": 50,
    "team": 9999,
    "enterprise": 9999,
    "admin": 9999,
}
DISCOVER_POOL_MAX = 30
DISCOVER_BATCH_SIZE = 30


def _get_plan_tier_value(value: Optional[str]) -> str:
    return (value or "free").lower()


async def _get_user_plan_tier(user_id: str) -> str:
    from app.services.quota_management import get_user_quota_info

    try:
        quota_info = await get_user_quota_info(user_id)
        return _get_plan_tier_value(quota_info.get("plan_tier"))
    except Exception as exc:
        logger.warning(f"[PAPER-REC-API] Failed to load plan tier, defaulting to free: {exc}")
        return "free"


def _get_discover_quota(user_id: str, plan_tier: str) -> dict[str, Any]:
    normalized_plan = _get_plan_tier_value(plan_tier)
    limit = DAILY_DISCOVER_LIMITS.get(normalized_plan, DAILY_DISCOVER_LIMITS["free"])
    today = date.today().isoformat()
    key = f"daily_discover_actions:{user_id}:{today}"
    try:
        r = _get_redis_client()
        actions_used = int(r.get(key) or 0)
    except Exception as exc:
        logger.warning(f"[PAPER-REC-API] Discover quota read failed (fail open): {exc}")
        actions_used = 0

    return {
        "actions_used": actions_used,
        "actions_limit": limit,
        "remaining": max(limit - actions_used, 0),
    }


def _check_discover_quota(user_id: str, plan_tier: str) -> dict[str, Any]:
    """Check quota and raise 429 if exceeded. Does NOT increment."""
    quota = _get_discover_quota(user_id, plan_tier)
    if quota["actions_used"] >= quota["actions_limit"]:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "quota_type": "discover_actions",
                "used": quota["actions_used"],
                "limit": quota["actions_limit"],
                "remaining": quota["remaining"],
                "message": f"Free plan includes {quota['actions_limit']} Discover actions per day.",
            },
        )
    return quota


def _increment_discover_quota(user_id: str, quota: dict[str, Any]) -> dict[str, Any]:
    """Increment quota after successful paper generation."""
    key = f"daily_discover_actions:{user_id}:{date.today().isoformat()}"
    try:
        pipe = _get_redis_client().pipeline()
        pipe.incr(key)
        pipe.expire(key, 90000)
        pipe.execute()
        quota["actions_used"] += 1
        quota["remaining"] = max(quota["actions_limit"] - quota["actions_used"], 0)
    except Exception as exc:
        logger.warning(f"[PAPER-REC-API] Discover quota increment failed (fail open): {exc}")
    return quota


def _check_and_increment_discover_quota(
    user_id: str,
    plan_tier: str,
    redis_client=None,
) -> dict[str, Any]:
    """Legacy combined check+increment — kept for internal callers."""
    quota = _check_discover_quota(user_id, plan_tier)
    return _increment_discover_quota(user_id, quota)


def _apply_recommendation_pool_cap(project_id: str, user_id: str) -> int:
    existing_res = supabase.table("paper_recommendations").select("id, created_at")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("created_at", desc=False)\
        .execute()

    existing_count = len(existing_res.data) if existing_res.data else 0

    if existing_count + DISCOVER_BATCH_SIZE > DISCOVER_POOL_MAX:
        delete_count = (existing_count + DISCOVER_BATCH_SIZE) - DISCOVER_POOL_MAX
        oldest_ids = [r["id"] for r in (existing_res.data or [])[:delete_count]]
        if oldest_ids:
            for oid in oldest_ids:
                supabase.table("paper_recommendations").delete().eq("id", oid).execute()
            print(f"[PAPER-REC-API] Deleted {len(oldest_ids)} oldest recs to make room")

    return existing_count


def _calculate_post_insert_total(existing_count: int, inserted_count: int) -> int:
    deleted_count = min(existing_count, max(0, existing_count + DISCOVER_BATCH_SIZE - DISCOVER_POOL_MAX))
    return existing_count - deleted_count + inserted_count


def _build_quota_status(project_id: str, user_id: str, plan_tier: str) -> dict[str, Any]:
    quota = _get_discover_quota(user_id, plan_tier)
    total_res = supabase.table("paper_recommendations").select("id", count="exact")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()
    total_held = total_res.count if total_res.count is not None else 0
    return {
        "actions_used": quota["actions_used"],
        "actions_limit": quota["actions_limit"],
        "total_held": total_held,
        "max_pool": DISCOVER_POOL_MAX,
    }


def _generate_and_store_recommendations(
    *,
    project_id: str,
    user_id: str,
    discovery_type: str,
    search_query: Optional[str],
) -> dict[str, Any]:
    existing_count = _apply_recommendation_pool_cap(project_id, user_id)

    if discovery_type == "recommended":
        project_res = supabase.table("projects").select("*")\
            .eq("id", project_id)\
            .eq("user_id", user_id)\
            .execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        project = project_res.data[0]
        insights = project.get("insights")
        questions_res = supabase.table("research_questions").select("*")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .limit(10)\
            .execute()

        from app.services.paper_recommendations import generate_paper_recommendations as svc_generate

        papers = svc_generate(
            project_data={
                "title": project.get("title"),
                "description": project.get("description"),
            },
            insights=insights,
            research_questions=questions_res.data or [],
            limit=DISCOVER_BATCH_SIZE,
        )
    else:
        if not search_query:
            raise HTTPException(status_code=400, detail="Search query is required")

        project_res = supabase.table("projects").select("id")\
            .eq("id", project_id)\
            .eq("user_id", user_id)\
            .execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        from app.services.paper_recommendations import search_papers_by_query

        papers = search_papers_by_query(query=search_query, limit=DISCOVER_BATCH_SIZE)

        existing_full_res = supabase.table("paper_recommendations").select("doi, arxiv_id, title")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()
        existing_keys = set()
        for rec in (existing_full_res.data or []):
            if rec.get("doi"):
                existing_keys.add(f"doi:{rec['doi']}")
            elif rec.get("arxiv_id"):
                existing_keys.add(f"arxiv:{rec['arxiv_id']}")
            elif rec.get("title"):
                existing_keys.add(f"title:{rec['title'].lower().strip()}")

        deduped_papers = []
        for paper in papers:
            key = None
            if paper.get("doi"):
                key = f"doi:{paper['doi']}"
            elif paper.get("arxiv_id"):
                key = f"arxiv:{paper['arxiv_id']}"
            elif paper.get("title"):
                key = f"title:{paper['title'].lower().strip()}"

            if key and key not in existing_keys:
                deduped_papers.append(paper)
                existing_keys.add(key)
        papers = deduped_papers

    MIN_RELEVANCE = 0.45 if discovery_type == "recommended" else 0.3
    stored_recommendations = []
    for paper in papers:
        if paper.get("relevance_score", 0) < MIN_RELEVANCE:
            print(f"[PAPER-REC-API] Skipping low-relevance paper (score={paper.get('relevance_score', 0):.2f}): {paper.get('title', '')[:60]}")
            continue
        insert_data = {
            "project_id": project_id,
            "user_id": user_id,
            "discovery_type": discovery_type,
            "search_query": search_query,
            "bib_saved": False,
            "status": "new",
            **paper,
        }
        insert_res = supabase.table("paper_recommendations").insert(insert_data).execute()
        if insert_res.data:
            stored_recommendations.append(insert_res.data[0])

    return {
        "success": True,
        "count": len(stored_recommendations),
        "recommendations": stored_recommendations,
        "total_held": _calculate_post_insert_total(existing_count, len(stored_recommendations)),
    }


@router.post("/projects/{project_id}/generate")
async def generate_paper_recommendations(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Generate paper recommendations for a project (Find Papers button).
    Rate limited via unified discover actions.
    Maintains a rolling pool of max 30 papers.
    """
    print(f"[PAPER-REC-API] Generating recommendations for project_id={project_id}")

    plan_tier = await _get_user_plan_tier(user_id)
    quota = _check_discover_quota(user_id, plan_tier)

    try:
        from fastapi.concurrency import run_in_threadpool

        result = await run_in_threadpool(
            lambda: _generate_and_store_recommendations(
                project_id=project_id,
                user_id=user_id,
                discovery_type="recommended",
                search_query=None,
            )
        )
        if result.get("count", 0) > 0:
            quota = _increment_discover_quota(user_id, quota)
        result["quota"] = quota
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PAPER-REC-API] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


class PaperSearchRequest(BaseModel):
    query: str


@router.post("/projects/{project_id}/search")
async def search_paper_recommendations(
    project_id: str,
    body: PaperSearchRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Search for papers by query string.
    Rate limited via unified discover actions.
    Maintains rolling pool of max 30 papers.
    """
    print(f"[PAPER-REC-API] Searching for '{body.query}' in project_id={project_id}")

    plan_tier = await _get_user_plan_tier(user_id)
    quota = _check_discover_quota(user_id, plan_tier)

    try:
        from fastapi.concurrency import run_in_threadpool

        result = await run_in_threadpool(
            lambda: _generate_and_store_recommendations(
                project_id=project_id,
                user_id=user_id,
                discovery_type="searched",
                search_query=body.query,
            )
        )
        if result.get("count", 0) > 0:
            quota = _increment_discover_quota(user_id, quota)
        result["quota"] = quota
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PAPER-REC-API] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/projects/{project_id}")
def get_paper_recommendations(
    project_id: str,
    status: Optional[str] = None,
    limit: int = Query(default=5, ge=1, le=30),
    offset: int = Query(0, ge=0),
    user_id: str = Depends(get_current_user)
):
    """
    Get paper recommendations for a project.

    Optional filter by status: new, added, dismissed
    """
    print(f"[PAPER-REC-API] Fetching recommendations for project_id={project_id}")

    # Verify project belongs to user
    project_res = supabase.table("projects").select("id")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch recommendations
    query = supabase.table("paper_recommendations").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("relevance_score", desc=True)

    if status:
        query = query.eq("status", status)

    total_new_res = supabase.table("paper_recommendations").select("id", count="exact")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .eq("status", "new")\
        .execute()

    recommendations_res = query.range(offset, offset + limit - 1).execute()

    return {
        "papers": recommendations_res.data or [],
        "total_new": total_new_res.count if total_new_res.count is not None else 0
    }


@router.get("/projects/{project_id}/quota-status")
def get_discover_quota_status(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """Return current daily quota usage for the discover tab."""
    plan_tier = "free"
    try:
        quota_res = supabase.table("user_quotas").select("plan_tier")\
            .eq("user_id", user_id)\
            .limit(1)\
            .execute()
        if quota_res.data:
            plan_tier = _get_plan_tier_value(quota_res.data[0].get("plan_tier"))
    except Exception as exc:
        logger.warning(f"[PAPER-REC-API] Failed to load plan tier for quota status: {exc}")

    return _build_quota_status(project_id, user_id, plan_tier)


@router.post("/projects/{project_id}/save-discovered/{recommendation_id}")
async def save_discovered_paper(
    project_id: str,
    recommendation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Save a discovered paper to the project's Literature tab.

    Flow:
    1. Fetch the recommendation and verify ownership
    2. Check monthly document quota via quota_management
    3. Insert document record with source_type='discovered', resolution_status='resolving'
    4. Submit resolve_bibtex_task to Celery
    5. Mark bib_saved=TRUE on recommendation
    6. Increment monthly document quota
    """
    from app.services.quota_management import check_quota, increment_quota_usage, QuotaExceededError

    print(f"[PAPER-REC-API] Saving discovered paper rec_id={recommendation_id} to project={project_id}")

    # 1. Fetch recommendation and verify ownership
    rec_res = supabase.table("paper_recommendations").select("*")\
        .eq("id", recommendation_id)\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not rec_res.data:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    rec = rec_res.data[0]

    if rec.get("bib_saved"):
        raise HTTPException(status_code=409, detail="Paper already saved to Literature")

    # 2. Check monthly document quota (discovered papers are fully processed like uploads)
    try:
        await check_quota(user_id, "document")
    except QuotaExceededError as e:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly document quota reached ({e.limit}/month). Upgrade to Pro for more."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[PAPER-REC-API] Monthly quota check failed (fail open): {e}")

    # 4. Build document metadata from recommendation
    doc_metadata = {
        "doi": rec.get("doi"),
        "arxiv_id": rec.get("arxiv_id"),
        "pubmed_id": rec.get("pubmed_id"),
        "authors": rec.get("authors") or [],
        "year": rec.get("year"),
        "abstract": rec.get("abstract"),
        "journal": rec.get("journal_name"),
        "pdf_url": rec.get("pdf_url"),
        "paper_url": rec.get("paper_url"),
        "citation_count": rec.get("citation_count"),
        "source": rec.get("source"),
        "fields_of_study": rec.get("fields_of_study") or [],
        "from_discover": True,
        "recommendation_id": recommendation_id,
    }

    # 5. Insert document record (bypass file upload)
    doc_insert = {
        "user_id": user_id,
        "project_id": project_id,
        "title": rec.get("title") or "Untitled Paper",
        "file_url": "",          # Required NOT NULL; no physical file for discovered papers
        "file_type": "discovered",
        "status": "imported",
        "source_type": "discovered",
        "resolution_status": "resolving",
        "metadata": doc_metadata,
    }

    doc_res = supabase.table("documents").insert(doc_insert).execute()

    if not doc_res.data:
        raise HTTPException(status_code=500, detail="Failed to create document record")

    document_id = doc_res.data[0]["id"]
    print(f"[PAPER-REC-API] Created document record doc_id={document_id}")

    # 6. Submit BibTeX resolution Celery task
    try:
        from app.tasks.bibtex_resolution_task import resolve_bibtex_task
        resolve_bibtex_task.delay([document_id], user_id, project_id)
        print(f"[PAPER-REC-API] Submitted resolve_bibtex_task for doc_id={document_id}")
    except Exception as e:
        logger.error(f"[PAPER-REC-API] Failed to submit bibtex resolution task: {e}")

    # 7. Mark bib_saved=TRUE on recommendation
    supabase.table("paper_recommendations").update({"bib_saved": True})\
        .eq("id", recommendation_id)\
        .execute()

    # 8. Increment monthly document quota
    try:
        await increment_quota_usage(user_id, "document")
    except Exception as e:
        logger.warning(f"[PAPER-REC-API] Monthly quota increment failed: {e}")

    # 9. Populate shared cache best-effort so future users hit shared_papers first
    try:
        from app.services.shared_paper_cache import get_or_fetch_paper

        await get_or_fetch_paper(
            doi=rec.get("doi"),
            arxiv_id=rec.get("arxiv_id"),
            title=rec.get("title"),
        )
    except Exception as cache_exc:
        logger.warning(f"[PAPER-REC-API] Shared cache populate failed (non-fatal): {cache_exc}")

    return {
        "success": True,
        "document_id": document_id,
        "resolution_started": True,
        "message": "Paper saved to Literature. AI analysis will start shortly."
    }


@router.patch("/{recommendation_id}/status")
def update_recommendation_status(
    recommendation_id: str,
    status: str,
    user_id: str = Depends(get_current_user)
):
    """
    Update recommendation status (new, added, dismissed).
    """
    print(f"[PAPER-REC-API] Updating recommendation {recommendation_id} to status={status}")

    # Validate status
    valid_statuses = ["new", "added", "dismissed"]
    if status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )

    # Verify recommendation belongs to user
    rec_res = supabase.table("paper_recommendations").select("*")\
        .eq("id", recommendation_id)\
        .eq("user_id", user_id)\
        .execute()

    if not rec_res.data:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Update status
    update_res = supabase.table("paper_recommendations").update({"status": status})\
        .eq("id", recommendation_id)\
        .execute()

    if not update_res.data:
        raise HTTPException(status_code=500, detail="Failed to update status")

    return {
        "success": True,
        "recommendation": update_res.data[0]
    }


@router.delete("/{recommendation_id}")
def delete_recommendation(
    recommendation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a paper recommendation.
    """
    print(f"[PAPER-REC-API] Deleting recommendation_id={recommendation_id}")

    # Verify recommendation belongs to user
    rec_res = supabase.table("paper_recommendations").select("id")\
        .eq("id", recommendation_id)\
        .eq("user_id", user_id)\
        .execute()

    if not rec_res.data:
        raise HTTPException(status_code=404, detail="Recommendation not found")

    # Delete
    supabase.table("paper_recommendations").delete()\
        .eq("id", recommendation_id)\
        .execute()

    return {
        "success": True,
        "message": "Recommendation deleted"
    }
