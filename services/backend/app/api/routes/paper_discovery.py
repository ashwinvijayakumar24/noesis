"""
API routes for paper discovery
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional
import logging
import os
from datetime import date

from app.core.supabase_client import get_supabase_client
from app.core.security_middleware import SecureAuthValidator
from app.services.paper_discovery_agent import discover_papers


router = APIRouter()
logger = logging.getLogger(__name__)

DAILY_DISCOVERY_LIMITS = {
    'free': 3,
    'pro': 999,
    'team': 999,
    'enterprise': 9999,
}


def _check_discovery_quota(user_id: str, plan_tier: str = 'free') -> None:
    """Raise HTTPException if user has exceeded daily paper discovery limit."""
    daily_limit = DAILY_DISCOVERY_LIMITS.get(plan_tier, DAILY_DISCOVERY_LIMITS['free'])
    if daily_limit >= 999:
        return  # unlimited

    try:
        import redis as redis_lib
        r = redis_lib.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0)),
            decode_responses=True
        )
        today = date.today().isoformat()
        key = f"daily_discovery:{user_id}:{today}"
        count = int(r.get(key) or 0)
        if count >= daily_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Daily paper discovery limit reached ({daily_limit} searches/day on free plan). Upgrade to Pro for unlimited searches."
            )
        # Increment with 25h TTL
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, 90000)
        pipe.execute()
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[DISCOVERY-QUOTA] Redis check failed (fail open): {e}")


def get_current_user(authorization: str = Header(None)):
    supabase = get_supabase_client()
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    token = SecureAuthValidator.validate_bearer_token(authorization)

    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class PaperDiscoveryRequest(BaseModel):
    query: str = Field(..., description="Search query for discovering papers")
    max_papers: int = Field(10, ge=1, le=10, description="Maximum number of papers to discover")


class PaperDiscoveryResponse(BaseModel):
    success: bool
    papers_found: int
    papers_with_pdf: int
    papers_added: int
    errors: list[str]
    message: str


@router.post("/projects/{project_id}/discover-papers", response_model=PaperDiscoveryResponse)
async def discover_papers_endpoint(
    project_id: str,
    request: PaperDiscoveryRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Discover and automatically add papers to a project

    Searches across:
    - PubMed
    - arXiv
    - Semantic Scholar

    Then:
    - Finds free full-text PDFs
    - Downloads them
    - Processes with GROBID
    - Adds to project
    """
    try:
        supabase = get_supabase_client()

        # Verify project exists and user has access
        project = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()

        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Check daily quota (free tier: 3 searches/day)
        quota_res = supabase.table("user_quotas").select("plan_tier").eq("user_id", user_id).execute()
        plan_tier = quota_res.data[0].get("plan_tier", "free") if quota_res.data else "free"
        _check_discovery_quota(user_id, plan_tier)

        # Run discovery workflow
        result = await discover_papers(
            query=request.query,
            project_id=project_id,
            user_id=user_id,
            max_papers=request.max_papers
        )

        message = f"Successfully discovered {result['papers_found']} papers, "
        message += f"added {result['papers_added']} to your project"

        if result['errors']:
            message += f" (with {len(result['errors'])} errors)"

        return PaperDiscoveryResponse(
            success=result['success'],
            papers_found=result['papers_found'],
            papers_with_pdf=result['papers_with_pdf'],
            papers_added=result['papers_added'],
            errors=result['errors'],
            message=message
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Paper discovery failed: {str(e)}")


@router.get("/projects/{project_id}/discovery-sources")
async def get_discovery_sources():
    """
    Get available paper discovery sources and their status
    """
    return {
        "sources": [
            {
                "name": "PubMed",
                "description": "Biomedical and life sciences literature",
                "coverage": "30M+ papers",
                "status": "active"
            },
            {
                "name": "arXiv",
                "description": "Physics, mathematics, computer science preprints",
                "coverage": "2M+ papers",
                "status": "active"
            },
            {
                "name": "Semantic Scholar",
                "description": "Multi-disciplinary academic search",
                "coverage": "200M+ papers",
                "status": "active"
            }
        ]
    }
