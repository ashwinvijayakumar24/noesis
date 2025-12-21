from fastapi import APIRouter, HTTPException, Depends, Header
from app.core.supabase_client import supabase
from app.schemas.projects import ProjectBundle, Dataset, Document
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import datetime

router = APIRouter()

# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split("Bearer ")[-1]
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")

# CREATE
@router.post("/")
def create_project(title: str, description: Optional[str] = None, user_id: str = Depends(get_current_user)):
    data = {
        "user_id": user_id,
        "title": title,
        "description": description,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }
    res = supabase.table("projects").insert(data).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to create project")
    return {"message": "Project created", "project": res.data[0]}

# READ (all user projects)
@router.get("/")
def get_projects(user_id: str = Depends(get_current_user)):
    # Get all projects for the user
    res = supabase.table("projects").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    projects = res.data

    # For each project, count the number of documents
    for project in projects:
        doc_count_res = supabase.table("documents").select("id", count="exact").eq("project_id", project["id"]).eq("user_id", user_id).execute()
        project["document_count"] = doc_count_res.count if doc_count_res.count is not None else 0

    return projects

# READ (single)
@router.get("/{project_id}")
def get_project(project_id: str, user_id: str = Depends(get_current_user)):
    res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return res.data[0]

# UPDATE
@router.put("/{project_id}")
def update_project(project_id: str, title: Optional[str] = None, description: Optional[str] = None, user_id: str = Depends(get_current_user)):
    updates = {"updated_at": datetime.datetime.utcnow().isoformat()}
    if title:
        updates["title"] = title
    if description:
        updates["description"] = description
    res = supabase.table("projects").update(updates).eq("id", project_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=400, detail="Failed to update project")
    return {"message": "Project updated", "project": res.data[0]}

