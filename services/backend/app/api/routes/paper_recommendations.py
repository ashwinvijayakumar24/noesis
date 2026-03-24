"""
Paper Recommendations API Endpoints

Provides endpoints for discovering and managing paper recommendations from external sources.
"""

import os
from datetime import date
from fastapi import APIRouter, HTTPException, Depends, Header
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
from pydantic import BaseModel
from typing import Optional
import logging

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
        logger.error(f"Token validation failed: {str(e)}")
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

def _check_and_increment_daily_quota(user_id: str, redis_key_prefix: str, daily_limit: int) -> int:
    """Check daily quota and increment. Returns current count after increment.
    Raises HTTPException 429 if limit reached."""
    today = date.today().isoformat()
    key = f"{redis_key_prefix}:{user_id}:{today}"
    try:
        r = _get_redis_client()
        count = int(r.get(key) or 0)
        if count >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily limit reached ({daily_limit}/day). Resets tomorrow."
            )
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 90000)  # 25 hours
        pipe.execute()
        return count + 1
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Redis quota check failed (fail open): {e}")
        return 1  # fail open

def _get_daily_quota_count(user_id: str, redis_key_prefix: str) -> int:
    """Get current daily usage count without incrementing."""
    today = date.today().isoformat()
    key = f"{redis_key_prefix}:{user_id}:{today}"
    try:
        r = _get_redis_client()
        return int(r.get(key) or 0)
    except Exception:
        return 0


