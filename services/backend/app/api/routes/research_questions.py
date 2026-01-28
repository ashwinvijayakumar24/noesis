"""
Research Questions API Endpoints

Provides endpoints for generating and managing research questions.
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
from pydantic import BaseModel
from typing import Optional, List
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


class UpdateQuestionRequest(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None


@router.post("/projects/{project_id}/generate")
def generate_research_questions(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Generate research questions for a project based on its insights.

    Requirements:
    - Project must have insights analyzed
    - Insights must contain research gaps

    This endpoint:
    1. Fetches project insights
    2. Uses GPT-4 to generate research questions
    3. Stores questions in database
    4. Returns generated questions
    """
    print(f"[RQ-API] Generating research questions for project_id={project_id}")

    # 1. Verify project belongs to user and has insights
    project_res = supabase.table("projects").select("*")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]

    # Check if insights exist
    if not project.get('insights') or project.get('insights_status') != 'analyzed':
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Project insights must be analyzed before generating research questions",
                "insights_status": project.get('insights_status', 'not_analyzed')
            }
        )

    insights = project['insights']

    # Check if there are research gaps
    if not insights.get('research_gaps') or len(insights.get('research_gaps', [])) == 0:
        raise HTTPException(
            status_code=400,
            detail="Project insights must contain research gaps to generate questions"
        )

    # 2. Generate research questions using GPT-4
    try:
        from app.services.research_questions import generate_research_questions

        questions = generate_research_questions(insights)

        print(f"[RQ-API] Generated {len(questions)} research questions")

        # 3. Store questions in database
        stored_questions = []
        for q in questions:
            # Insert into database
            insert_res = supabase.table("research_questions").insert({
                "project_id": project_id,
                "user_id": user_id,
                "question": q['question'],
                "rationale": q['rationale'],
                "suggested_methodology": q['suggested_methodology'],
                "gap_category": q['gap_category'],
                "status": "new"
            }).execute()

            if insert_res.data:
                stored_questions.append(insert_res.data[0])

        print(f"[RQ-API] Stored {len(stored_questions)} questions in database")

        return {
            "success": True,
            "questions": stored_questions,
            "count": len(stored_questions)
        }

    except Exception as e:
        print(f"[RQ-API] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate research questions: {str(e)}")


@router.get("/projects/{project_id}/questions")
def get_research_questions(
    project_id: str,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Get all research questions for a project.

    Optional filter by status: new, exploring, answered
    """
    print(f"[RQ-API] Fetching research questions for project_id={project_id}, status={status}")

    # Verify project belongs to user
    project_res = supabase.table("projects").select("id")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Fetch questions
    query = supabase.table("research_questions").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)

    if status:
        query = query.eq("status", status)

    questions_res = query.execute()

    return {
        "questions": questions_res.data or [],
        "count": len(questions_res.data) if questions_res.data else 0
    }


@router.patch("/questions/{question_id}")
def update_research_question(
    question_id: str,
    request: UpdateQuestionRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Update a research question's status or notes.

    Allowed status values: new, exploring, answered
    """
    print(f"[RQ-API] Updating question_id={question_id}")

    # Verify question belongs to user
    question_res = supabase.table("research_questions").select("*")\
        .eq("id", question_id)\
        .eq("user_id", user_id)\
        .execute()

    if not question_res.data:
        raise HTTPException(status_code=404, detail="Research question not found")

    # Build update data
    update_data = {}
    if request.status is not None:
        # Validate status
        valid_statuses = ['new', 'exploring', 'answered']
        if request.status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )
        update_data['status'] = request.status

    if request.notes is not None:
        update_data['notes'] = request.notes

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update question
    update_res = supabase.table("research_questions").update(update_data)\
        .eq("id", question_id)\
        .execute()

    if not update_res.data:
        raise HTTPException(status_code=500, detail="Failed to update question")

    return {
        "success": True,
        "question": update_res.data[0]
    }


@router.delete("/questions/{question_id}")
def delete_research_question(
    question_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a research question.
    """
    print(f"[RQ-API] Deleting question_id={question_id}")

    # Verify question belongs to user
    question_res = supabase.table("research_questions").select("id")\
        .eq("id", question_id)\
        .eq("user_id", user_id)\
        .execute()

    if not question_res.data:
        raise HTTPException(status_code=404, detail="Research question not found")

    # Delete question
    supabase.table("research_questions").delete()\
        .eq("id", question_id)\
        .execute()

    return {
        "success": True,
        "message": "Research question deleted"
    }


@router.delete("/projects/{project_id}/questions")
def delete_all_research_questions(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete all research questions for a project.
    """
    print(f"[RQ-API] Deleting all questions for project_id={project_id}")

    # Verify project belongs to user
    project_res = supabase.table("projects").select("id")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete all questions for this project
    supabase.table("research_questions").delete()\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    return {
        "success": True,
        "message": "All research questions deleted"
    }
