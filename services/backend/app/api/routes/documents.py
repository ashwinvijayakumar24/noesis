"""
Documents API Endpoints

Provides endpoints for managing research documents (separate from datasets).
Documents are PDFs that will be ingested into the RAG pipeline.
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, Query, Request
from fastapi.responses import Response
from openai import APIConnectionError, APIError, RateLimitError
from app.core.supabase_client import supabase
from app.core.api_errors import build_error_detail, raise_api_error
from app.services.citation_management import format_citation_bibtex
from app.core.security_middleware import SecureAuthValidator, limiter
from app.services.progress_tracking import (
    clear_progress_snapshot,
    get_progress_snapshot,
    store_progress_snapshot,
)
from app.tasks import analyze_document_task
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import logging
import json
import hashlib
import re

router = APIRouter()

# Set up logging
logger = logging.getLogger(__name__)

ACTIVE_DOCUMENT_STATUSES = {"uploaded", "processing", "ready", "analyzing"}


def _merge_metadata(existing: Optional[dict], **updates) -> dict:
    merged = dict(existing or {})
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    return merged


def _is_transient_provider_error(error: Exception) -> bool:
    if isinstance(error, (RateLimitError, APIError, APIConnectionError)):
        return True

    message = str(error).lower()
    return any(
        token in message
        for token in (
            "ratelimiterror",
            "rate limit",
            "too many requests",
            "apiconnectionerror",
            "temporary service issue",
            "connection reset",
        )
    )


def _attach_document_progress(document: dict) -> dict:
    progress = get_progress_snapshot("document", document["id"])
    if progress and document.get("status") in ACTIVE_DOCUMENT_STATUSES:
        document["progress"] = progress

    metadata = document.get("metadata") or {}
    error_detail = metadata.get("error_detail")
    if error_detail and document.get("status") == "failed":
        document["error_detail"] = error_detail

    return document


def _sanitize_filename(filename: str, fallback: str = "document_analysis") -> str:
    safe_filename = "".join(c for c in (filename or "") if c.isalnum() or c in (" ", "_", "-")).strip()
    if not safe_filename:
        safe_filename = fallback
    return safe_filename.replace(" ", "_")


def _sanitize_storage_stem(filename: str, fallback: str = "document") -> str:
    stem = filename.rsplit(".", 1)[0] if filename and "." in filename else filename
    safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem or "").strip("_")
    return (safe_stem or fallback)[:80]


def _get_existing_manual_upload(user_id: str, project_id: Optional[str], file_sha256: str) -> Optional[dict]:
    query = (
        supabase.table("documents")
        .select("*")
        .eq("user_id", user_id)
        .eq("source_type", "manual_upload")
        .eq("metadata->>file_sha256", file_sha256)
        .limit(1)
    )
    if project_id:
        query = query.eq("project_id", project_id)
    else:
        query = query.is_("project_id", "null")

    response = query.execute()
    if response.data:
        return _attach_document_progress(response.data[0])
    return None


def _is_unique_violation(error: Exception) -> bool:
    message = str(error).lower()
    return "23505" in message or "duplicate key" in message or "unique constraint" in message


def _serialize_document_analysis(analysis: object, title: str) -> str:
    """Normalize structured document analysis into markdown for export flows."""
    if isinstance(analysis, str):
        return analysis

    if not isinstance(analysis, dict):
        return str(analysis)

    sections: List[str] = [f"# {title}"]

    executive_summary = analysis.get("executive_summary")
    if executive_summary:
        sections.extend(["", "## Executive Summary", "", str(executive_summary)])

    methodology = analysis.get("methodology") or {}
    if methodology:
        sections.extend(["", "## Methodology", ""])
        if methodology.get("approach"):
            sections.append(f"**Approach:** {methodology['approach']}")
        if methodology.get("summary"):
            sections.extend(["", str(methodology["summary"])])

    key_findings = analysis.get("key_findings") or []
    if key_findings:
        sections.extend(["", "## Key Findings", ""])
        sections.extend(f"- {finding}" for finding in key_findings)

    results = analysis.get("results") or {}
    if results:
        sections.extend(["", "## Results", ""])
        if results.get("summary"):
            sections.append(str(results["summary"]))
        for key, value in results.items():
            if key == "summary":
                continue
            label = key.replace("_", " ").title()
            sections.append(f"- **{label}:** {value}")

    limitations = analysis.get("limitations") or []
    if limitations:
        sections.extend(["", "## Limitations", ""])
        sections.extend(f"- {limitation}" for limitation in limitations)

    references = analysis.get("references") or []
    if references:
        sections.extend(["", "## References", ""])
        sections.extend(f"- {reference}" for reference in references)

    if len(sections) == 1:
        sections.extend(["", "## Analysis", "", json.dumps(analysis, indent=2)])

    return "\n".join(sections).strip()


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"
        )

    # Use secure token validator
    token = SecureAuthValidator.validate_bearer_token(authorization)

    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


@router.post("/upload")
@limiter.limit("10/minute")  # Max 10 document uploads per minute
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user)
):
    """
    Upload a document file to Supabase Storage and create metadata entry.
    Files are stored in user-specific folders: documents/{user_id}/{filename}

    Rate limit: 10 uploads per minute per IP address
    """
    print(f"[UPLOAD] Received: file={file.filename}, project_id={project_id}, title={title}, user_id={user_id}")
    from app.services.quota_management import check_quota, QuotaExceededError
    try:
        original_filename = file.filename or "document.pdf"
        file_extension = original_filename.split(".")[-1].lower()
        if file_extension != "pdf":
            raise_api_error(
                400,
                code="invalid_file_type",
                title="PDF required",
                message="Only PDF uploads are supported in this flow.",
                details=[f"Received file: {original_filename}"],
                next_action="fix_file",
                retryable=False,
            )

        # CHECK QUOTA BEFORE PROCESSING
        try:
            await check_quota(user_id, "document")
        except QuotaExceededError as qe:
            raise_api_error(
                429,
                code="quota_exceeded",
                title="Monthly PDF limit reached",
                message=str(qe),
                next_action="upgrade",
                retryable=False,
                error="quota_exceeded",
                quota_type=qe.quota_type,
                limit=qe.limit,
                current=qe.current,
            )
        # Read file content and derive the idempotency key before any write.
        file_content = await file.read()
        file_size = len(file_content)
        file_sha256 = hashlib.sha256(file_content).hexdigest()

        existing_document = _get_existing_manual_upload(user_id, project_id, file_sha256)
        if existing_document:
            print(f"[UPLOAD] Duplicate upload detected; returning existing document_id={existing_document.get('id')}")
            return {
                "message": "Document already exists",
                "document": existing_document,
                "duplicate": True,
                "task_id": (existing_document.get("metadata") or {}).get("analysis_task_id"),
            }

        # Generate deterministic storage path from content hash.
        import time
        import random

        extension = original_filename.rsplit('.', 1)[1] if '.' in original_filename else ''
        safe_stem = _sanitize_storage_stem(original_filename or title or "document")
        project_scope = project_id or "no_project"
        unique_filename = f"{file_sha256[:16]}_{safe_stem}.{extension or 'pdf'}"
        storage_path = f"{user_id}/{project_scope}/{unique_filename}"

        # Upload to Supabase Storage with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"[UPLOAD] Attempting upload (try {attempt + 1}/{max_retries}) to path: {storage_path}")
                try:
                    storage_response = supabase.storage.from_("documents").upload(
                        path=storage_path,
                        file=file_content,
                        file_options={"content-type": file.content_type or "application/octet-stream"}
                    )
                    print(f"[UPLOAD] Upload successful: {storage_response}")
                except Exception as storage_error:
                    # A deterministic path can already exist if a previous DB insert failed
                    # after storage upload, or if a concurrent request won the storage write.
                    if "already exists" not in str(storage_error).lower() and "duplicate" not in str(storage_error).lower():
                        raise
                    print(f"[UPLOAD] Storage object already exists for hash={file_sha256[:16]}; continuing")
                break
            except Exception as upload_error:
                print(f"[UPLOAD] Upload attempt {attempt + 1} failed: {type(upload_error).__name__}: {str(upload_error)}")
                if attempt < max_retries - 1:
                    time.sleep(1 + random.random())  # Wait 1-2 seconds before retry
                else:
                    raise upload_error

        # Get public/signed URL for the file
        file_url = supabase.storage.from_("documents").get_public_url(storage_path)

        # Create metadata entry in documents table
        metadata_entry = {
            "user_id": user_id,
            "project_id": project_id,
            "title": title or original_filename,
            "description": description,
            "file_url": file_url,
            "file_type": file.content_type or "application/octet-stream",
            "file_size": file_size,
            "status": "uploaded",
            "source_type": "manual_upload",
            "metadata": {
                "original_filename": original_filename,
                "file_sha256": file_sha256,
                "storage_path": storage_path,
                "upload_timestamp": datetime.utcnow().isoformat()
            },
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        try:
            db_response = supabase.table("documents").insert(metadata_entry).execute()
        except Exception as insert_error:
            if _is_unique_violation(insert_error):
                existing_document = _get_existing_manual_upload(user_id, project_id, file_sha256)
                if existing_document:
                    existing_storage_path = (existing_document.get("metadata") or {}).get("storage_path")
                    if existing_storage_path != storage_path:
                        try:
                            supabase.storage.from_("documents").remove([storage_path])
                        except Exception as cleanup_error:
                            print(f"[UPLOAD] Warning: failed to remove duplicate storage object {storage_path}: {cleanup_error}")
                    print(f"[UPLOAD] Concurrent duplicate insert detected; returning existing document_id={existing_document.get('id')}")
                    return {
                        "message": "Document already exists",
                        "document": existing_document,
                        "duplicate": True,
                        "task_id": (existing_document.get("metadata") or {}).get("analysis_task_id"),
                    }
            raise

        if not db_response.data:
            # If metadata creation fails, try to delete the uploaded file
            try:
                supabase.storage.from_("documents").remove([storage_path])
            except:
                pass
            raise_api_error(
                400,
                code="document_metadata_failed",
                title="We couldn't register this upload",
                message="The PDF was uploaded, but Noesis could not create the document record.",
                next_action="retry",
                retryable=True,
            )

        document = db_response.data[0]
        document_id = document['id']
        print(f"[UPLOAD] Document created: id={document_id}, project_id={document.get('project_id')}")

        # Auto-trigger analysis: set status to 'analyzing' and enqueue Celery task
        task_id = None
        if project_id:
            try:
                store_progress_snapshot("document", document_id, "queued", 5, "Queued for document analysis")
                task_result = analyze_document_task.delay(document_id, user_id, project_id)
                task_id = task_result.id
                supabase.table("documents").update({
                    "status": "analyzing",
                    "updated_at": datetime.utcnow().isoformat(),
                    "metadata": _merge_metadata(document.get("metadata"), analysis_task_id=task_id),
                }).eq("id", document_id).execute()
                print(f"[UPLOAD] Auto-triggered analysis for document_id={document_id}")
            except Exception as task_err:
                print(f"[UPLOAD] Warning: Failed to auto-trigger analysis: {task_err}")
                clear_progress_snapshot("document", document_id)

        # Refresh document record to reflect updated status
        doc_refresh = supabase.table("documents").select("*").eq("id", document_id).execute()
        if doc_refresh.data:
            document = _attach_document_progress(doc_refresh.data[0])

        return {
            "message": "Document uploaded successfully",
            "document": document,
            "duplicate": False,
            "task_id": task_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise_api_error(
            500,
            code="document_upload_failed",
            title="Upload failed",
            message="We couldn't upload this PDF.",
            details=[str(e)],
            next_action="retry",
            retryable=True,
        )


@router.get("/")
def list_documents(
    project_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100, description="Number of documents to return (max 100)"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
    user_id: str = Depends(get_current_user)
):
    """
    List all documents for the authenticated user with pagination.
    Optionally filter by project_id.

    Pagination:
    - limit: Number of documents to return (default: 50, max: 100)
    - offset: Number of documents to skip (default: 0)
    - Returns total count and has_more flag
    """
    # Get total count for pagination
    count_query = supabase.table("documents").select("id", count="exact").eq("user_id", user_id)
    if project_id:
        count_query = count_query.eq("project_id", project_id)
    count_response = count_query.execute()
    total = count_response.count if hasattr(count_response, 'count') else 0

    # Get paginated results
    query = supabase.table("documents").select("*").eq("user_id", user_id)
    if project_id:
        query = query.eq("project_id", project_id)

    response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()

    documents = [_attach_document_progress(document) for document in (response.data or [])]

    return {
        "data": documents,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }
    }


@router.get("/{document_id}")
def get_document(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Get a single document by ID.
    """
    response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

    if not response.data:
        raise_api_error(
            404,
            code="document_not_found",
            title="Document not found",
            message="This document may have been deleted or is unavailable.",
            next_action="refresh",
            retryable=False,
        )

    return _attach_document_progress(response.data[0])


