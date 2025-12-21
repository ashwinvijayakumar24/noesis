from fastapi import APIRouter, Depends, Header, HTTPException
from app.core.supabase_client import supabase
from typing import Optional

router = APIRouter()

# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split("Bearer ")[-1]
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")

@router.get("/")
def global_search(
    q: str,
    user_id: str = Depends(get_current_user)
):
    """
    Global search across projects, documents, and datasets.
    Returns top 5 results per category.
    """
    if not q or len(q.strip()) < 2:
        return {
            "query": q,
            "projects": [],
            "documents": [],
            "datasets": [],
            "total": 0
        }

    query = q.strip()
    search_pattern = f"%{query}%"

    try:
        # Search projects (title, description)
        projects_response = supabase.table("projects").select("*")\
            .eq("user_id", user_id)\
            .or_(f"title.ilike.{search_pattern},description.ilike.{search_pattern}")\
            .order("updated_at", desc=True)\
            .limit(5)\
            .execute()

        projects = projects_response.data or []

        # Search documents (title)
        documents_response = supabase.table("documents").select("*, projects!inner(id, title)")\
            .eq("user_id", user_id)\
            .ilike("title", search_pattern)\
            .order("created_at", desc=True)\
            .limit(5)\
            .execute()

        documents = documents_response.data or []

        # Search datasets (filename)
        datasets_response = supabase.table("datasets").select("*, projects!inner(id, title)")\
            .eq("user_id", user_id)\
            .ilike("filename", search_pattern)\
            .order("created_at", desc=True)\
            .limit(5)\
            .execute()

        datasets = datasets_response.data or []

        # Check if there are more results
        projects_total = len(projects)
        documents_total = len(documents)
        datasets_total = len(datasets)

        # For "has_more", we check if we got exactly the limit (suggests more might exist)
        has_more_projects = projects_total >= 5
        has_more_documents = documents_total >= 5
        has_more_datasets = datasets_total >= 5

        return {
            "query": query,
            "projects": projects,
            "documents": documents,
            "datasets": datasets,
            "total": projects_total + documents_total + datasets_total,
            "has_more": {
                "projects": has_more_projects,
                "documents": has_more_documents,
                "datasets": has_more_datasets
            }
        }

    except Exception as e:
        print(f"[SEARCH] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@router.get("/recent")
def get_recent_activity(
    limit: int = 5,
    user_id: str = Depends(get_current_user)
):
    """
    Get recently viewed/updated projects for the user.
    """
    try:
        response = supabase.table("projects").select("*")\
            .eq("user_id", user_id)\
            .order("updated_at", desc=True)\
            .limit(limit)\
            .execute()

        return response.data or []

    except Exception as e:
        print(f"[RECENT] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recent activity: {str(e)}")
