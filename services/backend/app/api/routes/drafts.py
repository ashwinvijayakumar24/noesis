"""
Drafts API Endpoints

Provides endpoints for managing research drafts (user's own papers).
Drafts are uploaded for analysis, claim extraction, coverage gap detection, and reviewer feedback.

Requirements: 1.1, 1.3, 1.5
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, Query, Request
from fastapi.responses import Response
from app.core.supabase_client import supabase
from app.services.draft_processing import ingest_draft, validate_file_format
from app.services.draft_export import export_draft_analysis_as_pdf
from app.services.draft_errors import DraftProcessingError
from app.core.security_middleware import SecureAuthValidator, limiter
from typing import Optional
import datetime
import uuid
import logging

router = APIRouter()

# Set up logging
logger = logging.getLogger(__name__)


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    """Extract and validate user from Authorization header"""
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
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


@router.post("/upload")
@limiter.limit("5/minute")  # Max 5 draft uploads per minute
async def upload_draft(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user)
):
    """
    Upload a research draft file (PDF, DOCX, or TXT).

    Files are validated before upload to provide immediate feedback on issues.
    Supported formats: PDF (.pdf), Word (.docx), Plain Text (.txt)
    Maximum file size: 100MB
    Rate limit: 5 uploads per minute per IP address

    The draft will be:
    1. Validated for format and extractability
    2. Uploaded to Supabase Storage (drafts/{user_id}/{filename})
    3. Stored with metadata in the drafts table
    4. Ready for analysis via POST /drafts/{draft_id}/analyze

    Returns:
        Draft metadata with ID for subsequent analysis
    """
    print(f"[DRAFT-UPLOAD] Received: file={file.filename}, project_id={project_id}, title={title}, user_id={user_id}")

    try:
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Determine file type from extension
        file_extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''

        if file_extension not in ['pdf', 'docx', 'txt']:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "Unsupported file format",
                    "message": f"File format '.{file_extension}' is not supported",
                    "suggestions": [
                        "Supported formats: PDF (.pdf), Word (.docx), Plain Text (.txt)",
                        "Convert your file to one of these formats",
                        "For Google Docs: File → Download → Microsoft Word (.docx) or PDF"
                    ]
                }
            )

        # Validate file before upload
        print(f"[DRAFT-UPLOAD] Validating {file_extension} file ({file_size} bytes)")
        validation_result = await validate_file_format(file_content, file_extension)

        if not validation_result["valid"]:
            # Return detailed validation errors
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "File validation failed",
                    "validation_errors": validation_result["errors"],
                    "suggestions": validation_result["suggestions"]
                }
            )

        print(f"[DRAFT-UPLOAD] Validation passed, can_extract_text={validation_result['can_extract_text']}")

        # Generate unique filename to avoid conflicts
        base_name = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename
        unique_filename = f"{base_name}_{uuid.uuid4().hex[:8]}.{file_extension}"
        storage_path = f"{user_id}/{unique_filename}"

        # Upload to Supabase Storage "drafts" bucket with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"[DRAFT-UPLOAD] Attempting upload (try {attempt + 1}/{max_retries}) to path: {storage_path}")
                storage_response = supabase.storage.from_("drafts").upload(
                    path=storage_path,
                    file=file_content,
                    file_options={"content-type": file.content_type or "application/octet-stream"}
                )
                print(f"[DRAFT-UPLOAD] Upload successful: {storage_response}")
                break
            except Exception as upload_error:
                print(f"[DRAFT-UPLOAD] Upload attempt {attempt + 1} failed: {type(upload_error).__name__}: {str(upload_error)}")
                if attempt < max_retries - 1:
                    import time, random
                    time.sleep(1 + random.random())  # Wait 1-2 seconds before retry
                else:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to upload file to storage after {max_retries} attempts: {str(upload_error)}"
                    )

        # Get public URL for the file
        file_url = supabase.storage.from_("drafts").get_public_url(storage_path)

        # Determine version number (increment if draft with same title exists)
        version = 1
        if project_id and title:
            # Check for existing drafts with same title in project
            existing_drafts = supabase.table("drafts").select("version")\
                .eq("project_id", project_id)\
                .eq("title", title or file.filename)\
                .order("version", desc=True)\
                .limit(1)\
                .execute()

            if existing_drafts.data:
                version = existing_drafts.data[0]["version"] + 1

        # Create metadata entry in drafts table
        # Phase 2.3: Auto-analyze on upload (status starts as "processing" not "uploaded")
        draft_entry = {
            "user_id": user_id,
            "project_id": project_id,
            "title": title or file.filename,
            "version": version,
            "file_url": file_url,
            "file_type": file_extension,
            "file_size": file_size,
            "status": "processing",  # Changed from "uploaded" to auto-trigger analysis
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        }

        db_response = supabase.table("drafts").insert(draft_entry).execute()

        if not db_response.data:
            # If metadata creation fails, try to delete the uploaded file
            try:
                supabase.storage.from_("drafts").remove([storage_path])
            except:
                pass
            raise HTTPException(status_code=400, detail="Failed to create draft metadata")

        draft = db_response.data[0]
        draft_id = draft['id']
        print(f"[DRAFT-UPLOAD] Draft created: id={draft_id}, version={draft.get('version')}, project_id={draft.get('project_id')}")

        # Phase 2.3 & 3.3: Auto-trigger analysis using Celery task
        from app.tasks.draft_analysis import analyze_draft_task
        task_result = analyze_draft_task.delay(draft_id, project_id or "")
        print(f"[DRAFT-UPLOAD] ✓ Auto-analysis triggered for draft_id={draft_id} (task_id={task_result.id})")

        return {
            "message": "Draft uploaded successfully. Analysis will complete in about 60 seconds.",
            "draft": draft
        }

    except HTTPException:
        raise
    except DraftProcessingError as e:
        # Handle our custom draft processing errors
        raise HTTPException(status_code=400, detail=e.to_dict())
    except Exception as e:
        print(f"[DRAFT-UPLOAD] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/")
def list_drafts(
    project_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100, description="Number of drafts to return (max 100)"),
    offset: int = Query(0, ge=0, description="Number of drafts to skip"),
    user_id: str = Depends(get_current_user)
):
    """
    List all drafts for the authenticated user with pagination.
    Optionally filter by project_id.

    Pagination:
    - limit: Number of drafts to return (default: 50, max: 100)
    - offset: Number of drafts to skip (default: 0)
    - Returns total count and has_more flag

    Returns drafts ordered by created_at (newest first).
    """
    print(f"[DRAFT-LIST] user_id={user_id}, project_id={project_id}, limit={limit}, offset={offset}")

    # Get total count for pagination
    count_query = supabase.table("drafts").select("id", count="exact").eq("user_id", user_id)
    if project_id:
        count_query = count_query.eq("project_id", project_id)
    count_response = count_query.execute()
    total = count_response.count if hasattr(count_response, 'count') else 0

    # Get paginated results
    query = supabase.table("drafts").select("*").eq("user_id", user_id)
    if project_id:
        query = query.eq("project_id", project_id)

    response = query.order("created_at", desc=True).range(offset, offset + limit - 1).execute()
    print(f"[DRAFT-LIST] Found {len(response.data) if response.data else 0} drafts (total: {total})")

    return {
        "drafts": response.data,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }
    }


@router.get("/projects/{project_id}/drafts")
def list_project_drafts(project_id: str, user_id: str = Depends(get_current_user)):
    """
    List all drafts for a specific project.
    Ordered by version (newest first).
    """
    # Verify project exists and belongs to user
    project_res = supabase.table("projects").select("id").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    response = supabase.table("drafts").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("version", desc=True)\
        .execute()

    return response.data


@router.get("/{draft_id}/signed-url")
def get_draft_signed_url(
    draft_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get a signed URL for accessing the draft file.
    Signed URLs provide temporary authenticated access to private storage buckets.
    URL expires after 1 hour (3600 seconds).
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    # Fetch draft to get file_url and verify ownership
    draft_response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).execute()

    if not draft_response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft = draft_response.data[0]
    file_url = draft.get("file_url")

    if not file_url:
        raise HTTPException(status_code=400, detail="Draft has no file URL")

    # Extract storage path from file_url
    storage_path = None
    if "/drafts/" in file_url:
        path_parts = file_url.split("/drafts/")
        if len(path_parts) >= 2:
            storage_path = path_parts[1]

    if not storage_path:
        raise HTTPException(status_code=400, detail="Could not extract storage path from file URL")

    try:
        # Create signed URL that expires in 1 hour (3600 seconds)
        signed_url_response = supabase.storage.from_("drafts").create_signed_url(storage_path, 3600)
        signed_url = signed_url_response.get("signedURL")

        if not signed_url:
            raise HTTPException(status_code=500, detail="Failed to create signed URL")

        return {
            "signed_url": signed_url,
            "expires_in": 3600
        }
    except Exception as e:
        logger.error(f"Failed to create signed URL for draft {draft_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create signed URL: {str(e)}")


@router.get("/{draft_id}")
def get_draft(draft_id: str, user_id: str = Depends(get_current_user)):
    """
    Get a single draft by ID with all metadata.

    Returns draft with status:
    - uploaded: Ready for analysis
    - processing: Analysis in progress
    - analyzed: Analysis complete (includes structure data)
    - failed: Analysis failed (check metadata for error)
    """
    response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    return response.data[0]


@router.put("/{draft_id}")
def update_draft(
    draft_id: str,
    title: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Update draft metadata (title only).

    Note: To upload a new version, use POST /drafts/upload with the same title.
    """
    updates = {"updated_at": datetime.datetime.utcnow().isoformat()}

    if title:
        updates["title"] = title

    response = supabase.table("drafts").update(updates).eq("id", draft_id).eq("user_id", user_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    return {"message": "Draft updated", "draft": response.data[0]}


@router.delete("/{draft_id}")
def delete_draft(draft_id: str, user_id: str = Depends(get_current_user)):
    """
    Delete a draft and its associated file from storage.
    Also deletes:
    - Draft analysis data
    - Draft chunks from vector database
    - Claims, gaps, and feedback (cascade delete)
    """
    print(f"[DRAFT-DELETE] Starting deletion for draft_id={draft_id}, user_id={user_id}")

    # First, get the draft to find the file path
    draft_response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).execute()

    if not draft_response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft = draft_response.data[0]
    print(f"[DRAFT-DELETE] Found draft: title={draft.get('title')}, file_url={draft.get('file_url')}")

    # Extract storage path from file_url
    file_url = draft.get("file_url", "")
    storage_path = None

    if file_url and "/drafts/" in file_url:
        path_parts = file_url.split("/drafts/")
        if len(path_parts) >= 2:
            storage_path = path_parts[1]
            print(f"[DRAFT-DELETE] Extracted storage path: {storage_path}")

    # Delete from storage if we have a valid path
    if storage_path:
        try:
            print(f"[DRAFT-DELETE] Attempting to delete file from storage: {storage_path}")
            supabase.storage.from_("drafts").remove([storage_path])
            print(f"[DRAFT-DELETE] Successfully deleted file from storage")
        except Exception as e:
            print(f"[DRAFT-DELETE] Warning: Failed to delete file from storage: {type(e).__name__}: {str(e)}")
    else:
        print(f"[DRAFT-DELETE] Warning: Could not extract storage path from file_url: {file_url}")

    # Delete draft chunks from vector database (cascading should handle this)
    try:
        print(f"[DRAFT-DELETE] Deleting draft chunks for draft_id={draft_id}")
        chunks_response = supabase.table("draft_chunks").delete().eq("draft_id", draft_id).execute()
        chunks_count = len(chunks_response.data) if chunks_response.data else 0
        print(f"[DRAFT-DELETE] Deleted {chunks_count} draft chunks")
    except Exception as e:
        print(f"[DRAFT-DELETE] Warning: Failed to delete draft chunks: {type(e).__name__}: {str(e)}")

    # Delete from database (CASCADE will delete draft_analysis, draft_claims, coverage_gaps, reviewer_feedback)
    print(f"[DRAFT-DELETE] Deleting draft record from database")
    db_response = supabase.table("drafts").delete().eq("id", draft_id).eq("user_id", user_id).execute()

    if not db_response.data:
        raise HTTPException(status_code=404, detail="Failed to delete draft")

    print(f"[DRAFT-DELETE] Successfully deleted draft {draft_id}")
    return {"message": "Draft deleted successfully"}


