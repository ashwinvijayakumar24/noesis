"""
Paper Recommendations API Endpoints

Provides endpoints for discovering and managing paper recommendations from external sources.
"""

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


@router.post("/projects/{project_id}/generate")
def generate_paper_recommendations(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Generate paper recommendations for a project.

    Queries multiple sources (Semantic Scholar, arXiv, PubMed) and returns
    relevant papers based on project themes, insights, and research questions.
    """
    print(f"[PAPER-REC-API] Generating recommendations for project_id={project_id}")

    # 1. Verify project belongs to user
    project_res = supabase.table("projects").select("*")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]

    # 2. Get insights if available
    insights = project.get("insights")

    # 3. Get research questions if available
    questions_res = supabase.table("research_questions").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .limit(10)\
        .execute()

    research_questions = questions_res.data if questions_res.data else []

    # 4. Build project data
    project_data = {
        "title": project.get("title"),
        "description": project.get("description")
    }

    # 5. Generate recommendations
    try:
        from app.services.paper_recommendations import generate_paper_recommendations

        papers = generate_paper_recommendations(
            project_data=project_data,
            insights=insights,
            research_questions=research_questions,
            limit=20
        )

        print(f"[PAPER-REC-API] Generated {len(papers)} recommendations")

        # 6. Store recommendations in database (replace existing)
        # First, delete old recommendations
        supabase.table("paper_recommendations").delete()\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        # Insert new recommendations
        stored_recommendations = []
        for paper in papers:
            insert_data = {
                "project_id": project_id,
                "user_id": user_id,
                **paper,
                "status": "new"
            }

            insert_res = supabase.table("paper_recommendations").insert(insert_data).execute()
            if insert_res.data:
                stored_recommendations.append(insert_res.data[0])

        print(f"[PAPER-REC-API] Stored {len(stored_recommendations)} recommendations")

        return {
            "success": True,
            "count": len(stored_recommendations),
            "recommendations": stored_recommendations
        }

    except Exception as e:
        print(f"[PAPER-REC-API] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate recommendations: {str(e)}")


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