# DELETE
@router.delete("/{project_id}")
def delete_project(project_id: str, user_id: str = Depends(get_current_user)):
    res = supabase.table("projects").delete().eq("id", project_id).eq("user_id", user_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Project not found or already deleted")
    return {"message": "Project deleted"}

# ATTACH DATASET TO PROJECT
@router.post("/{project_id}/attach-dataset/{dataset_id}")
def attach_dataset_to_project(project_id: str, dataset_id: str, user_id: str = Depends(get_current_user)):
    """
    Attach an existing dataset to a project.
    Updates the dataset's project_id field.
    """
    # First verify the project exists and belongs to the user
    project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify the dataset exists and belongs to the user
    dataset_res = supabase.table("datasets").select("*").eq("id", dataset_id).eq("user_id", user_id).execute()
    if not dataset_res.data:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # Update the dataset to attach it to the project
    update_res = supabase.table("datasets").update({
        "project_id": project_id,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("id", dataset_id).eq("user_id", user_id).execute()

    if not update_res.data:
        raise HTTPException(status_code=400, detail="Failed to attach dataset to project")

    return {
        "message": "Dataset attached to project successfully",
        "dataset": update_res.data[0]
    }

# GET PROJECT BUNDLE (project + datasets + documents)
@router.get("/{project_id}/bundle", response_model=ProjectBundle)
def get_project_bundle(project_id: str, user_id: str = Depends(get_current_user)):
    """
    Get a project with all its related datasets and documents.
    Returns a ProjectBundle containing the project, all attached datasets, and all attached documents.
    """
    # Get the project
    project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project_data = project_res.data[0]

    # Get all documents attached to this project
    documents_res = supabase.table("documents").select("*").eq("project_id", project_id).eq("user_id", user_id).execute()
    documents = documents_res.data if documents_res.data else []
    print(f"[BUNDLE] project_id={project_id}, found {len(documents)} documents")

    # Build the bundle response
    bundle = {
        **project_data,
        "documents": documents
    }

    return bundle


# RAG SETTINGS SCHEMA
class RAGSettingsUpdate(BaseModel):
    chunk_size: Optional[int] = Field(None, ge=200, le=2000, description="Chunk size in tokens (200-2000)")
    chunk_overlap: Optional[int] = Field(None, ge=0, le=200, description="Chunk overlap in tokens (0-200)")
    embedding_model: Optional[str] = Field(None, description="Embedding model (text-embedding-3-small or text-embedding-3-large)")
    max_chunks: Optional[int] = Field(None, ge=1, le=20, description="Max chunks to retrieve (1-20)")
    similarity_threshold: Optional[float] = Field(None, ge=0.0, le=1.0, description="Minimum similarity score (0.0-1.0)")


# GET RAG SETTINGS
@router.get("/{project_id}/rag-settings")
def get_rag_settings(project_id: str, user_id: str = Depends(get_current_user)):
    """
    Get RAG configuration settings for a project.
    """
    project_res = supabase.table("projects").select("rag_settings").eq("id", project_id).eq("user_id", user_id).execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    rag_settings = project_res.data[0].get("rag_settings", {})

    # Return defaults if not set
    return {
        "chunk_size": rag_settings.get("chunk_size", 1000),
        "chunk_overlap": rag_settings.get("chunk_overlap", 150),
        "embedding_model": rag_settings.get("embedding_model", "text-embedding-3-small"),
        "max_chunks": rag_settings.get("max_chunks", 5),
        "similarity_threshold": rag_settings.get("similarity_threshold", 0.0)
    }


# UPDATE RAG SETTINGS
@router.patch("/{project_id}/rag-settings")
def update_rag_settings(project_id: str, settings: RAGSettingsUpdate, user_id: str = Depends(get_current_user)):
    """
    Update RAG configuration settings for a project.

    Note: Changing these settings does NOT automatically re-process existing documents.
    You will need to manually re-ingest documents for changes to take effect.
    """
    # Verify project exists and belongs to user
    project_res = supabase.table("projects").select("rag_settings").eq("id", project_id).eq("user_id", user_id).execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get current settings
    current_settings = project_res.data[0].get("rag_settings", {})

    # Validate embedding model
    if settings.embedding_model and settings.embedding_model not in ["text-embedding-3-small", "text-embedding-3-large"]:
        raise HTTPException(status_code=400, detail="Invalid embedding model. Must be 'text-embedding-3-small' or 'text-embedding-3-large'")

    # Update only provided fields
    updated_settings = {**current_settings}
    if settings.chunk_size is not None:
        updated_settings["chunk_size"] = settings.chunk_size
    if settings.chunk_overlap is not None:
        updated_settings["chunk_overlap"] = settings.chunk_overlap
    if settings.embedding_model is not None:
        updated_settings["embedding_model"] = settings.embedding_model
    if settings.max_chunks is not None:
        updated_settings["max_chunks"] = settings.max_chunks
    if settings.similarity_threshold is not None:
        updated_settings["similarity_threshold"] = settings.similarity_threshold

    # Update in database
    update_res = supabase.table("projects").update({
        "rag_settings": updated_settings,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("id", project_id).eq("user_id", user_id).execute()

    if not update_res.data:
        raise HTTPException(status_code=400, detail="Failed to update RAG settings")

    return {
        "message": "RAG settings updated successfully",
        "rag_settings": updated_settings
    }


# RESET RAG SETTINGS TO DEFAULTS
@router.post("/{project_id}/rag-settings/reset")
def reset_rag_settings(project_id: str, user_id: str = Depends(get_current_user)):
    """
    Reset RAG settings to default values.
    """
    # Verify project exists
    project_res = supabase.table("projects").select("id").eq("id", project_id).eq("user_id", user_id).execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    default_settings = {
        "chunk_size": 1000,
        "chunk_overlap": 150,
        "embedding_model": "text-embedding-3-small",
        "max_chunks": 5,
        "similarity_threshold": 0.0
    }

    # Update in database
    update_res = supabase.table("projects").update({
        "rag_settings": default_settings,
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("id", project_id).eq("user_id", user_id).execute()

    if not update_res.data:
        raise HTTPException(status_code=400, detail="Failed to reset RAG settings")

    return {
        "message": "RAG settings reset to defaults",
        "rag_settings": default_settings
    }


# ============================================
# PROJECT INSIGHTS ENDPOINTS
# ============================================

def _run_insights_analysis_task(project_id: str, user_id: str):
    """
    Background task that performs project insights analysis.
    Fetches all analyzed documents and runs cross-paper analysis.
    """
    from app.services.project_insights import analyze_project_insights, validate_insights

    try:
        print(f"[INSIGHTS-BG] Starting insights analysis for project_id={project_id}")

        # 1. Fetch all documents for this project
        documents_res = supabase.table("documents").select("*")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        if not documents_res.data:
            raise Exception("No documents found in project")

        documents = documents_res.data
        print(f"[INSIGHTS-BG] Found {len(documents)} documents")

        # 2. Filter to only analyzed documents with valid analysis
        analyzed_docs = []
        for doc in documents:
            if doc.get('status') == 'analyzed' and doc.get('analysis'):
                analyzed_docs.append({
                    'id': doc['id'],
                    'title': doc['title'],
                    'analysis': doc['analysis']
                })

        if len(analyzed_docs) == 0:
            raise Exception("No analyzed documents found. Please analyze documents first.")

        print(f"[INSIGHTS-BG] Found {len(analyzed_docs)} analyzed documents")

        # 3. Run insights analysis
        print(f"[INSIGHTS-BG] Running GPT-4o insights analysis")
        insights = analyze_project_insights(analyzed_docs)

        # Add timestamp
        insights['analysis_metadata']['timestamp'] = datetime.datetime.utcnow().isoformat()

        # 4. Validate insights
        validate_insights(insights)
        print(f"[INSIGHTS-BG] Insights analysis completed and validated")

        # 5. Store insights in database (with document count tracking)
        update_response = supabase.table("projects").update({
            "insights": insights,
            "insights_status": "analyzed",
            "insights_doc_count": len(analyzed_docs),  # Track number of docs analyzed
            "insights_updated_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", project_id).eq("user_id", user_id).execute()

        if not update_response.data:
            raise Exception("Failed to update project with insights")

        print(f"[INSIGHTS-BG] Successfully stored insights for project_id={project_id}")

    except Exception as e:
        print(f"[INSIGHTS-BG] ERROR for project_id={project_id}: {type(e).__name__}: {str(e)}")
        # Update status to failed
        supabase.table("projects").update({
            "insights_status": "failed",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", project_id).eq("user_id", user_id).execute()


@router.post("/{project_id}/insights/analyze")
def analyze_project_insights_endpoint(project_id: str, user_id: str = Depends(get_current_user)):
    """
    Trigger insights analysis for a project.

    This endpoint:
    1. Verifies all documents in the project are analyzed
    2. Starts background analysis of all papers together
    3. Returns immediately with status='analyzing'

    The analysis identifies:
    - Research gaps (methodological, population, theoretical, temporal)
    - Common themes across papers
    - Methodological patterns
    - Timeline and evolution of ideas
    - Conflicting findings
    - Citation patterns
    """
    print(f"[INSIGHTS] Triggering insights analysis for project_id={project_id}")

    # 1. Verify project belongs to user
    project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]

    # 2. Check if already analyzing
    if project.get("insights_status") == "analyzing":
        return {
            "message": "Insights analysis already in progress",
            "status": "analyzing"
        }

    # 3. Get all documents for this project
    documents_res = supabase.table("documents").select("id, title, status, analysis")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not documents_res.data or len(documents_res.data) == 0:
        raise HTTPException(status_code=400, detail="No documents in project. Add documents first.")

    documents = documents_res.data

    # 4. Verify all documents are analyzed
    unanalyzed_docs = []
    for doc in documents:
        if doc.get('status') != 'analyzed' or not doc.get('analysis'):
            unanalyzed_docs.append(doc['title'])

    if unanalyzed_docs:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "All documents must be analyzed before generating insights",
                "unanalyzed_documents": unanalyzed_docs
            }
        )

    print(f"[INSIGHTS] All {len(documents)} documents are analyzed")

    # 5. Update status to 'analyzing'
    supabase.table("projects").update({
        "insights_status": "analyzing",
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("id", project_id).eq("user_id", user_id).execute()

    # 6. Submit background task
    from app.services.background_tasks import submit_task
    submit_task(_run_insights_analysis_task, project_id, user_id)

    print(f"[INSIGHTS] Background insights analysis task submitted for project_id={project_id}")

    return {
        "message": "Insights analysis started",
        "status": "analyzing",
        "num_documents": len(documents)
    }


@router.get("/{project_id}/insights")
def get_project_insights(project_id: str, user_id: str = Depends(get_current_user)):
    """
    Get insights for a project.

    Returns the insights data if available, or the current status.

    Possible statuses:
    - not_analyzed: Insights have not been generated yet
    - analyzing: Insights analysis is in progress
    - analyzed: Insights are ready
    - failed: Insights analysis failed
    """
    print(f"[GET-INSIGHTS] Fetching insights for project_id={project_id}")

    # Verify project belongs to user
    project_res = supabase.table("projects").select("insights, insights_status, insights_updated_at, insights_doc_count")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]
    status = project.get("insights_status", "not_analyzed")
    insights = project.get("insights")
    updated_at = project.get("insights_updated_at")
    insights_doc_count = project.get("insights_doc_count", 0)

    # Get current count of analyzed documents
    current_docs_res = supabase.table("documents").select("id", count="exact")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .eq("status", "analyzed")\
        .execute()

    current_analyzed_count = current_docs_res.count if current_docs_res.count is not None else 0

    if status == "analyzed" and insights:
        return {
            "status": "analyzed",
            "insights": insights,
            "updated_at": updated_at,
            "insights_doc_count": insights_doc_count,
            "current_analyzed_count": current_analyzed_count,
            "is_stale": current_analyzed_count != insights_doc_count
        }
    elif status == "analyzing":
        return {
            "status": "analyzing",
            "message": "Insights analysis in progress"
        }
    elif status == "failed":
        return {
            "status": "failed",
            "message": "Insights analysis failed. Please try again."
        }
    else:  # not_analyzed
        return {
            "status": "not_analyzed",
            "message": "Insights have not been generated yet"
        }
