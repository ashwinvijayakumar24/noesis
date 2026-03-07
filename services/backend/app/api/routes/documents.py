"""
Documents API Endpoints

Provides endpoints for managing research documents (separate from datasets).
Documents are PDFs that will be ingested into the RAG pipeline.
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, Query, Request
from fastapi.responses import Response
from app.core.supabase_client import supabase
from app.services.citation_management import format_citation_bibtex
from app.core.security_middleware import SecureAuthValidator, limiter
from typing import Optional
from datetime import datetime
import logging

router = APIRouter()

# Set up logging
logger = logging.getLogger(__name__)


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
        logger.error(f"Token validation failed: {str(e)}")
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
                "upload_timestamp": datetime.utcnow().isoformat()
            },
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
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

    return {
        "data": response.data,
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
    from app.services.rag_ingest import extract_text_from_pdf_fallback, get_pdf_page_count
    from app.workflows.document_analysis.graph import run_document_analysis_workflow
    import asyncio
    from app.services.quota_management import increment_quota_usage, track_openai_usage
    from app.core.openai_client import get_openai_client, get_completion_params
    import os

    try:
        print(f"[ANALYZE-BG-LG] ========== STARTING LANGGRAPH ANALYSIS ==========")
        print(f"[ANALYZE-BG-LG] document_id={document_id}")

        # Get document to retrieve user_id for quota tracking
        doc_response = supabase.table("documents").select("user_id, project_id").eq("id", document_id).execute()
        if not doc_response.data:
            raise Exception("Document not found")
        user_id = doc_response.data[0]["user_id"]
        project_id = doc_response.data[0].get("project_id")

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

        # 2. Get page count from PDF
        print(f"[ANALYZE-BG-LG] Step 2: Getting page count from PDF")
        page_count = get_pdf_page_count(pdf_bytes)
        print(f"[ANALYZE-BG-LG] ✓ PDF has {page_count} pages")

        # 3. Extract text from PDF (using fallback for compatibility)
        print(f"[ANALYZE-BG-LG] Step 3: Extracting text from PDF")
        paper_text = extract_text_from_pdf_fallback(pdf_bytes)
        print(f"[ANALYZE-BG-LG] ✓ Extracted {len(paper_text)} characters of text")

        if len(paper_text) < 100:
            raise Exception("Extracted text is too short. PDF might be scanned or corrupted.")

        # 4. Run BOTH workflows in parallel for best of both worlds
        print(f"[ANALYZE-BG-LG] Step 4: Running dual analysis (LangGraph + Traditional)...")

        # 4a. Run traditional comprehensive analysis (for display quality)
        print(f"[ANALYZE-BG-LG] Step 4a: Running traditional GPT-4o analysis for narrative quality...")
        from app.services.document_analysis import analyze_paper_text, validate_analysis

        comprehensive_analysis = analyze_paper_text(paper_text, page_count=page_count, model="gpt-5.2-chat-latest")
        validate_analysis(comprehensive_analysis)
        print(f"[ANALYZE-BG-LG] ✓ Traditional analysis complete (high-quality narrative)")

        # 4b. Run LangGraph workflow for structured extraction (for citations)
        print(f"[ANALYZE-BG-LG] Step 4b: Running LangGraph workflow for structured extraction...")
        print(f"[ANALYZE-BG-LG] This will extract: claims, methods, findings for citation matching")

        # Create async loop for workflow execution
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        final_state = loop.run_until_complete(
            run_document_analysis_workflow(
                document_id=document_id,
                project_id=project_id,
                document_text=paper_text,
                page_count=page_count
            )
        )
        loop.close()

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

        # Get OpenAI client for generating embeddings
        client = get_openai_client()

        # 5.1 Store claims with embeddings
        claims = final_state.get("claims", [])
        if claims:
            print(f"[ANALYZE-BG-LG] Storing {len(claims)} claims...")
            # Generate embeddings for all claims
            claim_texts = [c["claim_text"] for c in claims]
            embeddings_response = client.embeddings.create(
                model="text-embedding-3-large",
                input=claim_texts,
                dimensions=1536
            )

            # Insert claims into database
            for i, claim in enumerate(claims):
                claim_row = {
                    "document_id": document_id,
                    "project_id": project_id,
                    "claim_text": claim["claim_text"],
                    "claim_type": claim["claim_type"],
                    "section_title": claim.get("section_title"),
                    "section_type": claim.get("section_type"),
                    "page_number": claim.get("page_number"),
                    "importance_score": claim["importance_score"],
                    "confidence_score": claim["confidence_score"],
                    "supports_primary_thesis": claim["supports_primary_thesis"],
                    "embedding": embeddings_response.data[i].embedding
                }
                supabase.table("document_claims").insert(claim_row).execute()

            print(f"[ANALYZE-BG-LG] ✓ Stored {len(claims)} claims")

        # 5.2 Store methods
        methods = final_state.get("methods", [])
        if methods:
            print(f"[ANALYZE-BG-LG] Storing {len(methods)} methods...")
            for method in methods:
                method_row = {
                    "document_id": document_id,
                    "project_id": project_id,
                    "method_name": method["method_name"],
                    "method_type": method.get("method_type"),
                    "description": method["description"],
                    "parameters": method.get("parameters", {}),
                    "section_title": method.get("section_title"),
                    "page_number": method.get("page_number"),
                    "datasets_used": method.get("datasets_used", []),
                    "evaluation_metrics": method.get("evaluation_metrics", [])
                }
                supabase.table("document_methods").insert(method_row).execute()

            print(f"[ANALYZE-BG-LG] ✓ Stored {len(methods)} methods")

        # 5.3 Store findings
        findings = final_state.get("findings", [])
        if findings:
            print(f"[ANALYZE-BG-LG] Storing {len(findings)} findings...")
            for finding in findings:
                finding_row = {
                    "document_id": document_id,
                    "project_id": project_id,
                    "finding_text": finding["finding_text"],
                    "finding_type": finding.get("finding_type"),
                    "metrics": finding.get("metrics", {}),
                    "comparison_baseline": finding.get("comparison_baseline"),
                    "improvement_over_baseline": finding.get("improvement_over_baseline"),
                    "section_title": finding.get("section_title"),
                    "page_number": finding.get("page_number"),
                    "table_or_figure_reference": finding.get("table_or_figure_reference"),
                    "statistical_significance": finding.get("statistical_significance"),
                    "confidence_score": finding["confidence_score"]
                }
                supabase.table("document_findings").insert(finding_row).execute()

            print(f"[ANALYZE-BG-LG] ✓ Stored {len(findings)} findings")

        print(f"[ANALYZE-BG-LG] ✓ All structured data stored successfully")

        # 5.5. Track quota usage and OpenAI costs
        try:
            # Increment quota counter
            asyncio.run(increment_quota_usage(user_id, "document"))
            print(f"[ANALYZE-BG] Quota incremented for user_id={user_id}")

            # Track OpenAI usage
            metadata = analysis.get("analysis_metadata", {})
            if metadata.get("prompt_tokens") and metadata.get("completion_tokens"):
                asyncio.run(track_openai_usage(
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

                                # Update draft status to analyzing
                                supabase.table("drafts").update({
                                    "status": "analyzing",
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

    except Exception as e:
        # Update status to failed
        import traceback
        print(f"[ANALYZE-BG-LG] ========== LANGGRAPH ANALYSIS FAILED ==========")
        print(f"[ANALYZE-BG-LG] ERROR for document_id={document_id}: {type(e).__name__}: {str(e)}")
        print(f"[ANALYZE-BG-LG] Traceback:\n{traceback.format_exc()}")
        supabase.table("documents").update({
            "status": "failed",
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": {
                "error": str(e),
                "error_type": type(e).__name__
            }
        }).eq("id", document_id).execute()

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
        # 1. Fetch document record
        doc_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

        if not doc_response.data:
            raise HTTPException(status_code=404, detail="Document not found")

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
                "status": "analyzing"
            }

        # 4. Validate file URL exists
        file_url = document.get("file_url")
        if not file_url:
            raise HTTPException(status_code=400, detail="Document has no file URL")

        # 5. Update status to 'analyzing'
        supabase.table("documents").update({
            "status": "analyzing",
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", document_id).execute()

        # 6. Submit Celery task
        task_result = analyze_document_task.delay(document_id, user_id, project_id)

        print(f"[ANALYZE] Celery analysis task submitted for document_id={document_id} (task_id={task_result.id})")

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


@router.get("/{document_id}/file")
async def get_document_file(document_id: str, user_id: str = Depends(get_current_user)):
    """
    Proxy the document file from Supabase Storage with authentication.
    This ensures users can only access their own documents.
    """
    from fastapi.responses import StreamingResponse
    import httpx

    print(f"[GET-FILE] Fetching file for document_id={document_id}, user_id={user_id}")

    # Get document metadata
    doc_response = supabase.table("documents").select("file_url, file_type, user_id, metadata").eq("id", document_id).eq("user_id", user_id).execute()

    if not doc_response.data:
        print(f"[GET-FILE] Document not found: {document_id}")
        raise HTTPException(status_code=404, detail="Document not found")

    document = doc_response.data[0]
    file_url = document.get("file_url")
    file_type = document.get("file_type", "application/pdf")

    print(f"[GET-FILE] file_url={file_url}, file_type={file_type}")

    if not file_url:
        raise HTTPException(status_code=404, detail="Document file not found")

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


# NOTE: BibTeX export endpoint moved to projects.py router
# The route /projects/{project_id}/export-bibtex is now at /{project_id}/export-bibtex in projects router
