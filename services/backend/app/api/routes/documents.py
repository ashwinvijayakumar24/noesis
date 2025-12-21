"""
Documents API Endpoints

Provides endpoints for managing research documents (separate from datasets).
Documents are PDFs that will be ingested into the RAG pipeline.
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form
from app.core.supabase_client import supabase
from typing import Optional
import datetime

router = APIRouter()


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables."
        )
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split("Bearer ")[-1]
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user)
):
    """
    Upload a document file to Supabase Storage and create metadata entry.
    Files are stored in user-specific folders: documents/{user_id}/{filename}
    """
    print(f"[UPLOAD] Received: file={file.filename}, project_id={project_id}, title={title}, user_id={user_id}")
    try:
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)

        # Generate storage path: documents/{user_id}/{filename}
        import time
        import random
        import uuid

        # Add unique suffix to avoid file name conflicts
        base_name = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename
        extension = file.filename.rsplit('.', 1)[1] if '.' in file.filename else ''
        unique_filename = f"{base_name}_{uuid.uuid4().hex[:8]}.{extension}" if extension else f"{base_name}_{uuid.uuid4().hex[:8]}"
        storage_path = f"{user_id}/{unique_filename}"

        # Upload to Supabase Storage with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                print(f"[UPLOAD] Attempting upload (try {attempt + 1}/{max_retries}) to path: {storage_path}")
                storage_response = supabase.storage.from_("documents").upload(
                    path=storage_path,
                    file=file_content,
                    file_options={"content-type": file.content_type or "application/octet-stream"}
                )
                print(f"[UPLOAD] Upload successful: {storage_response}")
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
            "title": title or file.filename,
            "description": description,
            "file_url": file_url,
            "file_type": file.content_type or "application/octet-stream",
            "file_size": file_size,
            "status": "uploaded",
            "metadata": {
                "original_filename": file.filename,
                "upload_timestamp": datetime.datetime.utcnow().isoformat()
            },
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat()
        }

        db_response = supabase.table("documents").insert(metadata_entry).execute()

        if not db_response.data:
            # If metadata creation fails, try to delete the uploaded file
            try:
                supabase.storage.from_("documents").remove([storage_path])
            except:
                pass
            raise HTTPException(status_code=400, detail="Failed to create document metadata")

        document = db_response.data[0]
        print(f"[UPLOAD] Document created: id={document['id']}, project_id={document.get('project_id')}")

        return {
            "message": "Document uploaded successfully",
            "document": document
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/")
def list_documents(project_id: Optional[str] = None, user_id: str = Depends(get_current_user)):
    """
    List all documents for the authenticated user.
    Optionally filter by project_id.
    """
    query = supabase.table("documents").select("*").eq("user_id", user_id)

    if project_id:
        query = query.eq("project_id", project_id)

    response = query.order("created_at", desc=True).execute()
    return response.data


@router.get("/{document_id}")
def get_document(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Get a single document by ID.
    """
    response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Document not found")

    return response.data[0]


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
    updates = {"updated_at": datetime.datetime.utcnow().isoformat()}

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
        raise HTTPException(status_code=404, detail="Document not found")

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
    return {"message": "Document deleted successfully"}


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
        "updated_at": datetime.datetime.utcnow().isoformat()
    }).eq("id", document_id).eq("user_id", user_id).execute()

    if not update_res.data:
        raise HTTPException(status_code=400, detail="Failed to attach document to project")

    return {
        "message": "Document attached to project successfully",
        "document": update_res.data[0]
    }