def _run_draft_analysis_task(draft_id: str, project_id: str):
    """
    Background task that performs draft analysis using LangGraph workflow.
    Runs in a separate thread to avoid blocking the API.

    Steps:
    1. Download draft from storage
    2. Extract text based on file type
    3. Run complete LangGraph workflow (structure → claims → search → citations → gaps → feedback → synthesis)
    4. Store all analysis results in database
    5. Update draft status
    6. Track quota usage and OpenAI costs
    """
    import asyncio
    import traceback
    from app.services.quota_management import increment_quota_usage, track_openai_usage
    from app.services.draft_analysis_langgraph import analyze_draft_with_langgraph

    try:
        print(f"[DRAFT-ANALYZE-BG-LG] ========== STARTING BACKGROUND TASK ==========")
        print(f"[DRAFT-ANALYZE-BG-LG] draft_id={draft_id}, project_id={project_id}")

        # Get draft info
        print(f"[DRAFT-ANALYZE-BG-LG] Fetching draft record from database...")
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).execute()
        if not draft_response.data:
            raise ValueError(f"Draft {draft_id} not found")

        draft = draft_response.data[0]
        user_id = draft["user_id"]
        file_url = draft.get("file_url")
        print(f"[DRAFT-ANALYZE-BG-LG] Found draft: user_id={user_id}, file_url={file_url}")

        # Download and extract text from draft
        # First, ingest the draft to get the text content
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Ingest draft (extract text, chunk, embed)
        print(f"[DRAFT-ANALYZE-BG-LG] ========== STEP 1: INGESTING DRAFT ==========")
        try:
            ingest_result = loop.run_until_complete(ingest_draft(draft_id, project_id))
            print(f"[DRAFT-ANALYZE-BG-LG] ✓ Draft ingested successfully: {ingest_result.get('message', 'Success')}")
        except Exception as ingest_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ INGEST FAILED: {type(ingest_error).__name__}: {str(ingest_error)}")
            print(f"[DRAFT-ANALYZE-BG-LG] Stack trace:")
            print(traceback.format_exc())
            # ingest_draft already updates status to 'failed', so we can re-raise
            raise

        # Get the extracted content
        # The ingest_draft function should have stored the full_text in draft_chunks or metadata
        # For now, let's re-extract the text directly
        print(f"[DRAFT-ANALYZE-BG-LG] ========== STEP 2: EXTRACTING TEXT FOR LANGGRAPH ==========")

        # Extract storage path from file_url
        storage_path = None
        if file_url and "/drafts/" in file_url:
            path_parts = file_url.split("/drafts/")
            if len(path_parts) >= 2:
                storage_path = path_parts[1]
                print(f"[DRAFT-ANALYZE-BG-LG] Extracted storage path: {storage_path}")

        if not storage_path:
            error_msg = f"Could not extract storage path from file_url: {file_url}"
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ ERROR: {error_msg}")
            raise ValueError(error_msg)

        # Download file bytes
        print(f"[DRAFT-ANALYZE-BG-LG] Downloading file from storage...")
        try:
            file_bytes = supabase.storage.from_("drafts").download(storage_path)
            if not file_bytes:
                raise ValueError("Downloaded file is empty")
            print(f"[DRAFT-ANALYZE-BG-LG] ✓ Downloaded {len(file_bytes)} bytes")
        except Exception as download_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ DOWNLOAD FAILED: {type(download_error).__name__}: {str(download_error)}")
            raise ValueError(f"Failed to download draft file: {str(download_error)}")

        # Extract text based on file type
        file_type = draft.get("file_type", "").lower()
        print(f"[DRAFT-ANALYZE-BG-LG] Extracting text from {file_type} file...")
        try:
            if file_type == "pdf" or storage_path.endswith(".pdf"):
                from app.services.rag_ingest import extract_text_from_pdf_fallback
                draft_content = extract_text_from_pdf_fallback(file_bytes)
            elif file_type in ["docx", "doc"] or storage_path.endswith((".docx", ".doc")):
                import docx
                import io
                doc = docx.Document(io.BytesIO(file_bytes))
                draft_content = "\n\n".join([paragraph.text for paragraph in doc.paragraphs])
            elif file_type == "txt" or storage_path.endswith(".txt"):
                draft_content = file_bytes.decode("utf-8")
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

            print(f"[DRAFT-ANALYZE-BG-LG] ✓ Extracted {len(draft_content)} characters of text")
        except Exception as extract_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ TEXT EXTRACTION FAILED: {type(extract_error).__name__}: {str(extract_error)}")
            print(f"[DRAFT-ANALYZE-BG-LG] Stack trace:")
            print(traceback.format_exc())
            raise

        # Run the LangGraph workflow
        print(f"[DRAFT-ANALYZE-BG-LG] ========== STEP 3: RUNNING LANGGRAPH WORKFLOW ==========")
        try:
            result = loop.run_until_complete(
                analyze_draft_with_langgraph(
                    draft_id=draft_id,
                    project_id=project_id,
                    user_id=user_id,
                    draft_content=draft_content
                )
            )
            print(f"[DRAFT-ANALYZE-BG-LG] ✓ LangGraph workflow completed successfully!")
            print(f"[DRAFT-ANALYZE-BG-LG] Results: {result.get('message', 'Success')}")
            print(f"[DRAFT-ANALYZE-BG-LG] Summary: {result.get('results', {})}")
        except Exception as langgraph_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ LANGGRAPH WORKFLOW FAILED!")
            print(f"[DRAFT-ANALYZE-BG-LG] Error type: {type(langgraph_error).__name__}")
            print(f"[DRAFT-ANALYZE-BG-LG] Error message: {str(langgraph_error)}")
            print(f"[DRAFT-ANALYZE-BG-LG] Full stack trace:")
            print(traceback.format_exc())

            # CRITICAL: Update draft status to 'failed' since LangGraph workflow failed
            # ingest_draft succeeded (status='analyzed'), but LangGraph failed
            print(f"[DRAFT-ANALYZE-BG-LG] Updating draft status to 'failed'...")
            print(f"[DRAFT-ANALYZE-BG-LG] Error: {str(langgraph_error)}")
            try:
                supabase.table("drafts").update({
                    "status": "failed",
                    "updated_at": datetime.datetime.utcnow().isoformat()
                }).eq("id", draft_id).execute()
                print(f"[DRAFT-ANALYZE-BG-LG] ✓ Draft status updated to 'failed'")
            except Exception as update_error:
                print(f"[DRAFT-ANALYZE-BG-LG] ✗ Failed to update draft status: {update_error}")

            raise

        loop.close()

        # Track quota usage and OpenAI costs
        print(f"[DRAFT-ANALYZE-BG-LG] ========== STEP 4: TRACKING USAGE ==========")
        try:
            # Increment quota counter
            asyncio.run(increment_quota_usage(user_id, "draft"))
            print(f"[DRAFT-ANALYZE-BG-LG] ✓ Quota incremented for user_id={user_id}")

            # Track OpenAI usage
            # Note: Draft analysis involves multiple AI operations (structure analysis, claim extraction,
            # coverage detection, reviewer feedback). For now, we track it as a single "draft_analysis"
            # operation. In the future, we could track each sub-operation separately.
            try:
                # Get analysis metadata to extract token usage if available
                analysis_response = supabase.table("draft_analysis")\
                    .select("analysis_metadata")\
                    .eq("draft_id", draft_id)\
                    .execute()

                if analysis_response.data:
                    metadata = analysis_response.data[0].get("analysis_metadata", {})

                    # Track the main structure analysis operation
                    # Note: This only captures structure analysis tokens. Claim/coverage/feedback
                    # operations use separate OpenAI calls that should ideally be tracked separately.
                    asyncio.run(track_openai_usage(
                        user_id=user_id,
                        operation_type="draft_analysis",
                        model="gpt-4o-mini",  # Structure analysis uses mini
                        prompt_tokens=800,  # Estimated (structure analysis uses ~8000 chars)
                        completion_tokens=200,  # Estimated (structure JSON response)
                        project_id=project_id,
                        draft_id=draft_id
                    ))
                    print(f"[DRAFT-ANALYZE-BG-LG] ✓ OpenAI usage tracked")
            except Exception as tracking_error:
                print(f"[DRAFT-ANALYZE-BG-LG] WARNING: Failed to track OpenAI usage: {tracking_error}")
                # Don't fail on tracking errors

        except Exception as tracking_error:
            # Don't fail the analysis if tracking fails
            print(f"[DRAFT-ANALYZE-BG-LG] WARNING: Failed to track quota/usage: {tracking_error}")

        print(f"[DRAFT-ANALYZE-BG-LG] ========== BACKGROUND TASK COMPLETED SUCCESSFULLY ==========")

    except Exception as e:
        print(f"[DRAFT-ANALYZE-BG-LG] ========== BACKGROUND TASK FAILED ==========")
        print(f"[DRAFT-ANALYZE-BG-LG] Error type: {type(e).__name__}")
        print(f"[DRAFT-ANALYZE-BG-LG] Error message: {str(e)}")
        print(f"[DRAFT-ANALYZE-BG-LG] Full stack trace:")
        print(traceback.format_exc())

        # Make sure draft status is set to 'failed' if not already done
        try:
            print(f"[DRAFT-ANALYZE-BG-LG] Ensuring draft status is 'failed'...")
            print(f"[DRAFT-ANALYZE-BG-LG] Error was: {type(e).__name__}: {str(e)}")
            supabase.table("drafts").update({
                "status": "failed",
                "updated_at": datetime.datetime.utcnow().isoformat()
            }).eq("id", draft_id).execute()
            print(f"[DRAFT-ANALYZE-BG-LG] ✓ Draft status updated to 'failed'")
        except Exception as update_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ Failed to update draft status: {update_error}")


