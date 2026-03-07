"""
API routes for user feedback system
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.core.supabase_client import get_supabase_client


router = APIRouter()


class FeedbackCreate(BaseModel):
    feature_type: str = Field(..., description="Feature being reviewed (draft_analysis, chat, etc.)")
    context_id: Optional[str] = Field(None, description="ID of the draft, chat session, etc.")
    rating: Optional[int] = Field(None, ge=1, le=5, description="Rating 1-5")
    feedback_text: Optional[str] = Field(None, description="User's feedback text")
    feedback_category: Optional[str] = Field(None, description="bug, feature_request, positive, etc.")
    metadata: Optional[dict] = Field(default_factory=dict)


class FeedbackResponse(BaseModel):
    id: str
    feature_type: str
    rating: Optional[int]
    feedback_text: Optional[str]
    feedback_category: Optional[str]
    created_at: datetime


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    feedback: FeedbackCreate,
    user_id: str = Depends(lambda: None)  # TODO: Replace with actual auth dependency
):
    """
    Submit user feedback

    Allows users to provide feedback on any feature
    """
    try:
        supabase = get_supabase_client()

        # For now, get user_id from context_id if it's a draft/project
        # TODO: Replace with actual authenticated user_id
        if not user_id:
            # Temporary: try to get user_id from project/draft
            if feedback.context_id:
                if feedback.feature_type == "draft_analysis":
                    draft = supabase.table("drafts").select("user_id").eq("id", feedback.context_id).execute()
                    if draft.data:
                        user_id = draft.data[0]["user_id"]
                elif feedback.feature_type in ["project", "paper_discovery"]:
                    project = supabase.table("projects").select("user_id").eq("id", feedback.context_id).execute()
                    if project.data:
                        user_id = project.data[0]["user_id"]

        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        # Insert feedback
        feedback_data = {
            "user_id": user_id,
            "feature_type": feedback.feature_type,
            "context_id": feedback.context_id,
            "rating": feedback.rating,
            "feedback_text": feedback.feedback_text,
            "feedback_category": feedback.feedback_category,
            "metadata": feedback.metadata
        }

        result = supabase.table("user_feedback").insert(feedback_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to submit feedback")

        return FeedbackResponse(**result.data[0])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit feedback: {str(e)}")


@router.get("/feedback/my", response_model=List[FeedbackResponse])
async def get_my_feedback(
    user_id: str = Depends(lambda: None),  # TODO: Replace with actual auth
    feature_type: Optional[str] = Query(None, description="Filter by feature type"),
    limit: int = Query(50, ge=1, le=200)
):
    """
    Get user's own feedback history
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        supabase = get_supabase_client()

        query = supabase.table("user_feedback").select("*").eq("user_id", user_id)

        if feature_type:
            query = query.eq("feature_type", feature_type)

        result = query.order("created_at", desc=True).limit(limit).execute()

        return [FeedbackResponse(**item) for item in result.data]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch feedback: {str(e)}")


@router.get("/feedback/stats")
async def get_feedback_stats(
    user_id: str = Depends(lambda: None)  # TODO: Admin check
):
    """
    Get feedback statistics (admin only)

    Returns aggregated stats about user feedback
    """
    try:
        supabase = get_supabase_client()

        # Get counts by category
        result = supabase.table("user_feedback").select("*").execute()

        if not result.data:
            return {
                "total_feedback": 0,
                "by_feature": {},
                "by_category": {},
                "average_rating": 0,
                "rating_distribution": {}
            }

        feedbacks = result.data

        # Calculate stats
        by_feature = {}
        by_category = {}
        rating_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        total_ratings = 0
        sum_ratings = 0

        for fb in feedbacks:
            feature = fb.get("feature_type", "unknown")
            category = fb.get("feedback_category", "uncategorized")
            rating = fb.get("rating")

            by_feature[feature] = by_feature.get(feature, 0) + 1
            by_category[category] = by_category.get(category, 0) + 1

            if rating:
                rating_distribution[rating] = rating_distribution.get(rating, 0) + 1
                total_ratings += 1
                sum_ratings += rating

        avg_rating = round(sum_ratings / total_ratings, 2) if total_ratings > 0 else 0

        return {
            "total_feedback": len(feedbacks),
            "by_feature": by_feature,
            "by_category": by_category,
            "average_rating": avg_rating,
            "rating_distribution": rating_distribution
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")
