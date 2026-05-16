from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
import random
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Predefined color palette
TAG_COLORS = [
    "red-500", "orange-500", "yellow-500", "green-500",
    "blue-500", "purple-500", "pink-500", "cyan-500",
    "indigo-500", "rose-500"
]

# Suggested predefined tags
SUGGESTED_TAGS = [
    {"name": "research", "color": "red-500"},
    {"name": "work", "color": "orange-500"},
    {"name": "personal", "color": "yellow-500"},
    {"name": "academic", "color": "green-500"},
    {"name": "archived", "color": "blue-500"},
    {"name": "priority", "color": "purple-500"},
]

# Request models
class AddTagRequest(BaseModel):
    tag_name: str

# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"  # Don't expose environment details
        )

    try:
        return SecureAuthValidator.get_user_id(authorization, supabase)
    except Exception as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )

@router.get("/suggestions")
def get_tag_suggestions(user_id: str = Depends(get_current_user)):
    """
    Get suggested tags (predefined + user's existing unique tags).
    """
    try:
        # Get user's existing tags
        user_tags_response = supabase.table("project_tags").select("tag_name, tag_color")\
            .eq("user_id", user_id)\
            .execute()

        user_tags = user_tags_response.data or []

        # Get unique tags from user
        unique_user_tags = {}
        for tag in user_tags:
            tag_name = tag["tag_name"]
            if tag_name not in unique_user_tags:
                unique_user_tags[tag_name] = tag["tag_color"]

        # Combine with predefined
        all_suggestions = list(SUGGESTED_TAGS)

        # Add user's custom tags
        for tag_name, tag_color in unique_user_tags.items():
            if tag_name not in [t["name"] for t in SUGGESTED_TAGS]:
                all_suggestions.append({"name": tag_name, "color": tag_color})

        return all_suggestions

    except Exception as e:
        print(f"[TAGS] Error getting suggestions: {e}")
        return SUGGESTED_TAGS  # Fallback to predefined

@router.get("/projects")
def get_all_project_tags(user_id: str = Depends(get_current_user)):
    """
    Get all tags for all of the current user's projects in one request.
    """
    try:
        response = supabase.table("project_tags").select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=False)\
            .execute()

        return response.data or []

    except Exception as e:
        print(f"[TAGS] Error getting all project tags: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get project tags: {str(e)}")

@router.get("/projects/{project_id}")
def get_project_tags(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get all tags for a specific project.
    """
    try:
        response = supabase.table("project_tags").select("*")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .order("created_at", desc=False)\
            .execute()

        return response.data or []

    except Exception as e:
        print(f"[TAGS] Error getting project tags: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get tags: {str(e)}")

@router.post("/projects/{project_id}")
def add_tag_to_project(
    project_id: str,
    request: AddTagRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Add a tag to a project.
    Max 5 tags per project.
    Tag names are case-insensitive (stored as lowercase).
    """
    try:
        # Normalize tag name to lowercase
        tag_name = request.tag_name.strip().lower()

        if not tag_name:
            raise HTTPException(status_code=400, detail="Tag name cannot be empty")

        # Check current tag count
        existing_tags = supabase.table("project_tags").select("id")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        if len(existing_tags.data or []) >= 5:
            raise HTTPException(status_code=400, detail="Maximum 5 tags per project")

        # Check if tag already exists for this project
        existing_tag = supabase.table("project_tags").select("*")\
            .eq("project_id", project_id)\
            .eq("tag_name", tag_name)\
            .eq("user_id", user_id)\
            .execute()

        if existing_tag.data:
            raise HTTPException(status_code=400, detail="Tag already exists on this project")

        # Find matching predefined tag or assign random color
        tag_color = None
        for suggested in SUGGESTED_TAGS:
            if suggested["name"] == tag_name:
                tag_color = suggested["color"]
                break

        if not tag_color:
            # Check if user has used this tag before
            user_tag = supabase.table("project_tags").select("tag_color")\
                .eq("user_id", user_id)\
                .eq("tag_name", tag_name)\
                .limit(1)\
                .execute()

            if user_tag.data:
                tag_color = user_tag.data[0]["tag_color"]
            else:
                # Assign random color
                tag_color = random.choice(TAG_COLORS)

        # Create tag
        new_tag = {
            "project_id": project_id,
            "user_id": user_id,
            "tag_name": tag_name,
            "tag_color": tag_color
        }

        response = supabase.table("project_tags").insert(new_tag).execute()

        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create tag")

        return response.data[0]

    except HTTPException:
        raise
    except Exception as e:
        print(f"[TAGS] Error adding tag: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add tag: {str(e)}")

@router.delete("/projects/{project_id}/tags/{tag_id}")
def remove_tag_from_project(
    project_id: str,
    tag_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Remove a tag from a project.
    """
    try:
        response = supabase.table("project_tags").delete()\
            .eq("id", tag_id)\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Tag not found")

        return {"message": "Tag removed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[TAGS] Error removing tag: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove tag: {str(e)}")