@router.post("/projects/{project_id}/generate")
async def generate_paper_recommendations(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Generate paper recommendations for a project (Find Papers button).
    Rate limited: tier-based (free=1/day, pro/team=unlimited).
    Maintains a rolling pool of max 20 papers; deletes oldest 5 if cap exceeded.
    """
    print(f"[PAPER-REC-API] Generating recommendations for project_id={project_id}")

    # 1. Check daily quota: tier-based limits
    from app.services.quota_management import get_user_quota_info
    REFRESH_LIMITS = {'free': 1, 'pro': 999, 'team': 999, 'enterprise': 9999}
    try:
        quota_info = await get_user_quota_info(user_id)
        plan_tier = quota_info.get('plan_tier', 'free')
    except Exception:
        plan_tier = 'free'
    daily_limit = REFRESH_LIMITS.get(plan_tier, 1)
    _check_and_increment_daily_quota(user_id, "daily_discover_refresh", daily_limit=daily_limit)

    # 2. Verify project belongs to user
    project_res = supabase.table("projects").select("*")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]

    # 3. Count existing recs; hard-delete oldest if cap would be exceeded
    existing_res = supabase.table("paper_recommendations").select("id, created_at")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("created_at", desc=False)\
        .execute()

    existing_count = len(existing_res.data) if existing_res.data else 0
    MAX_POOL = 20
    BATCH_SIZE = 5

    if existing_count + BATCH_SIZE > MAX_POOL:
        delete_count = (existing_count + BATCH_SIZE) - MAX_POOL
        oldest_ids = [r["id"] for r in (existing_res.data or [])[:delete_count]]
        if oldest_ids:
            for oid in oldest_ids:
                supabase.table("paper_recommendations").delete().eq("id", oid).execute()
            print(f"[PAPER-REC-API] Deleted {len(oldest_ids)} oldest recs to make room")

    # 4. Build project data + insights + research questions
    insights = project.get("insights")

    questions_res = supabase.table("research_questions").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .limit(10)\
        .execute()

    research_questions = questions_res.data if questions_res.data else []

    project_data = {
        "title": project.get("title"),
        "description": project.get("description")
    }

    # 5. Generate recommendations (limit=5)
    try:
        from app.services.paper_recommendations import generate_paper_recommendations as svc_generate
        from fastapi.concurrency import run_in_threadpool

        papers = await run_in_threadpool(
            lambda: svc_generate(
                project_data=project_data,
                insights=insights,
                research_questions=research_questions,
                limit=BATCH_SIZE
            )
        )

        print(f"[PAPER-REC-API] Generated {len(papers)} recommendations")

        # 6. Insert with discovery_type='recommended'
        stored_recommendations = []
        for paper in papers:
            insert_data = {
                "project_id": project_id,
                "user_id": user_id,
                "discovery_type": "recommended",
                "search_query": None,
                "bib_saved": False,
                "status": "new",
                **paper,
            }
            insert_res = supabase.table("paper_recommendations").insert(insert_data).execute()
            if insert_res.data:
                stored_recommendations.append(insert_res.data[0])

        print(f"[PAPER-REC-API] Stored {len(stored_recommendations)} recommendations")

        return {
            "success": True,
            "count": len(stored_recommendations),
            "recommendations": stored_recommendations,
            "total_held": existing_count - min(existing_count, max(0, existing_count + BATCH_SIZE - MAX_POOL)) + len(stored_recommendations)
        }

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
    Rate limited: 3x/day per user (reuses daily_discovery quota).
    Maintains rolling pool of max 20 papers; deletes oldest if cap exceeded.
    """
    print(f"[PAPER-REC-API] Searching for '{body.query}' in project_id={project_id}")

    # 1. Check daily search quota: 3x/day
    _check_and_increment_daily_quota(user_id, "daily_discovery", daily_limit=3)

    # 2. Verify project belongs to user
    project_res = supabase.table("projects").select("id")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # 3. Count + hard-delete oldest if cap would be exceeded
    existing_res = supabase.table("paper_recommendations").select("id, created_at")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("created_at", desc=False)\
        .execute()

    existing_count = len(existing_res.data) if existing_res.data else 0
    MAX_POOL = 20
    BATCH_SIZE = 5

    if existing_count + BATCH_SIZE > MAX_POOL:
        delete_count = (existing_count + BATCH_SIZE) - MAX_POOL
        oldest_ids = [r["id"] for r in (existing_res.data or [])[:delete_count]]
        if oldest_ids:
            for oid in oldest_ids:
                supabase.table("paper_recommendations").delete().eq("id", oid).execute()
            print(f"[PAPER-REC-API] Deleted {len(oldest_ids)} oldest recs to make room")

    # 4. Search papers
    try:
        from app.services.paper_recommendations import search_papers_by_query, _deduplicate_papers
        from fastapi.concurrency import run_in_threadpool

        papers = await run_in_threadpool(lambda: search_papers_by_query(query=body.query, limit=BATCH_SIZE))
        print(f"[PAPER-REC-API] Found {len(papers)} papers for query '{body.query}'")

        # Deduplicate against existing recs (by DOI/arxiv_id/title)
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
        for p in papers:
            key = None
            if p.get("doi"):
                key = f"doi:{p['doi']}"
            elif p.get("arxiv_id"):
                key = f"arxiv:{p['arxiv_id']}"
            elif p.get("title"):
                key = f"title:{p['title'].lower().strip()}"
            if key and key not in existing_keys:
                deduped_papers.append(p)
                existing_keys.add(key)

        # 5. Insert with discovery_type='searched'
        stored_recommendations = []
        for paper in deduped_papers:
            insert_data = {
                "project_id": project_id,
                "user_id": user_id,
                "discovery_type": "searched",
                "search_query": body.query,
                "bib_saved": False,
                "status": "new",
                **paper,
            }
            insert_res = supabase.table("paper_recommendations").insert(insert_data).execute()
            if insert_res.data:
                stored_recommendations.append(insert_res.data[0])

        final_total = existing_count - min(existing_count, max(0, existing_count + BATCH_SIZE - MAX_POOL)) + len(stored_recommendations)

        return {
            "success": True,
            "count": len(stored_recommendations),
            "recommendations": stored_recommendations,
            "total_held": final_total
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[PAPER-REC-API] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/projects/{project_id}")
def get_paper_recommendations(
    project_id: str,
    status: Optional[str] = None,
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

    recommendations_res = query.execute()

    return {
        "recommendations": recommendations_res.data or [],
        "count": len(recommendations_res.data) if recommendations_res.data else 0
    }


@router.get("/projects/{project_id}/quota-status")
def get_discover_quota_status(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """Return current daily quota usage for the discover tab."""
    refresh_count = _get_daily_quota_count(user_id, "daily_discover_refresh")
    search_count = _get_daily_quota_count(user_id, "daily_discovery")
    bib_save_count = _get_daily_quota_count(user_id, "daily_bib_save")

    # Count total held
    total_res = supabase.table("paper_recommendations").select("id", count="exact")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    total_held = total_res.count if total_res.count is not None else 0

    return {
        "refresh_used": refresh_count,
        "refresh_limit": 1,
        "search_used": search_count,
        "search_limit": 3,
        "bib_save_used": bib_save_count,
        "bib_save_limit": 3,
        "total_held": total_held,
        "max_pool": 20
    }


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
    2. Check daily bib_save quota (3x/day, Redis key: daily_bib_save:{user_id}:{date})
    3. Check monthly bib_import quota via quota_management
    4. Insert document record with source_type='bibtex_import', resolution_status='resolving'
    5. Submit resolve_bibtex_task to Celery
    6. Mark bib_saved=TRUE on recommendation
    7. Increment quotas
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

    # 2. Check daily bib_save quota (3 saves/day per user)
    today = date.today().isoformat()
    bib_save_key = f"daily_bib_save:{user_id}:{today}"
    try:
        r = _get_redis_client()
        bib_save_count = int(r.get(bib_save_key) or 0)
        if bib_save_count >= 3:
            raise HTTPException(
                status_code=429,
                detail="Daily save limit reached (3 saves/day). Resets tomorrow."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[PAPER-REC-API] Redis bib_save quota check failed (fail open): {e}")
        bib_save_count = 0

    # 3. Check monthly bib_import quota
    try:
        await check_quota(user_id, "bib_import")
    except QuotaExceededError as e:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly BibTeX import quota reached ({e.limit} refs/month). Upgrade to Pro for more."
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
        "file_type": "bibtex_import",
        "status": "imported",
        "source_type": "bibtex_import",
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

    # 8. Increment Redis daily save counter (25h TTL)
    try:
        r = _get_redis_client()
        pipe = r.pipeline()
        pipe.incr(bib_save_key)
        pipe.expire(bib_save_key, 90000)
        pipe.execute()
    except Exception as e:
        logger.warning(f"[PAPER-REC-API] Redis bib_save increment failed: {e}")

    # 9. Increment monthly bib_import quota
    try:
        await increment_quota_usage(user_id, "bib_import")
    except Exception as e:
        logger.warning(f"[PAPER-REC-API] Monthly quota increment failed: {e}")

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
