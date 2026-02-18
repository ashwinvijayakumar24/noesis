"""
Literature Review Compass API Routes

Provides structural guidance for literature reviews.
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from app.services.literature_compass import generate_compass_guidance
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
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


@router.get("/projects/{project_id}/guidance")
def get_compass_guidance(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get Literature Review Compass guidance.

    Prerequisites:
    - Project must have analyzed insights
    - At least 2 documents recommended

    Returns guidance for structuring a literature review (NO PROSE).

    Returns:
        Dictionary containing:
        - structure_recommendations: List of scored organizational approaches
        - synthesis_questions: Critical thinking questions with rich metadata
          (difficulty, confidence, sources, actionable flag)
        - positioning_prompts: Prompts for positioning research
        - structure_guidance: List of guidance items with type, priority, source_data
          (NEW: uses template variations to avoid repetition)
    """

    # 1. Get project with insights and verify ownership
    project_response = supabase.table("projects") \
        .select("insights, insights_status") \
        .eq("id", project_id) \
        .eq("user_id", user_id) \
        .execute()

    if not project_response.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Check insights status
    project = project_response.data[0]
    insights_status = project.get('insights_status', 'not_analyzed')
    insights = project.get('insights')

    if insights_status != 'analyzed' or not insights:
        raise HTTPException(
            status_code=400,
            detail="Project insights must be analyzed first. Go to Insights tab and click 'Analyze Project Insights'."
        )

    # 3. Get documents
    docs_response = supabase.table("documents") \
        .select("*") \
        .eq("project_id", project_id) \
        .eq("user_id", user_id) \
        .execute()

    documents = docs_response.data or []

    if len(documents) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need at least 2 analyzed documents for compass guidance. Upload more documents and analyze them first."
        )

    # 4. Generate guidance
    try:
        guidance = generate_compass_guidance(insights, documents)
        return guidance
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate guidance: {str(e)}"
        )