@router.post("/{draft_id}/analyze")
async def analyze_draft(draft_id: str, user_id: str = Depends(get_current_user)):
    """
    Trigger draft analysis in the background.
    Returns immediately while analysis happens in a background thread.

    The analysis extracts:
    - Document structure (sections, paragraphs)
    - Word count and metadata
    - Section types (abstract, intro, methods, results, discussion, conclusion)

    Check draft status to monitor progress:
    - 'processing': Analysis in progress
    - 'analyzed': Analysis complete (check draft_analysis table)
    - 'failed': Analysis failed
    """
    print(f"[DRAFT-ANALYZE] ========== ANALYZE ENDPOINT CALLED ==========")
    print(f"[DRAFT-ANALYZE] draft_id={draft_id}, user_id={user_id}")
    print(f"[DRAFT-ANALYZE] Endpoint hit at: {datetime.datetime.utcnow().isoformat()}")

    # Phase 3.3: Use Celery task instead of ThreadPoolExecutor
    from app.tasks.draft_analysis import analyze_draft_task
    from app.services.quota_management import check_quota, QuotaExceededError

    try:
        # CHECK QUOTA BEFORE PROCESSING
        try:
            await check_quota(user_id, "draft")
            print(f"[DRAFT-ANALYZE] Quota check passed for user_id={user_id}")
        except QuotaExceededError as qe:
            print(f"[DRAFT-ANALYZE] Quota exceeded for user_id={user_id}: {qe}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "quota_exceeded",
                    "message": str(qe),
                    "quota_type": qe.quota_type,
                    "limit": qe.limit,
                    "current": qe.current
                }
            )

        # Fetch draft record
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        draft = draft_response.data[0]
        print(f"[DRAFT-ANALYZE] Found draft: {draft.get('title')}")

        # Check if already analyzed
        analysis_response = supabase.table("draft_analysis").select("*").eq("draft_id", draft_id).execute()
        if analysis_response.data:
            return {
                "message": "Draft already analyzed",
                "draft_id": draft_id,
                "status": "analyzed",
                "analysis": analysis_response.data[0]
            }

        # Check if already processing
        if draft.get("status") == "processing":
            return {
                "message": "Analysis already in progress",
                "draft_id": draft_id,
                "status": "processing"
            }

        # Validate file URL exists
        file_url = draft.get("file_url")
        if not file_url:
            raise HTTPException(status_code=400, detail="Draft has no file URL")

        project_id = draft.get("project_id")
        if not project_id:
            raise HTTPException(status_code=400, detail="Draft must be associated with a project")

        # Submit Celery task
        task_result = analyze_draft_task.delay(draft_id, project_id)

        print(f"[DRAFT-ANALYZE] Celery analysis task submitted for draft_id={draft_id} (task_id={task_result.id})")

        return {
            "message": "Analysis started in background",
            "draft_id": draft_id,
            "status": "processing",
            "estimated_time_seconds": 10
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DRAFT-ANALYZE] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")


