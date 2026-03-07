"""
Methodology Recommendations API Endpoints

Provides endpoints for generating methodology recommendations for research questions.
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


class MethodologyRequest(BaseModel):
    question_id: Optional[str] = None  # For pre-generated questions
    custom_question: Optional[str] = None  # For user-provided questions
    project_id: str  # Always need project context


@router.post("/generate")
def generate_methodology_recommendations(
    request: MethodologyRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Generate methodology recommendations for a research question.

    Can be used in two ways:
    1. With question_id - Generate for an existing research question
    2. With custom_question - Generate for a user-provided question

    This endpoint:
    1. Fetches project context and insights
    2. Uses GPT-4o to generate detailed methodology recommendations
    3. Stores recommendations in database
    4. Returns comprehensive methodology guidance
    """
    print(f"[METHODOLOGY-API] Generating recommendations for project_id={request.project_id}")

    # Validate that we have either question_id or custom_question
    if not request.question_id and not request.custom_question:
        raise HTTPException(
            status_code=400,
            detail="Must provide either question_id or custom_question"
        )

    # Verify project belongs to user
    project_res = supabase.table("projects").select("*")\
        .eq("id", request.project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]

    # Get the question text
    question_text = None
    research_question_id = None

    if request.question_id:
        # Fetch the research question
        question_res = supabase.table("research_questions").select("*")\
            .eq("id", request.question_id)\
            .eq("user_id", user_id)\
            .execute()

        if not question_res.data:
            raise HTTPException(status_code=404, detail="Research question not found")

        question_text = question_res.data[0]['question']
        research_question_id = request.question_id
        print(f"[METHODOLOGY-API] Using pre-generated question: {question_text[:50]}...")

    else:
        # Use custom question
        question_text = request.custom_question.strip()
        if not question_text:
            raise HTTPException(status_code=400, detail="Custom question cannot be empty")
        print(f"[METHODOLOGY-API] Using custom question: {question_text[:50]}...")

    # Build project context
    project_context = {
        "project_title": project.get('title'),
        "project_description": project.get('description')
    }

    # Get number of documents
    docs_res = supabase.table("documents").select("id")\
        .eq("project_id", request.project_id)\
        .eq("status", "analyzed")\
        .execute()

    project_context['num_papers'] = len(docs_res.data) if docs_res.data else 0

    # Get insights if available
    insights = project.get('insights')
    if insights:
        project_context['common_themes'] = insights.get('common_themes', [])

    # Generate methodology recommendations
    try:
        from app.services.methodology_recommendations import generate_methodology_recommendations

        recommendations = generate_methodology_recommendations(
            question=question_text,
            project_context=project_context,
            insights=insights
        )

        print(f"[METHODOLOGY-API] Generated recommendations: {recommendations['primary_methodology']['name']}")

        # Store in database
        insert_data = {
            "project_id": request.project_id,
            "user_id": user_id,
            "question": question_text,
            "recommendations": recommendations,
            "model": "gpt-5.2-chat-latest"
        }

        if research_question_id:
            insert_data["research_question_id"] = research_question_id

        insert_res = supabase.table("methodology_recommendations").insert(insert_data).execute()

        if not insert_res.data:
            raise HTTPException(status_code=500, detail="Failed to store recommendations")

        stored_recommendation = insert_res.data[0]

        print(f"[METHODOLOGY-API] Stored recommendations with id={stored_recommendation['id']}")

        return {
            "success": True,
            "recommendation_id": stored_recommendation['id'],
            "question": question_text,
            "recommendations": recommendations
        }

    except Exception as e:
        print(f"[METHODOLOGY-API] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate methodology recommendations: {str(e)}")


@router.get("/questions/{question_id}")
def get_methodology_for_question(
    question_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get methodology recommendations for a specific research question.

    Returns the most recent recommendations if they exist.
    """
    print(f"[METHODOLOGY-API] Fetching recommendations for question_id={question_id}")

    # Verify question belongs to user
    question_res = supabase.table("research_questions").select("*")\
        .eq("id", question_id)\
        .eq("user_id", user_id)\
        .execute()

    if not question_res.data:
        raise HTTPException(status_code=404, detail="Research question not found")

    # Fetch recommendations
    recommendations_res = supabase.table("methodology_recommendations").select("*")\
        .eq("research_question_id", question_id)\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()

    if not recommendations_res.data:
        return {
            "has_recommendations": False,
            "question": question_res.data[0]['question']
        }

    return {
        "has_recommendations": True,
        "question": question_res.data[0]['question'],
        "recommendation": recommendations_res.data[0]
    }


@router.get("/projects/{project_id}")
def get_all_methodology_recommendations(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get all methodology recommendations for a project.
    """
    print(f"[METHODOLOGY-API] Fetching all recommendations for project_id={project_id}")

    # Verify project belongs to user
    project_res = supabase.table("projects").select("id")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch all recommendations
    recommendations_res = supabase.table("methodology_recommendations").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .execute()

    return {
        "recommendations": recommendations_res.data or [],
        "count": len(recommendations_res.data) if recommendations_res.data else 0
    }


@router.delete("/{recommendation_id}")
def delete_methodology_recommendation(
    recommendation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a methodology recommendation.
    """
    print(f"[METHODOLOGY-API] Deleting recommendation_id={recommendation_id}")

    # Verify recommendation belongs to user
    recommendation_res = supabase.table("methodology_recommendations").select("id")\
        .eq("id", recommendation_id)\
        .eq("user_id", user_id)\
        .execute()

    if not recommendation_res.data:
        raise HTTPException(status_code=404, detail="Methodology recommendation not found")

    # Delete recommendation
    supabase.table("methodology_recommendations").delete()\
        .eq("id", recommendation_id)\
        .execute()

    return {
        "success": True,
        "message": "Methodology recommendation deleted"
    }