def _run_analysis_task(document_id: str, file_url: str):
    """
    Background task that performs the actual document analysis.
    This runs in a separate thread to avoid blocking the API.
    """
    from app.services.rag_ingest import extract_text_from_pdf
    from app.services.document_analysis import analyze_paper_text, validate_analysis

    try:
        print(f"[ANALYZE-BG] Starting background analysis for document_id={document_id}")

        # 1. Download PDF from storage using Supabase client (authenticated)
        print(f"[ANALYZE-BG] Downloading PDF from: {file_url}")

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

        # 2. Extract text from PDF
        print(f"[ANALYZE-BG] Extracting text from PDF")
        paper_text = extract_text_from_pdf(pdf_bytes)
        print(f"[ANALYZE-BG] Extracted {len(paper_text)} characters of text")

        if len(paper_text) < 100:
            raise Exception("Extracted text is too short. PDF might be scanned or corrupted.")

        # 3. Run GPT-4o analysis
        print(f"[ANALYZE-BG] Running GPT-4o analysis")
        analysis = analyze_paper_text(paper_text, model="gpt-4o")

        # 4. Extract citation metadata for literature reviews
        print(f"[ANALYZE-BG] Extracting citation metadata")
        from app.services.document_analysis import extract_citation_metadata
        citation_metadata = extract_citation_metadata(paper_text)

        # Add citation metadata to analysis
        analysis['citation_metadata'] = citation_metadata

        # 5. Validate analysis
        validate_analysis(analysis)
        print(f"[ANALYZE-BG] Analysis completed and validated")

        # 6. Store analysis in database
        update_response = supabase.table("documents").update({
            "analysis": analysis,
            "status": "analyzed",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", document_id).execute()

        if not update_response.data:
            raise Exception("Failed to update document with analysis")

        # 7. Reset project insights status (since new document analyzed)
        # Get the document's project_id
        document = update_response.data[0]
        project_id = document.get("project_id")

        if project_id:
            print(f"[ANALYZE-BG] Resetting insights status for project_id={project_id}")
            # Check if project has insights
            project_res = supabase.table("projects").select("insights_status").eq("id", project_id).execute()
            if project_res.data and project_res.data[0].get("insights_status") in ["analyzed", "analyzing"]:
                # Reset to not_analyzed so user knows insights need to be regenerated
                supabase.table("projects").update({
                    "insights_status": "not_analyzed",
                    "updated_at": datetime.datetime.utcnow().isoformat()
                }).eq("id", project_id).execute()
                print(f"[ANALYZE-BG] Project insights status reset to not_analyzed")

        print(f"[ANALYZE-BG] Analysis stored successfully for document_id={document_id}")

    except Exception as e:
        # Update status to failed
        print(f"[ANALYZE-BG] ERROR for document_id={document_id}: {type(e).__name__}: {str(e)}")
        supabase.table("documents").update({
            "status": "failed",
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "metadata": {
                "error": str(e),
                "error_type": type(e).__name__
            }
        }).eq("id", document_id).execute()


@router.post("/{document_id}/analyze")
def analyze_document(document_id: str, user_id: str = Depends(get_current_user)):
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

    from app.services.background_tasks import submit_task

    try:
        # 1. Fetch document record
        doc_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

        if not doc_response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        document = doc_response.data[0]
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
                "status": "analyzing"
            }

        # 4. Validate file URL exists
        file_url = document.get("file_url")
        if not file_url:
            raise HTTPException(status_code=400, detail="Document has no file URL")

        # 5. Update status to 'analyzing'
        supabase.table("documents").update({
            "status": "analyzing",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", document_id).execute()

        # 6. Submit background task
        submit_task(_run_analysis_task, document_id, file_url)

        print(f"[ANALYZE] Background analysis task submitted for document_id={document_id}")

        return {
            "message": "Analysis started in background",
            "document_id": document_id,
            "status": "analyzing",
            "estimated_time_seconds": 25
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ANALYZE] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start analysis: {str(e)}")


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
            raise HTTPException(status_code=404, detail="Document not found")

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
                "message": "Analysis in progress"
            }
        elif status == "failed":
            error_info = document.get("metadata", {}).get("error", "Unknown error")
            return {
                "status": "failed",
                "document_id": document_id,
                "document_title": document.get("title"),
                "error": error_info
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
        raise HTTPException(status_code=500, detail=f"Failed to fetch analysis: {str(e)}")