@router.get("/{draft_id}/analysis")
def get_draft_analysis(draft_id: str, user_id: str = Depends(get_current_user)):
    """
    Get the structural analysis for a draft.
    Returns the analysis if available, or status if still processing.
    """
    print(f"[DRAFT-GET-ANALYSIS] Fetching analysis for draft_id={draft_id}")

    try:
        # Fetch draft
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        draft = draft_response.data[0]
        status = draft.get("status", "uploaded")

        # Fetch analysis if it exists
        analysis_response = supabase.table("draft_analysis").select("*").eq("draft_id", draft_id).execute()

        if status == "analyzed" and analysis_response.data:
            return {
                "status": "analyzed",
                "draft_id": draft_id,
                "draft_title": draft.get("title"),
                "analysis": analysis_response.data[0]
            }
        elif status == "processing":
            return {
                "status": "processing",
                "draft_id": draft_id,
                "draft_title": draft.get("title"),
                "message": "Analysis in progress"
            }
        elif status == "failed":
            return {
                "status": "failed",
                "draft_id": draft_id,
                "draft_title": draft.get("title"),
                "message": "Analysis failed"
            }
        else:
            return {
                "status": "not_analyzed",
                "draft_id": draft_id,
                "draft_title": draft.get("title"),
                "message": "Draft has not been analyzed yet"
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[DRAFT-GET-ANALYSIS] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch analysis: {str(e)}")


@router.get("/{draft_id}/claims")
def get_draft_claims(draft_id: str, user_id: str = Depends(get_current_user)):
    """
    Get extracted claims for a draft.

    Returns empty list if claims haven't been extracted yet.
    Claims are extracted in a later task (Task 5: Claim Analysis Service).
    """
    print(f"[DRAFT-CLAIMS] Fetching claims for draft_id={draft_id}, user_id={user_id}")

    # Verify draft belongs to user
    draft_response = supabase.table("drafts").select("id").eq("id", draft_id).eq("user_id", user_id).execute()
    print(f"[DRAFT-CLAIMS] Draft verification: {draft_response.data}")
    if not draft_response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Fetch claims
    print(f"[DRAFT-CLAIMS] Querying draft_claims table for draft_id={draft_id}")
    claims_response = supabase.table("draft_claims").select("*").eq("draft_id", draft_id).execute()
    print(f"[DRAFT-CLAIMS] Claims response: {claims_response}")
    print(f"[DRAFT-CLAIMS] Claims data: {claims_response.data}")
    print(f"[DRAFT-CLAIMS] Number of claims: {len(claims_response.data) if claims_response.data else 0}")

    return {
        "draft_id": draft_id,
        "claims": claims_response.data or [],
        "total_claims": len(claims_response.data) if claims_response.data else 0
    }


@router.get("/{draft_id}/gaps")
def get_draft_coverage_gaps(draft_id: str, user_id: str = Depends(get_current_user)):
    """
    Get coverage gaps identified for a draft.

    Returns empty list if gap analysis hasn't been run yet.
    Gap analysis is performed in a later task (Task 7: Coverage Gap Detection).
    """
    # Verify draft belongs to user
    draft_response = supabase.table("drafts").select("id").eq("id", draft_id).eq("user_id", user_id).execute()
    if not draft_response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Fetch coverage gaps
    gaps_response = supabase.table("coverage_gaps").select("*").eq("draft_id", draft_id).execute()

    return {
        "draft_id": draft_id,
        "gaps": gaps_response.data or [],
        "total_gaps": len(gaps_response.data) if gaps_response.data else 0
    }


@router.get("/{draft_id}/feedback")
def get_draft_feedback(draft_id: str, user_id: str = Depends(get_current_user)):
    """
    Get reviewer-style feedback for a draft.

    Returns empty list if feedback hasn't been generated yet.
    Feedback generation is performed in a later task (Task 9: Reviewer Feedback Engine).
    """
    # Verify draft belongs to user
    draft_response = supabase.table("drafts").select("id").eq("id", draft_id).eq("user_id", user_id).execute()
    if not draft_response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Fetch reviewer feedback
    feedback_response = supabase.table("reviewer_feedback").select("*").eq("draft_id", draft_id).execute()

    return {
        "draft_id": draft_id,
        "feedback": feedback_response.data or [],
        "total_feedback_items": len(feedback_response.data) if feedback_response.data else 0
    }


@router.get("/{draft_id}/export-pdf")
async def export_draft_analysis_pdf(
    draft_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Export draft analysis as a comprehensive PDF report.

    Returns:
        PDF file containing claims, coverage gaps, reviewer feedback, and citation suggestions
    """
    try:
        # Verify draft ownership
        draft = supabase.table("drafts")\
            .select("*")\
            .eq("id", draft_id)\
            .eq("user_id", user_id)\
            .single()\
            .execute()

        if not draft.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Fetch all analysis data from multiple tables
        claims = supabase.table("draft_claims")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .execute()

        gaps = supabase.table("coverage_gaps")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .execute()

        feedback = supabase.table("reviewer_feedback")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .execute()

        # Fetch citation suggestions with joined citation data
        citation_suggestions = supabase.table("citation_suggestions")\
            .select("*, citations(*)")\
            .eq("draft_id", draft_id)\
            .execute()

        # Combine all analysis data
        analysis_data = {
            "claims": claims.data or [],
            "coverage_gaps": gaps.data or [],
            "reviewer_feedback": feedback.data or [],
            "citation_suggestions": citation_suggestions.data or []
        }

        # Generate PDF
        draft_title = draft.data.get("title", "Untitled")
        pdf_bytes = export_draft_analysis_as_pdf(draft_id, draft_title, analysis_data)

        # Sanitize filename (remove special characters)
        safe_filename = "".join(c for c in draft_title if c.isalnum() or c in (' ', '_', '-')).strip()
        if not safe_filename:
            safe_filename = "draft_analysis"
        safe_filename = safe_filename.replace(' ', '_')

        # Return as downloadable PDF file
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}_analysis.pdf"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF export failed for draft {draft_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to export PDF: {str(e)}")