@router.put("/{document_id}")
def update_document(
    document_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Update document metadata.
    """
    updates = {"updated_at": datetime.utcnow().isoformat()}

    if title:
        updates["title"] = title
    if description:
        updates["description"] = description
    if status:
        updates["status"] = status

    response = supabase.table("documents").update(updates).eq("id", document_id).eq("user_id", user_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"message": "Document updated", "document": response.data[0]}


class UpdateTagsRequest(BaseModel):
    tags: List[str]


@router.patch("/{document_id}/tags")
def update_document_tags(
    document_id: str,
    request: UpdateTagsRequest,
    user_id: str = Depends(get_current_user)
):
    tags = [t.strip().lower() for t in request.tags if t.strip()][:10]
    response = supabase.table("documents").update({
        "tags": tags,
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", document_id).eq("user_id", user_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"tags": response.data[0]["tags"]}


@router.delete("/{document_id}")
def delete_document(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Delete a document and its associated file from storage.
    Also deletes all associated chunks from the vector database.
    """
    print(f"[DELETE] Starting deletion for document_id={document_id}, user_id={user_id}")

    # First, get the document to find the file path
    document_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

    if not document_response.data:
        raise_api_error(
            404,
            code="document_not_found",
            title="Document not found",
            message="This document may have been deleted or is unavailable.",
            next_action="refresh",
            retryable=False,
        )

    document = document_response.data[0]
    print(f"[DELETE] Found document: title={document.get('title')}, file_url={document.get('file_url')}")

    # Extract storage path from file_url
    # URL format: https://.../storage/v1/object/public/documents/{user_id}/{filename}
    file_url = document.get("file_url", "")
    storage_path = None

    if file_url and "/documents/" in file_url:
        # Extract path after "/documents/"
        path_parts = file_url.split("/documents/")
        if len(path_parts) >= 2:
            storage_path = path_parts[1]  # This is "{user_id}/{filename}"
            print(f"[DELETE] Extracted storage path: {storage_path}")

    # Delete from storage if we have a valid path
    if storage_path:
        try:
            print(f"[DELETE] Attempting to delete file from storage: {storage_path}")
            supabase.storage.from_("documents").remove([storage_path])
            print(f"[DELETE] Successfully deleted file from storage")
        except Exception as e:
            # Log the error but continue with database deletion
            print(f"[DELETE] Warning: Failed to delete file from storage: {type(e).__name__}: {str(e)}")
    else:
        print(f"[DELETE] Warning: Could not extract storage path from file_url: {file_url}")

    # Delete chunks from vector database (cascading should handle this, but explicit is better)
    try:
        print(f"[DELETE] Deleting document chunks for document_id={document_id}")
        chunks_response = supabase.table("document_chunks").delete().eq("document_id", document_id).execute()
        chunks_count = len(chunks_response.data) if chunks_response.data else 0
        print(f"[DELETE] Deleted {chunks_count} document chunks")
    except Exception as e:
        print(f"[DELETE] Warning: Failed to delete document chunks: {type(e).__name__}: {str(e)}")

    # Delete from database
    print(f"[DELETE] Deleting document record from database")
    db_response = supabase.table("documents").delete().eq("id", document_id).eq("user_id", user_id).execute()

    if not db_response.data:
        raise HTTPException(status_code=404, detail="Failed to delete document")

    print(f"[DELETE] Successfully deleted document {document_id}")

    # Invalidate project insights and clean up orphaned derived rows
    project_id = document.get("project_id")
    if project_id:
        try:
            supabase.table("projects").update({
                "insights_status": "not_analyzed",
                "insights": None,
                "insights_doc_count": 0,
                "insights_updated_at": None
            }).eq("id", project_id).execute()
            print(f"[DELETE] Invalidated insights for project_id={project_id}")
        except Exception as e:
            print(f"[DELETE] Warning: Failed to invalidate project insights: {e}")

        try:
            supabase.table("research_questions").delete().eq("project_id", project_id).execute()
            print(f"[DELETE] Cleaned orphaned research_questions for project_id={project_id}")
        except Exception as e:
            print(f"[DELETE] Warning: Failed to clean research_questions: {e}")

        try:
            supabase.table("paper_recommendations").delete().eq("project_id", project_id).execute()
            print(f"[DELETE] Cleaned orphaned paper_recommendations for project_id={project_id}")
        except Exception as e:
            print(f"[DELETE] Warning: Failed to clean paper_recommendations: {e}")

    return {"message": "Document deleted successfully"}


@router.post("/{document_id}/retry")
def retry_document_analysis(document_id: str, user_id: str = Depends(get_current_user)):
    """Re-queue analysis for a failed document without requiring a re-upload."""
    document_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

    if not document_response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    document = document_response.data[0]
    if document.get("status") != "failed":
        raise_api_error(
            400,
            code="retry_not_allowed",
            title="Retry unavailable",
            message="Only failed document analyses can be retried.",
            next_action="refresh",
            retryable=False,
        )

    project_id = document.get("project_id") or ""
    store_progress_snapshot("document", document_id, "queued", 5, "Queued for document analysis")
    task_result = analyze_document_task.delay(document_id, user_id, project_id)

    update_response = supabase.table("documents").update({
        "status": "analyzing",
        "updated_at": datetime.utcnow().isoformat(),
        "metadata": _merge_metadata(document.get("metadata"), analysis_task_id=task_result.id),
    }).eq("id", document_id).eq("user_id", user_id).execute()

    if not update_response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    return {"message": "Analysis re-queued", "document_id": document_id, "task_id": task_result.id}


@router.post("/{document_id}/mark-failed")
def mark_document_failed(document_id: str, user_id: str = Depends(get_current_user)):
    """Mark a stuck document as failed so the retry button becomes available."""
    document_response = supabase.table("documents").select("id, status")\
        .eq("id", document_id).eq("user_id", user_id).execute()

    if not document_response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    stuck_statuses = {"analyzing", "processing", "uploaded", "ready"}
    if document_response.data[0].get("status") not in stuck_statuses:
        raise HTTPException(status_code=400, detail="Document is not in a stuck state")

    supabase.table("documents").update({
        "status": "failed",
        "updated_at": datetime.utcnow().isoformat(),
    }).eq("id", document_id).eq("user_id", user_id).execute()

    return {"document_id": document_id, "status": "failed"}


@router.post("/{document_id}/attach-to-project/{project_id}")
def attach_document_to_project(
    document_id: str,
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Attach an existing document to a project.
    """
    # Verify project exists and belongs to user
    project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify document exists and belongs to user
    doc_res = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()
    if not doc_res.data:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update document to attach it to the project
    update_res = supabase.table("documents").update({
        "project_id": project_id,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", document_id).eq("user_id", user_id).execute()

    if not update_res.data:
        raise HTTPException(status_code=400, detail="Failed to attach document to project")

    return {
        "message": "Document attached to project successfully",
        "document": update_res.data[0]
    }


def _run_analysis_task(document_id: str, file_url: str):
    """
    Background task that performs the actual document analysis using LangGraph workflow.

    This workflow:
    1. Extracts text from PDF
    2. Runs LangGraph workflow (structure, claims, methods, findings)
    3. Stores extracted claims/methods/findings in database
    4. Stores analysis report for frontend

    This runs in a separate thread to avoid blocking the API.
    """
    from app.services.rag_ingest import extract_structured_data_from_pdf, extract_text_from_pdf_fallback, get_pdf_page_count
    from app.workflows.document_analysis.graph import run_document_analysis_workflow
    from app.services.async_utils import run_coroutine_sync
    from app.services.quota_management import increment_quota_usage, track_openai_usage
    from app.core.openai_client import get_openai_client, get_completion_params
    import os

    try:
        print(f"[ANALYZE-BG-LG] ========== STARTING LANGGRAPH ANALYSIS ==========")
        print(f"[ANALYZE-BG-LG] document_id={document_id}")

        # Get document to retrieve user_id for quota tracking
        doc_response = supabase.table("documents").select("user_id, project_id, title, metadata").eq("id", document_id).execute()
        if not doc_response.data:
            raise Exception("Document not found")
        user_id = doc_response.data[0]["user_id"]
        project_id = doc_response.data[0].get("project_id")
        document_title = doc_response.data[0].get("title") or ""
        document_metadata = doc_response.data[0].get("metadata") or {}
        store_progress_snapshot("document", document_id, "queued", 5, "Queued for analysis")

        # 1. Download PDF from storage using Supabase client (authenticated)
        print(f"[ANALYZE-BG] Downloading PDF from: {file_url}")
        store_progress_snapshot("document", document_id, "parsing_pdf", 15, "Downloading and parsing PDF")

        # Extract storage path from file_url
        # URL format: https://.../storage/v1/object/public/documents/{user_id}/{filename}
        storage_path = None
        if file_url and "/documents/" in file_url:
            path_parts = file_url.split("/documents/")
            if len(path_parts) >= 2:
                storage_path = path_parts[1]
                print(f"[ANALYZE-BG] Extracted storage path: {storage_path}")

        if not storage_path:
            raise Exception(f"Could not extract storage path from file_url: {file_url}")

        # Download using Supabase client with authentication
        pdf_bytes = supabase.storage.from_("documents").download(storage_path)

        if not pdf_bytes:
            raise Exception("Failed to download PDF: empty response from storage")

        print(f"[ANALYZE-BG] Downloaded {len(pdf_bytes)} bytes")

        # 2. Get page count from PDF
        print(f"[ANALYZE-BG-LG] Step 2: Getting page count from PDF")
        page_count = get_pdf_page_count(pdf_bytes)
        print(f"[ANALYZE-BG-LG] ✓ PDF has {page_count} pages")

        # 3. Extract text and display metadata from PDF.
        print(f"[ANALYZE-BG-LG] Step 3: Extracting text and metadata from PDF")
        store_progress_snapshot("document", document_id, "extracting_structure", 30, "Extracting text and metadata")
        try:
            structured_data = run_coroutine_sync(extract_structured_data_from_pdf(pdf_bytes))
            paper_text = structured_data.get("full_text") or ""

            try:
                from app.services.document_metadata import enrich_and_persist_document_metadata

                store_progress_snapshot("document", document_id, "extracting_metadata", 38, "Extracting paper metadata")
                metadata_update = run_coroutine_sync(
                    enrich_and_persist_document_metadata(
                        document_id,
                        current_title=document_title,
                        existing_metadata=document_metadata,
                        structured_data=structured_data,
                    )
                )
                document_title = metadata_update.get("title", document_title)
                document_metadata = metadata_update.get("metadata", document_metadata)
                print(f"[ANALYZE-BG-LG] ✓ Metadata updated for document_id={document_id}")
            except Exception as metadata_err:
                print(f"[ANALYZE-BG-LG] Warning: metadata enrichment failed: {metadata_err}")
        except Exception as structured_err:
            print(f"[ANALYZE-BG-LG] Structured extraction failed, using fallback: {structured_err}")
            paper_text = extract_text_from_pdf_fallback(pdf_bytes)

        print(f"[ANALYZE-BG-LG] ✓ Extracted {len(paper_text)} characters of text")

        if len(paper_text) < 100:
            raise Exception("Extracted text is too short. PDF might be scanned or corrupted.")

        # 4. Run BOTH workflows in parallel for best of both worlds
        print(f"[ANALYZE-BG-LG] Step 4: Running dual analysis (LangGraph + Traditional)...")
        store_progress_snapshot("document", document_id, "running_analysis", 55, "Running paper analysis")

        # 4a. Run traditional comprehensive analysis (for display quality)
        print(f"[ANALYZE-BG-LG] Step 4a: Running traditional GPT-4o analysis for narrative quality...")
        from app.services.document_analysis import analyze_paper_text, validate_analysis

        comprehensive_analysis = analyze_paper_text(paper_text, page_count=page_count, model="gpt-5.2-chat-latest")
        validate_analysis(comprehensive_analysis)
        print(f"[ANALYZE-BG-LG] ✓ Traditional analysis complete (high-quality narrative)")

        # 4b. Run LangGraph workflow for structured extraction (for citations)
        print(f"[ANALYZE-BG-LG] Step 4b: Running LangGraph workflow for structured extraction...")
        print(f"[ANALYZE-BG-LG] This will extract: claims, methods, findings for citation matching")

        final_state = run_coroutine_sync(
            run_document_analysis_workflow(
                document_id=document_id,
                project_id=project_id,
                document_text=paper_text,
                page_count=page_count
            )
        )

        print(f"[ANALYZE-BG-LG] ✓ LangGraph workflow completed")
        print(f"[ANALYZE-BG-LG] Extracted: {len(final_state.get('claims', []))} claims, "
              f"{len(final_state.get('methods', []))} methods, "
              f"{len(final_state.get('findings', []))} findings")

        # Use traditional analysis for frontend (high quality)
        # But add LangGraph metadata for transparency
        analysis = comprehensive_analysis
        analysis['langgraph_metadata'] = {
            'claims_extracted': len(final_state.get('claims', [])),
            'methods_extracted': len(final_state.get('methods', [])),
            'findings_extracted': len(final_state.get('findings', [])),
            'structured_extraction_completed': True
        }

        print(f"[ANALYZE-BG-LG] ✓ Using traditional analysis for display (quality preserved)")
        print(f"[ANALYZE-BG-LG] ✓ LangGraph data will be used for citation matching")

        # Safety check: Ensure we have a valid analysis object
        if not analysis or not isinstance(analysis, dict):
            print(f"[ANALYZE-BG-LG] WARNING: Analysis report is empty or invalid, creating minimal report")
            analysis = {
                "executive_summary": "Analysis completed. Structured data extracted successfully.",
                "research_problem": "",
                "key_questions": [],
                "methodology": {"approach": "See structured data", "techniques": [], "dataset": ""},
                "key_findings": [],
                "results": {"summary": "See structured claims and findings", "metrics": []},
                "limitations": [],
                "future_work": [],
                "key_citations": [],
                "analysis_metadata": {
                    "version": "v2_langgraph",
                    "workflow_version": "1.0",
                    "claims_extracted": len(final_state.get("claims", [])),
                    "methods_extracted": len(final_state.get("methods", [])),
                    "findings_extracted": len(final_state.get("findings", []))
                }
            }

        # Ensure all required fields exist (for legacy frontend compatibility)
        required_fields = {
            "executive_summary": "Analysis complete.",
            "research_problem": "",
            "key_questions": [],
            "methodology": {"approach": "", "techniques": [], "dataset": ""},
            "key_findings": [],
            "results": {"summary": "", "metrics": []},
            "limitations": [],
            "future_work": [],
            "key_citations": []
        }

        for field, default_value in required_fields.items():
            if field not in analysis:
                analysis[field] = default_value

        print(f"[ANALYZE-BG-LG] ✓ Analysis report validated, all required fields present")

        # 5. Store extracted claims, methods, and findings in database
        print(f"[ANALYZE-BG-LG] Step 5: Storing structured data in database...")
        store_progress_snapshot("document", document_id, "generating_embeddings", 75, "Saving structured extraction")

        from app.services.structured_data_storage import store_structured_data
        struct_counts = store_structured_data(document_id, project_id, final_state)

        print(f"[ANALYZE-BG-LG] ✓ All structured data stored successfully "
              f"({struct_counts['claims']} claims, {struct_counts['methods']} methods, "
              f"{struct_counts['findings']} findings)")

        # 5.5. Track quota usage and OpenAI costs
        try:
            # Increment quota counter
            run_coroutine_sync(increment_quota_usage(user_id, "document"))
            print(f"[ANALYZE-BG] Quota incremented for user_id={user_id}")

            # Track OpenAI usage
            metadata = analysis.get("analysis_metadata", {})
            if metadata.get("prompt_tokens") and metadata.get("completion_tokens"):
                run_coroutine_sync(track_openai_usage(
                    user_id=user_id,
                    operation_type="document_analysis",
                    model=metadata.get("model", "gpt-5.2-chat-latest"),
                    prompt_tokens=metadata["prompt_tokens"],
                    completion_tokens=metadata["completion_tokens"],
                    project_id=project_id,
                    document_id=document_id
                ))
                print(f"[ANALYZE-BG] OpenAI usage tracked: {metadata['tokens_used']} tokens")
        except Exception as tracking_error:
            # Don't fail the analysis if tracking fails
            print(f"[ANALYZE-BG] WARNING: Failed to track quota/usage: {tracking_error}")

        # 6. Store analysis in database with v2_langgraph version
        print(f"[ANALYZE-BG-LG] Step 6: Storing analysis report in database...")
        store_progress_snapshot("document", document_id, "finalizing", 90, "Finalizing analysis")
        update_response = supabase.table("documents").update({
            "analysis": analysis,
            "status": "analyzed",
            "analysis_version": "v2_langgraph",  # Mark as LangGraph analysis
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", document_id).execute()

        if not update_response.data:
            raise Exception("Failed to update document with analysis")

        print(f"[ANALYZE-BG-LG] ✓ Analysis report stored")

        # 7. Auto-regenerate project insights (since new document analyzed)
        # Get the document's project_id
        document = update_response.data[0]
        project_id = document.get("project_id")

        if project_id:
            print(f"[ANALYZE-BG-LG] Auto-regenerating insights for project_id={project_id}")

            # Check if project has any insights (analyzed or not)
            project_res = supabase.table("projects").select("insights_status, user_id").eq("id", project_id).execute()

            if project_res.data:
                current_status = project_res.data[0].get("insights_status", "not_analyzed")
                project_user_id = project_res.data[0].get("user_id")

                # Only auto-regenerate if insights were previously analyzed
                # (Don't generate for first document - user should trigger manually)
                if current_status == "analyzed":
                    print(f"[ANALYZE-BG-LG] Triggering auto-regeneration of insights")
                    # Phase 3.3: Use Celery task instead of ThreadPoolExecutor
                    from app.tasks.insights_analysis import generate_insights_task

                    # Update status to analyzing
                    supabase.table("projects").update({
                        "insights_status": "analyzing",
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("id", project_id).execute()

                    # Submit Celery task to regenerate insights
                    task_result = generate_insights_task.delay(project_id, project_user_id)
                    print(f"[ANALYZE-BG-LG] ✓ Insights auto-regeneration triggered (task_id={task_result.id})")

                    # 8. Auto-re-analyze drafts after first document uploaded (Phase 2.1)
                    # Check for analyzed drafts in this project
                    drafts_res = supabase.table("drafts").select("id, status, title").eq("project_id", project_id).execute()

                    if drafts_res.data:
                        analyzed_drafts = [d for d in drafts_res.data if d.get("status") == "analyzed"]

                        if analyzed_drafts:
                            print(f"[ANALYZE-BG-LG] Found {len(analyzed_drafts)} analyzed draft(s) - triggering re-analysis for citation suggestions")

                            # Phase 3.3: Use Celery task instead of ThreadPoolExecutor
                            from app.tasks.draft_analysis import analyze_draft_task

                            for draft in analyzed_drafts:
                                draft_id = draft.get("id")
                                draft_title = draft.get("title", "Untitled")

                                # Update draft status to processing (re-analysis triggered)
                                supabase.table("drafts").update({
                                    "status": "processing",
                                    "updated_at": datetime.utcnow().isoformat()
                                }).eq("id", draft_id).execute()

                                # Submit Celery task to re-analyze draft
                                task_result = analyze_draft_task.delay(draft_id, project_id)
                                print(f"[ANALYZE-BG-LG] ✓ Draft re-analysis triggered for '{draft_title}' (draft_id={draft_id}, task_id={task_result.id})")

                else:
                    # Just mark as stale for first-time or failed insights
                        if current_status in ["analyzing", "failed"]:
                            supabase.table("projects").update({
                                "insights_status": "not_analyzed",
                                "updated_at": datetime.utcnow().isoformat()
                            }).eq("id", project_id).execute()
                        print(f"[ANALYZE-BG-LG] Insights status reset to not_analyzed")

        print(f"[ANALYZE-BG-LG] ========== LANGGRAPH ANALYSIS COMPLETE ==========")
        print(f"[ANALYZE-BG-LG] Successfully analyzed document_id={document_id}")
        store_progress_snapshot("document", document_id, "finalizing", 100, "Analysis ready")
        clear_progress_snapshot("document", document_id)

    except Exception as e:
        # Update status to failed
        import traceback
        print(f"[ANALYZE-BG-LG] ========== LANGGRAPH ANALYSIS FAILED ==========")
        print(f"[ANALYZE-BG-LG] ERROR for document_id={document_id}: {type(e).__name__}: {str(e)}")
        print(f"[ANALYZE-BG-LG] Traceback:\n{traceback.format_exc()}")
        error_detail = build_error_detail(
            code="transient_provider_error" if _is_transient_provider_error(e) else "document_analysis_failed",
            title="Analysis failed" if not _is_transient_provider_error(e) else "Service under load",
            message=(
                "The analysis service is under load. We can retry automatically."
                if _is_transient_provider_error(e)
                else "We couldn't analyze this PDF."
            ),
            next_action="retry",
            retryable=True,
            details=[str(e)] if str(e) else None,
        )
        clear_progress_snapshot("document", document_id)

        # CRITICAL: Re-raise the exception so Celery knows the task failed and can retry
        raise


@router.post("/{document_id}/analyze")
async def analyze_document(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Trigger document analysis in the background using GPT-4o.
    Returns immediately while analysis happens in a background thread.

    The analysis extracts:
    - Executive summary
    - Research problem
    - Methodology
    - Key findings
    - Results
    - Limitations
    - Future work
    - Key citations

    Check document status to monitor progress:
    - 'analyzing': Analysis in progress
    - 'analyzed': Analysis complete (check analysis field)
    - 'failed': Analysis failed (check metadata.error)
    """
    print(f"[ANALYZE] Triggering analysis for document_id={document_id}, user_id={user_id}")

    # Phase 3.3: Use Celery task instead of ThreadPoolExecutor
    from app.tasks.document_analysis import analyze_document_task
    from app.services.quota_management import check_quota, QuotaExceededError

    try:
        # CHECK QUOTA BEFORE PROCESSING
        try:
            await check_quota(user_id, "document")
        except QuotaExceededError as qe:
            raise_api_error(
                429,
                code="quota_exceeded",
                title="Document quota reached",
                message=str(qe),
                next_action="upgrade",
                retryable=False,
                quota_type=qe.quota_type,
                limit=qe.limit,
                current=qe.current,
            )
        # 1. Fetch document record
        doc_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

        if not doc_response.data:
            raise_api_error(
                404,
                code="document_not_found",
                title="Document not found",
                message="We couldn't find that PDF in your workspace.",
                next_action="refresh",
            )

        document = doc_response.data[0]
        project_id = document.get("project_id", "")
        print(f"[ANALYZE] Found document: {document.get('title')}")

        # 2. Check if already analyzed
        if document.get("analysis"):
            return {
                "message": "Document already analyzed",
                "document_id": document_id,
                "status": "analyzed",
                "analysis": document.get("analysis")
            }

        # 3. Check if already analyzing
        if document.get("status") == "analyzing":
            return {
                "message": "Analysis already in progress",
                "document_id": document_id,
                "status": "analyzing",
                "progress": get_progress_snapshot("document", document_id),
            }

        # 4. Validate file URL exists
        file_url = document.get("file_url")
        if not file_url:
            raise_api_error(
                400,
                code="file_parse_failed",
                title="PDF missing",
                message="This document doesn't have a valid PDF file attached.",
                next_action="fix_file",
            )

        # 5. Update status to 'analyzing'
        task_result = analyze_document_task.delay(document_id, user_id, project_id)
        queued_progress = store_progress_snapshot("document", document_id, "queued", 5, "Queued for analysis")
        supabase.table("documents").update({
            "status": "analyzing",
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": _merge_metadata(document.get("metadata"), analysis_task_id=task_result.id, error_detail=None),
        }).eq("id", document_id).execute()

        print(f"[ANALYZE] Celery analysis task submitted for document_id={document_id} (task_id={task_result.id})")

        return {
            "message": "Analysis started in background",
            "document_id": document_id,
            "status": "analyzing",
            "estimated_time_seconds": 25,
            "task_id": task_result.id,
            "progress": queued_progress,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANALYZE] ERROR: {type(e).__name__}: {str(e)}")
        raise_api_error(
            500,
            code="analysis_start_failed",
            title="Couldn't start analysis",
            message="We couldn't queue this PDF for analysis right now.",
            details=[str(e)] if str(e) else None,
            next_action="retry",
            retryable=True,
        )


@router.post("/{document_id}/resolve")
async def resolve_document(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Re-trigger the BibTeX resolution pipeline for a stuck imported document.

    A document is considered 'stuck' when status='imported' and resolution_status is null.
    This happens with legacy documents imported before the resolution pipeline existed,
    or when the Celery task failed silently.

    The resolution pipeline:
    1. Searches arXiv / Semantic Scholar / Unpaywall for an open-access PDF
    2. If found: downloads → GROBID → GPT-5.2 analysis → RAG embed → status='analyzed'
    3. If not found: embeds title+abstract for basic RAG → resolution_status='unresolved'
    """
    doc_res = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()
    if not doc_res.data:
        raise HTTPException(status_code=404, detail="Document not found")

    doc = doc_res.data[0]
    project_id = doc.get("project_id")

    if doc.get("resolution_status") == "resolving":
        return {"message": "Resolution already in progress", "document_id": document_id}

    # Mark as resolving so the UI updates immediately
    supabase.table("documents").update({
        "resolution_status": "resolving",
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", document_id).execute()

    # Kick off the resolution task
    from app.tasks.bibtex_resolution_task import resolve_bibtex_task
    task_result = resolve_bibtex_task.delay([document_id], user_id, project_id)

    logger.info(f"[RESOLVE] Triggered resolution for document_id={document_id} (task={task_result.id})")

    return {"message": "Resolution started", "document_id": document_id, "task_id": task_result.id}


@router.get("/{document_id}/file")
async def get_document_file(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Proxy the document file from Supabase Storage with authentication.
    This ensures users can only access their own documents.
    """
    from fastapi.responses import StreamingResponse
    import httpx

    print(f"[GET-FILE] Fetching file for document_id={document_id}, user_id={user_id}")

    # Get document metadata (include resolution_status to distinguish no-PDF entries)
    doc_response = supabase.table("documents").select("file_url, file_type, user_id, metadata, resolution_status").eq("id", document_id).eq("user_id", user_id).execute()

    if not doc_response.data:
        print(f"[GET-FILE] Document not found: {document_id}")
        raise HTTPException(status_code=404, detail="Document not found")

    document = doc_response.data[0]
    file_url = document.get("file_url")
    file_type = document.get("file_type", "application/pdf")
    resolution_status = document.get("resolution_status")

    print(f"[GET-FILE] file_url={file_url}, file_type={file_type}, resolution_status={resolution_status}")

    # Documents that were analyzed from metadata only (no open-access PDF was found or
    # storage upload failed) should return a descriptive 404 rather than a broken redirect.
    if resolution_status == "resolved_no_pdf" or not file_url:
        detail = (
            "PDF not stored — paper was analyzed from metadata only"
            if resolution_status == "resolved_no_pdf"
            else "Document file not found"
        )
        print(f"[GET-FILE] No PDF available: resolution_status={resolution_status}")
        raise HTTPException(status_code=404, detail=detail)

    # Extract storage path from file_url
    # URL format: https://.../storage/v1/object/public/documents/{path}
    try:
        path_parts = file_url.split("/documents/")
        if len(path_parts) < 2:
            raise ValueError(f"Invalid file URL format: {file_url}")

        storage_path = path_parts[1]
        print(f"[GET-FILE] storage_path={storage_path}")

        # Create a signed URL (valid for 1 hour)
        signed_url_response = supabase.storage.from_("documents").create_signed_url(storage_path, 3600)
        signed_url = signed_url_response.get("signedURL")

        if not signed_url:
            print(f"[GET-FILE] Failed to create signed URL: {signed_url_response}")
            raise HTTPException(status_code=500, detail="Failed to generate signed URL")

        print(f"[GET-FILE] Generated signed URL successfully")

        # Fetch the file from Supabase Storage using signed URL
        async with httpx.AsyncClient() as client:
            response = await client.get(signed_url)

            if response.status_code != 200:
                print(f"[GET-FILE] Failed to fetch file: status={response.status_code}")
                raise HTTPException(status_code=response.status_code, detail=f"Failed to fetch document file: {response.text}")

            print(f"[GET-FILE] File fetched successfully, size={len(response.content)} bytes")

            # Stream the file content
            return StreamingResponse(
                iter([response.content]),
                media_type=file_type,
                headers={
                    "Content-Disposition": f'inline; filename="{document_id}.pdf"',
                    "Access-Control-Allow-Origin": "*",
                }
            )
    except Exception as e:
        print(f"[GET-FILE] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch document file: {str(e)}")


@router.get("/{document_id}/export")
def export_document(
    document_id: str,
    format: str = Query("txt", pattern="^(txt|md|tex|pdf)$"),
    user_id: str = Depends(get_current_user),
):
    """Export a document analysis as plain text, markdown, LaTeX, or PDF."""
    from app.services.export import export_to_markdown, export_to_latex, export_to_text, markdown_to_pdf

    document_response = (
        supabase.table("documents")
        .select("id, title, status, analysis, metadata")
        .eq("id", document_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not document_response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    document = document_response.data[0]
    analysis = document.get("analysis")
    if not analysis:
        raise HTTPException(status_code=400, detail="Document has no analysis to export")

    document_title = document.get("title") or "Document Analysis"
    safe_filename = _sanitize_filename(document_title)
    export_metadata = {
        "status": document.get("status"),
        "document_id": document.get("id"),
    }
    markdown_content = _serialize_document_analysis(analysis, document_title)

    if format == "txt":
        text_content = export_to_text(markdown_content, title=document_title, metadata=export_metadata)
        return Response(
            content=text_content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}.txt"'},
        )

    if format == "md":
        markdown_export = export_to_markdown(markdown_content, export_metadata)
        return Response(
            content=markdown_export,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}.md"'},
        )

    if format == "tex":
        latex_content = export_to_latex(markdown_content, export_metadata)
        return Response(
            content=latex_content,
            media_type="application/x-latex",
            headers={"Content-Disposition": f'attachment; filename="{safe_filename}.tex"'},
        )

    pdf_bytes = markdown_to_pdf(markdown_content, export_metadata)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_filename}.pdf"'},
    )


@router.get("/{document_id}/signed-url")
def get_document_signed_url(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Return a short-lived Supabase signed URL for the document's PDF.
    Use this instead of opening file_url directly (bucket may be private).
    """
    doc_response = supabase.table("documents").select("file_url, user_id, resolution_status").eq("id", document_id).eq("user_id", user_id).execute()

    if not doc_response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    document = doc_response.data[0]
    file_url = document.get("file_url")
    resolution_status = document.get("resolution_status")

    if resolution_status == "resolved_no_pdf" or not file_url:
        raise HTTPException(status_code=404, detail="PDF not stored — paper was analyzed from metadata only")

    # Extract storage path from the public URL
    # Format: https://.../storage/v1/object/public/documents/{path}
    try:
        path_parts = file_url.split("/documents/")
        if len(path_parts) < 2:
            raise ValueError(f"Invalid file URL format: {file_url}")
        storage_path = path_parts[1]

        signed_url_response = supabase.storage.from_("documents").create_signed_url(storage_path, 3600)
        signed_url = signed_url_response.get("signedURL")

        if not signed_url:
            raise HTTPException(status_code=500, detail="Failed to generate signed URL")

        return {"signed_url": signed_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate signed URL: {str(e)}")


@router.get("/{document_id}/analysis")
def get_document_analysis(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Get the analysis for a document.
    Returns the structured analysis if available, or status if still processing.
    """
    print(f"[GET-ANALYSIS] Fetching analysis for document_id={document_id}")

    try:
        # Fetch document with analysis
        doc_response = supabase.table("documents").select("id, title, status, analysis, metadata").eq("id", document_id).eq("user_id", user_id).execute()

        if not doc_response.data:
            raise_api_error(
                404,
                code="document_not_found",
                title="Document not found",
                message="We couldn't find that PDF in your workspace.",
                next_action="refresh",
            )

        document = doc_response.data[0]
        status = document.get("status", "uploaded")

        if status == "analyzed" and document.get("analysis"):
            return {
                "status": "analyzed",
                "document_id": document_id,
                "document_title": document.get("title"),
                "analysis": document.get("analysis")
            }
        elif status == "analyzing":
            return {
                "status": "analyzing",
                "document_id": document_id,
                "document_title": document.get("title"),
                "message": "Analysis in progress",
                "progress": get_progress_snapshot("document", document_id),
            }
        elif status == "failed":
            metadata = document.get("metadata") or {}
            error_info = metadata.get("error", "Unknown error")
            return {
                "status": "failed",
                "document_id": document_id,
                "document_title": document.get("title"),
                "error": error_info,
                "error_detail": metadata.get("error_detail"),
            }
        else:
            return {
                "status": "not_analyzed",
                "document_id": document_id,
                "document_title": document.get("title"),
                "message": "Document has not been analyzed yet"
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[GET-ANALYSIS] ERROR: {type(e).__name__}: {str(e)}")
        raise_api_error(
            500,
            code="analysis_fetch_failed",
            title="Couldn't load analysis",
            message="We couldn't load this document analysis right now.",
            details=[str(e)] if str(e) else None,
            next_action="retry",
            retryable=True,
        )


# NOTE: BibTeX export endpoint moved to projects.py router
# The route /projects/{project_id}/export-bibtex is now at /{project_id}/export-bibtex in projects router
