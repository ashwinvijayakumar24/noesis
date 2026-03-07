"""
API routes for draft comparison
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import Optional, List

from app.services.draft_comparison import compare_drafts
from app.core.supabase_client import get_supabase_client, supabase
from app.core.security_middleware import SecureAuthValidator
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_current_user(authorization: str = Header(None)):
    """Extract and validate user from Authorization header."""
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    token = SecureAuthValidator.validate_bearer_token(authorization)
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")


class ComparisonRequest(BaseModel):
    draft_v1_id: str = Field(..., description="Earlier draft version ID")
    draft_v2_id: str = Field(..., description="Later draft version ID")


@router.post("/projects/{project_id}/compare-drafts")
async def compare_draft_versions(
    project_id: str,
    request: ComparisonRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Compare two draft versions using AI-powered analysis.

    Shows:
    - Claims added/removed/improved/worsened (embedding-based matching)
    - Feedback resolution status per item
    - Coverage gaps resolved
    - Overall improvement score (0-100)
    - GPT-5.2 narrative explaining the evolution
    """
    try:
        db = get_supabase_client()
        project = db.table("projects").select("user_id").eq("id", project_id).execute()

        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Verify both drafts belong to this project
        draft_v1 = db.table("drafts").select("project_id").eq("id", request.draft_v1_id).execute()
        draft_v2 = db.table("drafts").select("project_id").eq("id", request.draft_v2_id).execute()

        if not draft_v1.data or not draft_v2.data:
            raise HTTPException(status_code=404, detail="One or both drafts not found")

        if draft_v1.data[0]["project_id"] != project_id or draft_v2.data[0]["project_id"] != project_id:
            raise HTTPException(status_code=403, detail="Drafts do not belong to this project")

        result = await compare_drafts(
            draft_v1_id=request.draft_v1_id,
            draft_v2_id=request.draft_v2_id,
            project_id=project_id,
            user_id=user_id
        )

        return {
            "comparison_id": result["comparison_id"],
            "improvement_score": result["improvement_score"],
            "summary": result["summary"],
            "narrative": result.get("narrative", {}),
            "claims_added": len(result.get("claims_added", [])),
            "claims_removed": len(result.get("claims_removed", [])),
            "claims_improved": len(result.get("claims_improved", [])),
            "claims_worsened": len(result.get("claims_worsened", [])),
            "feedback_addressed": len(result.get("feedback_addressed", [])),
            "feedback_tracked": result.get("feedback_tracked", []),
            "gaps_resolved": len(result.get("gaps_resolved", []))
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare drafts: {str(e)}")


@router.get("/comparisons/{comparison_id}")
async def get_comparison_details(
    comparison_id: str,
    user_id: str = Depends(get_current_user)
):
    """Get detailed comparison results including AI narrative."""
    try:
        db = get_supabase_client()
        comparison = db.table("draft_comparisons").select("*").eq("id", comparison_id).execute()

        if not comparison.data:
            raise HTTPException(status_code=404, detail="Comparison not found")

        data = comparison.data[0]
        metadata = data.get("metadata") or {}

        return {
            "comparison_id": data["id"],
            "improvement_score": data["improvement_score"],
            "summary": generate_summary_from_data(data),
            "narrative": metadata.get("narrative", {}),
            "detailed_changes": data.get("comparison_result", {}),
            "feedback_tracked": data.get("comparison_result", {}).get("feedback_tracked", []),
            "stats": {
                "claims_added": data.get("claims_added", 0),
                "claims_removed": data.get("claims_removed", 0),
                "claims_improved": data.get("claims_improved", 0),
                "claims_worsened": data.get("claims_worsened", 0),
                "feedback_addressed": data.get("feedback_addressed", 0),
                "gaps_resolved": data.get("gaps_resolved", 0)
            },
            "created_at": data["created_at"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch comparison: {str(e)}")


@router.get("/projects/{project_id}/comparisons")
async def list_project_comparisons(
    project_id: str,
    limit: int = 10,
    user_id: str = Depends(get_current_user)
):
    """List all comparisons for a project."""
    try:
        db = get_supabase_client()
        comparisons = (
            db.table("draft_comparisons")
            .select("*")
            .eq("project_id", project_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

        return {
            "comparisons": [
                {
                    "comparison_id": c["id"],
                    "improvement_score": c["improvement_score"],
                    "claims_added": c.get("claims_added", 0),
                    "claims_improved": c.get("claims_improved", 0),
                    "feedback_addressed": c.get("feedback_addressed", 0),
                    "created_at": c["created_at"],
                    "draft_v1_id": c.get("draft_v1_id"),
                    "draft_v2_id": c.get("draft_v2_id")
                }
                for c in comparisons.data
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch comparisons: {str(e)}")


def generate_summary_from_data(data: dict) -> str:
    """Helper to generate summary from comparison data."""
    score = data.get("improvement_score", 0)
    claims_added = data.get("claims_added", 0)
    claims_improved = data.get("claims_improved", 0)
    feedback_addressed = data.get("feedback_addressed", 0)
    gaps_resolved = data.get("gaps_resolved", 0)

    if score >= 75:
        rating = "Excellent improvement"
    elif score >= 60:
        rating = "Good improvement"
    elif score >= 50:
        rating = "Moderate improvement"
    else:
        rating = "Needs more work"

    changes = []
    if claims_added > 0:
        changes.append(f"{claims_added} new claims")
    if claims_improved > 0:
        changes.append(f"{claims_improved} improvements")
    if feedback_addressed > 0:
        changes.append(f"{feedback_addressed} issues fixed")
    if gaps_resolved > 0:
        changes.append(f"{gaps_resolved} gaps resolved")

    summary = f"{rating} (Score: {score}/100)"
    if changes:
        summary += ". " + ", ".join(changes) + "."

    return summary
