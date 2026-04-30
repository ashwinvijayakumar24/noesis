"""
Drafts API Endpoints

Provides endpoints for managing research drafts (user's own papers).
Drafts are uploaded for analysis, claim extraction, coverage gap detection, and reviewer feedback.

Requirements: 1.1, 1.3, 1.5
"""

from fastapi import APIRouter, HTTPException, Depends, Header, UploadFile, File, Form, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel
from app.core.supabase_client import supabase
from app.services.draft_processing import ingest_draft, validate_file_format
from app.services.draft_export import export_draft_analysis_as_pdf
from app.services.draft_errors import DraftProcessingError
from app.services.draft_anchor_qa import locate_text_snippet
from app.core.security_middleware import SecureAuthValidator, limiter
from typing import Any, Optional
import datetime
import uuid
import logging
import json
import asyncio
import os
import redis.asyncio as aioredis

_DEV = os.environ.get("ENVIRONMENT", "development") != "production"

router = APIRouter()

# Set up logging
logger = logging.getLogger(__name__)

REDIS_URL = "redis://redis:6379/0"
VALID_PAPER_TYPES = {
    "journal_article",
    "conference_paper",
    "thesis",
    "dissertation",
    "preprint",
}
VALID_CITATION_STYLES = {
    "apa",
    "mla",
    "chicago",
    "ieee",
    "vancouver",
    "other",
}


def _normalize_reviewer_persona(value: Optional[str]) -> str:
    return value if value in {"reviewer_1", "reviewer_2"} else "reviewer_2"


def _validate_upload_context(paper_type: str, citation_style: str) -> tuple[str, str]:
    normalized_paper_type = (paper_type or "journal_article").strip().lower()
    normalized_citation_style = (citation_style or "apa").strip().lower()

    if normalized_paper_type not in VALID_PAPER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid paper_type. Must be one of: {', '.join(sorted(VALID_PAPER_TYPES))}",
        )

    if normalized_citation_style not in VALID_CITATION_STYLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid citation_style. Must be one of: {', '.join(sorted(VALID_CITATION_STYLES))}",
        )

    return normalized_paper_type, normalized_citation_style


def _get_latest_revision_metadata(draft_id: str, user_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    empty_metadata = {
        "has_previous_version": False,
        "comparison_id": None,
        "draft_v1_id": None,
        "draft_v2_id": draft_id,
        "improvement_score": None,
        "feedback_resolved_count": 0,
        "feedback_carryover_count": 0,
        "gaps_resolved_count": 0,
    }

    comparison_response = supabase.table("draft_comparisons")\
        .select("*")\
        .eq("draft_v2_id", draft_id)\
        .eq("user_id", user_id)\
        .order("created_at", desc=True)\
        .limit(1)\
        .execute()

    if not comparison_response.data:
        return empty_metadata, {}

    comparison = comparison_response.data[0]
    comparison_result = comparison.get("comparison_result") or {}
    carryover_items = comparison_result.get("feedback_carryover") or []
    carryover_map = {
        item["feedback_id"]: item
        for item in carryover_items
        if item.get("feedback_id")
    }

    return (
        {
            "has_previous_version": True,
            "comparison_id": comparison.get("id"),
            "draft_v1_id": comparison.get("draft_v1_id"),
            "draft_v2_id": comparison.get("draft_v2_id"),
            "improvement_score": comparison.get("improvement_score"),
            "feedback_resolved_count": comparison.get("feedback_addressed", 0),
            "feedback_carryover_count": len(carryover_map),
            "gaps_resolved_count": comparison.get("gaps_resolved", 0),
        },
        carryover_map,
    )


def _load_draft_anchor_context(draft_id: str) -> tuple[str, list[dict[str, Any]]]:
    analysis_response = (
        supabase.table("draft_analysis")
        .select("structure")
        .eq("draft_id", draft_id)
        .limit(1)
        .execute()
    )
    if not analysis_response.data:
        return "", []

    structure = analysis_response.data[0].get("structure") or {}
    sections = [
        section for section in (structure.get("sections") or [])
        if isinstance(section, dict) and section.get("content")
    ]
    if not sections:
        return "", []

    draft_text = "\n\n".join(str(section.get("content") or "") for section in sections)
    return draft_text, sections


def _apply_anchor_to_item(
    item: dict[str, Any],
    *,
    draft_text: str,
    sections: list[dict[str, Any]],
    snippet_candidates: list[str],
    section_reference: Optional[str],
    min_confidence: float = 0.72,
) -> dict[str, Any]:
    if item.get("pdf_coordinates") or not draft_text or not sections:
        return item

    for candidate in snippet_candidates:
        text = (candidate or "").strip()
        if len(text) < 12:
            continue
        anchor = locate_text_snippet(
            text,
            draft_text,
            sections=sections,
            section_reference=section_reference,
            context_radius=60,
        )
        if not anchor.get("found"):
            continue
        if (anchor.get("match_confidence") or 0) < min_confidence:
            continue
        if not anchor.get("pdf_coordinates"):
            continue

        enriched = dict(item)
        for key in (
            "line_number",
            "char_start",
            "char_end",
            "text_snippet",
            "section_id",
            "char_offset_from_section",
            "pdf_coordinates",
            "match_confidence",
        ):
            if anchor.get(key) is not None:
                enriched[key] = anchor[key]
        return enriched

    return item


def _enrich_feedback_payload_with_anchors(
    draft_id: str,
    claims: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    feedback: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    draft_text, sections = _load_draft_anchor_context(draft_id)
    if not draft_text or not sections:
        return claims, gaps, feedback

    enriched_claims = [
        _apply_anchor_to_item(
            dict(claim),
            draft_text=draft_text,
            sections=sections,
            snippet_candidates=[claim.get("text_snippet", ""), claim.get("claim_text", "")],
            section_reference=claim.get("section_location") or claim.get("section_type"),
        )
        for claim in claims
    ]
    claim_anchor_map = {
        str(claim.get("id")): claim for claim in enriched_claims
        if claim.get("id") and claim.get("pdf_coordinates")
    }

    enriched_gaps = [
        _apply_anchor_to_item(
            dict(gap),
            draft_text=draft_text,
            sections=sections,
            snippet_candidates=[gap.get("text_snippet", ""), gap.get("description", "")],
            section_reference=gap.get("section_reference") or gap.get("section_type"),
        )
        for gap in gaps
    ]

    enriched_feedback: list[dict[str, Any]] = []
    for item in feedback:
        feedback_item = _apply_anchor_to_item(
            dict(item),
            draft_text=draft_text,
            sections=sections,
            snippet_candidates=[
                item.get("text_snippet", ""),
                item.get("specific_issue", ""),
                item.get("section_reference", ""),
                item.get("feedback_text", ""),
            ],
            section_reference=item.get("section_reference") or item.get("section_type"),
        )

        target_claim = claim_anchor_map.get(str(feedback_item.get("target_claim_id")))
        if target_claim and not feedback_item.get("pdf_coordinates"):
            for key in (
                "line_number",
                "char_start",
                "char_end",
                "text_snippet",
                "section_id",
                "char_offset_from_section",
                "pdf_coordinates",
                "match_confidence",
            ):
                if target_claim.get(key) is not None and feedback_item.get(key) is None:
                    feedback_item[key] = target_claim[key]

        enriched_feedback.append(feedback_item)

    return enriched_claims, enriched_gaps, enriched_feedback


def _filter_feedback_diagnostics(items: list[dict[str, Any]], text_key: str) -> list[dict[str, Any]]:
    return [
        item for item in items
        if not str(item.get(text_key) or "").lower().startswith("assessment failed:")
    ]


# Helper functions
def generate_signed_url_for_draft(file_url: str, draft_id: str) -> Optional[dict]:
    """
    Generate a signed URL for a draft file.

    Args:
        file_url: The public file URL from storage
        draft_id: Draft ID (for logging)

    Returns:
        Dict with 'signed_url' and 'expires_at' keys, or None if generation fails
    """
    if not file_url or "/drafts/" not in file_url:
        return None

    try:
        # Extract storage path from public URL
        path_parts = file_url.split("/drafts/")
        if len(path_parts) < 2:
            return None

        storage_path = path_parts[1]

        # Generate signed URL with 1-hour expiration
        signed_url_response = supabase.storage.from_("drafts").create_signed_url(storage_path, 3600)
        signed_url = signed_url_response.get("signedURL")

        if signed_url:
            expires_at = (datetime.datetime.utcnow() + datetime.timedelta(seconds=3600)).isoformat()
            logger.debug(f"Generated signed URL for draft {draft_id}")
            return {
                "signed_url": signed_url,
                "expires_at": expires_at
            }
        else:
            logger.warning(f"Failed to generate signed URL for draft {draft_id}")
            return None

    except Exception as e:
        logger.error(f"Error generating signed URL for draft {draft_id}: {e}")
        return None


def get_current_user(authorization: str = Header(None)):
    """Extract and validate user from Authorization header"""
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"
        )

    try:
        return SecureAuthValidator.get_user_id(authorization, supabase)
    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


class ExtensionAnalyzeRequest(BaseModel):
    content: str
    title: Optional[str] = "Overleaf Document"
    project_id: Optional[str] = None


@router.post("/analyze-from-extension")
async def analyze_draft_from_extension(
    body: ExtensionAnalyzeRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Create a draft from raw text content sent by the Chrome extension.
    Used when user clicks 'Noesis Review' button in Overleaf.
    """
    from app.tasks.draft_analysis import analyze_draft_task

    content = body.content.strip()
    title = (body.title or "Overleaf Document").strip()
    project_id = body.project_id

    if not content or len(content) < 50:
        raise HTTPException(status_code=400, detail="Document content too short")

    # If no project_id provided, use or create a default project
    if not project_id:
        projects_resp = supabase.table("projects").select("id").eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
        if projects_resp.data:
            project_id = projects_resp.data[0]["id"]
        else:
            new_project = supabase.table("projects").insert({
                "user_id": user_id,
                "title": "Overleaf Drafts",
                "description": "Drafts analyzed via Noesis Chrome extension",
            }).execute()
            project_id = new_project.data[0]["id"]

    # Store content in Supabase Storage as .txt
    draft_id = str(uuid.uuid4())
    storage_path = f"{user_id}/{draft_id}.txt"

    supabase.storage.from_("drafts").upload(
        path=storage_path,
        file=content.encode("utf-8"),
        file_options={"content-type": "text/plain"},
    )

    file_url = supabase.storage.from_("drafts").get_public_url(storage_path)

    draft_resp = supabase.table("drafts").insert({
        "id": draft_id,
        "user_id": user_id,
        "project_id": project_id,
        "title": title,
        "version": 1,
        "file_url": file_url,
        "file_type": "txt",
        "paper_type": "journal_article",
        "citation_style": "apa",
        "status": "processing",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
    }).execute()

    if not draft_resp.data:
        raise HTTPException(status_code=500, detail="Failed to create draft record")

    analyze_draft_task.delay(draft_id, project_id)
    logger.info(f"[EXTENSION] Draft {draft_id} created and analysis triggered for user {user_id}")

    return {"draft_id": draft_id, "project_id": project_id, "status": "processing"}


@router.post("/upload")
@limiter.limit("5/minute")  # Max 5 draft uploads per minute
async def upload_draft(
    request: Request,
    file: UploadFile = File(...),
    project_id: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    paper_type: str = Form(default="journal_article"),
    citation_style: str = Form(default="apa"),
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
    print(
        f"[DRAFT-UPLOAD] Received: file={file.filename}, project_id={project_id}, title={title}, "
        f"user_id={user_id}, paper_type={paper_type}, citation_style={citation_style}"
    )

    try:
        paper_type, citation_style = _validate_upload_context(paper_type, citation_style)

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
            "paper_type": paper_type,
            "citation_style": citation_style,
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
    include_signed_urls: bool = Query(False, description="Generate signed URLs for file access (slower)"),
    user_id: str = Depends(get_current_user)
):
    """
    List all drafts for the authenticated user with pagination.
    Optionally filter by project_id.

    Pagination:
    - limit: Number of drafts to return (default: 50, max: 100)
    - offset: Number of drafts to skip (default: 0)
    - Returns total count and has_more flag

    Security:
    - include_signed_urls: Generate time-limited signed URLs instead of public URLs (default: false for performance)

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

    drafts = response.data if response.data else []

    # Optionally generate signed URLs for each draft
    if include_signed_urls and drafts:
        for draft in drafts:
            file_url = draft.get("file_url")
            signed_url_data = generate_signed_url_for_draft(file_url, draft.get("id"))
            if signed_url_data:
                draft["file_url"] = signed_url_data["signed_url"]
                draft["file_url_expires_at"] = signed_url_data["expires_at"]

    return {
        "drafts": drafts,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }
    }


@router.get("/projects/{project_id}/drafts")
def list_project_drafts(
    project_id: str,
    include_signed_urls: bool = Query(False, description="Generate signed URLs for file access (slower)"),
    user_id: str = Depends(get_current_user)
):
    """
    List all drafts for a specific project.
    Ordered by version (newest first).

    Security:
    - include_signed_urls: Generate time-limited signed URLs instead of public URLs (default: false for performance)
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

    drafts = response.data if response.data else []

    # Optionally generate signed URLs for each draft
    if include_signed_urls and drafts:
        for draft in drafts:
            file_url = draft.get("file_url")
            signed_url_data = generate_signed_url_for_draft(file_url, draft.get("id"))
            if signed_url_data:
                draft["file_url"] = signed_url_data["signed_url"]
                draft["file_url_expires_at"] = signed_url_data["expires_at"]

    return drafts


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

    Security: Returns signed URL for file access (1-hour expiration) instead of public URL.
    """
    response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).execute()

    if not response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft = response.data[0]

    # Generate signed URL for secure file access (defense-in-depth)
    file_url = draft.get("file_url")
    signed_url_data = generate_signed_url_for_draft(file_url, draft_id)

    if signed_url_data:
        # Replace public URL with signed URL
        draft["file_url"] = signed_url_data["signed_url"]
        draft["file_url_expires_at"] = signed_url_data["expires_at"]
    # Otherwise, fallback to public URL (graceful degradation)

    return draft


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
            print(f"[DRAFT-ANALYZE-BG-LG] ✓ Draft ingested successfully")
        except Exception as ingest_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ INGEST FAILED: {type(ingest_error).__name__}")
            if _DEV:
                print(f"[DRAFT-ANALYZE-BG-LG] Detail: {str(ingest_error)}")
                print(traceback.format_exc())
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

        if not storage_path:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ ERROR: Could not extract storage path from file_url")
            raise ValueError(f"Could not extract storage path from file_url: {file_url}")

        # Download file bytes
        print(f"[DRAFT-ANALYZE-BG-LG] Downloading file from storage...")
        try:
            file_bytes = supabase.storage.from_("drafts").download(storage_path)
            if not file_bytes:
                raise ValueError("Downloaded file is empty")
            print(f"[DRAFT-ANALYZE-BG-LG] ✓ Downloaded {len(file_bytes)} bytes")
        except Exception as download_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ DOWNLOAD FAILED: {type(download_error).__name__}")
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
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ TEXT EXTRACTION FAILED: {type(extract_error).__name__}")
            if _DEV:
                print(f"[DRAFT-ANALYZE-BG-LG] Detail: {str(extract_error)}")
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
        except Exception as langgraph_error:
            print(f"[DRAFT-ANALYZE-BG-LG] ✗ LANGGRAPH WORKFLOW FAILED: {type(langgraph_error).__name__}")
            if _DEV:
                print(f"[DRAFT-ANALYZE-BG-LG] Detail: {str(langgraph_error)}")
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
                        model="gpt-5.2-chat-latest",
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

        # Auto-trigger comparison if a previous analyzed draft exists in the project
        print(f"[DRAFT-ANALYZE-BG-LG] ========== STEP 5: AUTO-COMPARISON ==========")
        try:
            if project_id:
                # Find the most recent *other* analyzed draft in this project
                prev_drafts = supabase.table("drafts")\
                    .select("id, created_at")\
                    .eq("project_id", project_id)\
                    .eq("status", "analyzed")\
                    .neq("id", draft_id)\
                    .order("created_at", desc=True)\
                    .limit(1)\
                    .execute()

                if prev_drafts.data:
                    prev_draft_id = prev_drafts.data[0]["id"]
                    print(f"[DRAFT-ANALYZE-BG-LG] Found previous analyzed draft: {prev_draft_id}")

                    from app.services.draft_comparison import compare_drafts as run_compare
                    loop2 = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop2)
                    loop2.run_until_complete(
                        run_compare(
                            draft_v1_id=prev_draft_id,
                            draft_v2_id=draft_id,
                            project_id=project_id,
                            user_id=user_id
                        )
                    )
                    loop2.close()
                    print(f"[DRAFT-ANALYZE-BG-LG] ✓ Auto-comparison completed")
                else:
                    print(f"[DRAFT-ANALYZE-BG-LG] No previous draft to compare against, skipping")
        except Exception as cmp_err:
            print(f"[DRAFT-ANALYZE-BG-LG] WARNING: Auto-comparison failed: {cmp_err}")
            # Don't fail the overall task if comparison fails

        print(f"[DRAFT-ANALYZE-BG-LG] ========== BACKGROUND TASK COMPLETED SUCCESSFULLY ==========")

    except Exception as e:
        print(f"[DRAFT-ANALYZE-BG-LG] ========== BACKGROUND TASK FAILED: {type(e).__name__} ==========")
        if _DEV:
            print(f"[DRAFT-ANALYZE-BG-LG] Detail: {str(e)}")
            print(traceback.format_exc())

        # Status lifecycle is owned by the Celery task (draft_analysis.py).
        # It sets 'failed' only after all retries are exhausted, so we just log here.
        print(f"[DRAFT-ANALYZE-BG-LG] Re-raising to Celery retry handler (status managed there)")


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

        if status in ("analyzed", "failed") and analysis_response.data:
            analysis_data = analysis_response.data[0]
            analysis_metadata = analysis_data.get("analysis_metadata") or {}
            analysis_payload = analysis_data.get("analysis") or {}
            revision_metadata, _ = _get_latest_revision_metadata(draft_id, user_id)
            return {
                "status": status,
                "draft_id": draft_id,
                "draft_title": draft.get("title"),
                "analysis": analysis_data,
                "editing_feedback": analysis_payload.get("editing_feedback"),
                "paper_type": draft.get("paper_type", "journal_article"),
                "citation_style": draft.get("citation_style", "apa"),
                "revision_metadata": revision_metadata,
                "priority_actions": analysis_metadata.get("priority_actions", []),
                # Enriched output fields
                "readiness_score": analysis_metadata.get("readiness_score"),
                "verdict": analysis_metadata.get("verdict"),
                "score_breakdown": analysis_metadata.get("score_breakdown", {}),
                "action_items": analysis_metadata.get("action_items", []),
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
    claims_response = supabase.table("draft_claims").select("*").eq("draft_id", draft_id).execute()
    print(f"[DRAFT-CLAIMS] Found {len(claims_response.data) if claims_response.data else 0} claims")
    claims = claims_response.data or []

    return {
        "draft_id": draft_id,
        "claims": claims,
        "total_claims": len(claims)
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
    gaps = _filter_feedback_diagnostics(gaps_response.data or [], "description")

    return {
        "draft_id": draft_id,
        "gaps": gaps,
        "total_gaps": len(gaps)
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
    feedback = _filter_feedback_diagnostics(feedback_response.data or [], "feedback_text")

    return {
        "draft_id": draft_id,
        "feedback": feedback,
        "total_feedback_items": len(feedback)
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


# ============================================
# Section-Based Feedback Endpoints (Phase 2E)
# ============================================

@router.get("/{draft_id}/feedback-by-section")
async def get_feedback_by_section(
    draft_id: str,
    section_type: str = Query(..., description="Section type: abstract, introduction, literature_review, methodology, results, discussion, conclusion, references"),
    status: str = Query('new', description="Feedback status: new, saved, dismissed"),
    user_id: str = Depends(get_current_user)
):
    """
    Get all feedback items for a specific section.

    Returns combined claims, coverage gaps, and reviewer feedback filtered by
    section type and status for the redesigned section-based navigation UI.

    Args:
        draft_id: Draft UUID
        section_type: One of the 8 standardized section types
        status: Feedback status (new, saved, dismissed)
        user_id: Current user ID from auth token

    Returns:
        {
            "claims": [...],
            "gaps": [...],
            "feedback": [...],
            "section_type": "methodology",
            "status": "new",
            "total_count": 15
        }
    """
    try:
        # Verify draft ownership
        draft_response = supabase.table("drafts")\
            .select("id")\
            .eq("id", draft_id)\
            .eq("user_id", user_id)\
            .execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Validate section_type
        valid_sections = ['abstract', 'introduction', 'literature_review', 'methodology', 'results', 'discussion', 'conclusion', 'references']
        if section_type not in valid_sections:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid section_type. Must be one of: {', '.join(valid_sections)}"
            )

        # Validate status
        valid_statuses = ['new', 'saved', 'dismissed']
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

        # Status filter: when querying "new", also include items with NULL status
        # (legacy data created before the status column was added)
        status_filter = f"status.eq.{status},status.is.null" if status == "new" else f"status.eq.{status}"

        # Fetch claims for this section + status
        claims_response = supabase.table("draft_claims")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .eq("section_type", section_type)\
            .or_(status_filter)\
            .eq("hidden", False)\
            .order("importance_score", desc=True)\
            .execute()

        # Fetch coverage gaps for this section + status
        gaps_response = supabase.table("coverage_gaps")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .eq("section_type", section_type)\
            .or_(status_filter)\
            .order("priority", desc=False)\
            .execute()

        # Fetch reviewer feedback for this section + status
        feedback_response = supabase.table("reviewer_feedback")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .eq("section_type", section_type)\
            .or_(status_filter)\
            .order("priority", desc=False)\
            .execute()

        claims = claims_response.data or []
        gaps = _filter_feedback_diagnostics(gaps_response.data or [], "description")
        feedback = _filter_feedback_diagnostics(feedback_response.data or [], "feedback_text")

        return {
            "claims": claims,
            "gaps": gaps,
            "feedback": feedback,
            "section_type": section_type,
            "status": status,
            "total_count": len(claims) + len(gaps) + len(feedback)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch section feedback for draft {draft_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch section feedback: {str(e)}")


@router.get("/{draft_id}/all-feedback")
async def get_all_feedback(
    draft_id: str,
    actionable_only: bool = Query(True, description="Filter to only actionable items"),
    status: str = Query('new', description="Feedback status: new, saved, dismissed"),
    user_id: str = Depends(get_current_user)
):
    """
    Get all feedback items across all sections in one call.

    Returns combined claims, coverage gaps, and reviewer feedback with
    aggregated counts and readiness score/verdict from draft_analysis.

    When actionable_only=True (default):
    - Claims: only those with requires_citation=True OR importance_score >= 0.65
    - Feedback: excludes feedback_type='strength'
    - Gaps: all included (gaps are inherently actionable)
    """
    try:
        # Verify draft ownership
        draft_response = supabase.table("drafts")\
            .select("id")\
            .eq("id", draft_id)\
            .eq("user_id", user_id)\
            .execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Validate status
        valid_statuses = ['new', 'saved', 'dismissed']
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

        # Status filter: when querying "new", also include items with NULL status
        status_filter = f"status.eq.{status},status.is.null" if status == "new" else f"status.eq.{status}"

        # Fetch all claims, gaps, feedback in parallel-ish queries
        claims_response = supabase.table("draft_claims")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .or_(status_filter)\
            .eq("hidden", False)\
            .order("importance_score", desc=True)\
            .execute()

        gaps_response = supabase.table("coverage_gaps")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .or_(status_filter)\
            .order("priority", desc=False)\
            .execute()

        feedback_response = supabase.table("reviewer_feedback")\
            .select("*")\
            .eq("draft_id", draft_id)\
            .or_(status_filter)\
            .order("priority", desc=False)\
            .execute()

        claims = claims_response.data or []
        gaps = _filter_feedback_diagnostics(gaps_response.data or [], "description")
        feedback = _filter_feedback_diagnostics(feedback_response.data or [], "feedback_text")
        revision_metadata, carryover_map = _get_latest_revision_metadata(draft_id, user_id)

        for item in feedback:
            item["reviewer_persona"] = _normalize_reviewer_persona(item.get("reviewer_persona"))
            carryover = carryover_map.get(item.get("id"))
            item["carryover_from_previous_version"] = carryover is not None
            item["carryover_status"] = "carried_over" if carryover else None
            item["previous_feedback_text"] = carryover.get("previous_feedback_text") if carryover else None
            item["previous_feedback_id"] = carryover.get("previous_feedback_id") if carryover else None

        # Apply actionable_only filtering
        if actionable_only:
            claims = [
                c for c in claims
                if c.get("requires_citation") is True or (c.get("importance_score") or 0) >= 0.65
            ]
            feedback = [
                f for f in feedback
                if f.get("feedback_type") != "strength"
            ]

        # Compute aggregated counts
        claims_needing_citation = len([c for c in claims if c.get("requires_citation") is True])
        critical_gaps = len([g for g in gaps if g.get("priority") == "high"])
        critical_feedback = len([f for f in feedback if f.get("severity") in ("critical", "major")])

        # Fetch readiness_score and verdict from draft_analysis
        analysis_response = supabase.table("draft_analysis")\
            .select("analysis_metadata")\
            .eq("draft_id", draft_id)\
            .execute()

        readiness_score = None
        verdict = None
        score_breakdown = {}
        if analysis_response.data:
            metadata = analysis_response.data[0].get("analysis_metadata") or {}
            readiness_score = metadata.get("readiness_score")
            verdict = metadata.get("verdict")
            score_breakdown = metadata.get("score_breakdown", {})

        return {
            "claims": claims,
            "gaps": gaps,
            "feedback": feedback,
            "status": status,
            "actionable_only": actionable_only,
            "counts": {
                "total_claims": len(claims),
                "claims_needing_citation": claims_needing_citation,
                "total_gaps": len(gaps),
                "critical_gaps": critical_gaps,
                "total_feedback": len(feedback),
                "critical_feedback": critical_feedback,
            },
            "readiness_score": readiness_score,
            "verdict": verdict,
            "score_breakdown": score_breakdown,
            "revision_metadata": revision_metadata,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch all feedback for draft {draft_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch all feedback: {str(e)}")


@router.post("/{draft_id}/gaps/{gap_id}/find-papers")
async def find_papers_for_gap(
    draft_id: str,
    gap_id: str,
    user_id: str = Depends(get_current_user),
):
    """Search for relevant external papers for a specific coverage gap."""
    draft_res = (
        supabase.table("drafts")
        .select("id, user_id, project_id")
        .eq("id", draft_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    if not draft_res.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    gap_res = (
        supabase.table("coverage_gaps")
        .select("id, description, draft_id, suggested_papers")
        .eq("id", gap_id)
        .eq("draft_id", draft_id)
        .single()
        .execute()
    )
    if not gap_res.data:
        raise HTTPException(status_code=404, detail="Gap not found")

    from fastapi.concurrency import run_in_threadpool
    from app.services.paper_recommendations import search_papers_by_query

    query = " ".join(
        part
        for part in [
            gap_res.data.get("description", "").strip(),
        ]
        if part
    )
    if not query:
        raise HTTPException(status_code=400, detail="Gap has no description to search")

    papers = await run_in_threadpool(lambda: search_papers_by_query(query=query, limit=5))

    project_id = draft_res.data.get("project_id")
    existing_recs = []
    if project_id:
        rec_res = (
            supabase.table("paper_recommendations")
            .select("id, doi, arxiv_id, title")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        existing_recs = rec_res.data or []

    rec_map: dict[str, str] = {}
    for rec in existing_recs:
        if rec.get("doi"):
            rec_map[f"doi:{rec['doi']}"] = rec["id"]
        if rec.get("arxiv_id"):
            rec_map[f"arxiv:{rec['arxiv_id']}"] = rec["id"]
        if rec.get("title"):
            rec_map[f"title:{rec['title'].strip().lower()}"] = rec["id"]

    annotated_papers = []
    for paper in papers:
        recommendation_id = None
        if paper.get("doi"):
            recommendation_id = rec_map.get(f"doi:{paper['doi']}")
        if recommendation_id is None and paper.get("arxiv_id"):
            recommendation_id = rec_map.get(f"arxiv:{paper['arxiv_id']}")
        if recommendation_id is None and paper.get("title"):
            recommendation_id = rec_map.get(f"title:{paper['title'].strip().lower()}")

        annotated_papers.append({**paper, "recommendation_id": recommendation_id})

    supabase.table("coverage_gaps").update(
        {
            "suggested_papers": annotated_papers,
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }
    ).eq("id", gap_id).eq("draft_id", draft_id).execute()

    return {"gap_id": gap_id, "query": query, "papers": annotated_papers, "count": len(annotated_papers)}


@router.patch("/{draft_id}/feedback/{feedback_id}/status")
async def update_feedback_status(
    draft_id: str,
    feedback_id: str,
    feedback_type: str = Query(..., description="Feedback type: claim, gap, feedback"),
    status: str = Query(..., description="New status: new, saved, dismissed"),
    user_id: str = Depends(get_current_user)
):
    """
    Update status for a feedback item (save/dismiss workflow).

    Allows users to save useful feedback or dismiss irrelevant items, similar to
    the Paper Recommendations and Research Questions workflow.

    Args:
        draft_id: Draft UUID
        feedback_id: UUID of the claim, gap, or feedback item
        feedback_type: Type of feedback (claim, gap, feedback)
        status: New status (new, saved, dismissed)
        user_id: Current user ID from auth token

    Returns:
        {
            "message": "Feedback status updated",
            "feedback_id": "...",
            "feedback_type": "claim",
            "status": "saved"
        }
    """
    try:
        # Verify draft ownership
        draft_response = supabase.table("drafts")\
            .select("id")\
            .eq("id", draft_id)\
            .eq("user_id", user_id)\
            .execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Validate feedback_type
        valid_types = ['claim', 'gap', 'feedback']
        if feedback_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid feedback_type. Must be one of: {', '.join(valid_types)}"
            )

        # Validate status
        valid_statuses = ['new', 'saved', 'dismissed']
        if status not in valid_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
            )

        # Map feedback_type to table name
        table_mapping = {
            'claim': 'draft_claims',
            'gap': 'coverage_gaps',
            'feedback': 'reviewer_feedback'
        }
        table_name = table_mapping[feedback_type]

        # Update status
        update_response = supabase.table(table_name)\
            .update({"status": status, "updated_at": datetime.datetime.utcnow().isoformat()})\
            .eq("id", feedback_id)\
            .eq("draft_id", draft_id)\
            .execute()

        if not update_response.data:
            raise HTTPException(
                status_code=404,
                detail=f"Feedback item not found in {table_name}"
            )

        logger.info(f"Updated {feedback_type} {feedback_id} status to {status}")

        return {
            "message": "Feedback status updated",
            "feedback_id": feedback_id,
            "feedback_type": feedback_type,
            "status": status
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update feedback status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update feedback status: {str(e)}")


@router.get("/{draft_id}/section-summary")
async def get_section_summary(
    draft_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get feedback counts per section for navigation badges.

    Uses the PostgreSQL function get_feedback_counts_by_section() to efficiently
    compute counts grouped by section_type, status, and feedback_source.

    Args:
        draft_id: Draft UUID
        user_id: Current user ID from auth token

    Returns:
        {
            "sections": [
                {
                    "section_type": "introduction",
                    "new_count": 5,
                    "saved_count": 2,
                    "dismissed_count": 1,
                    "total_count": 8
                },
                ...
            ],
            "total_new": 25,
            "total_saved": 10,
            "total_dismissed": 5
        }
    """
    try:
        # Verify draft ownership (1 query)
        draft_response = supabase.table("drafts")\
            .select("id")\
            .eq("id", draft_id)\
            .eq("user_id", user_id)\
            .execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Fetch all rows in 3 bulk queries instead of 72 individual queries
        claims_res = supabase.table("draft_claims")\
            .select("section_type, status")\
            .eq("draft_id", draft_id)\
            .execute()

        gaps_res = supabase.table("coverage_gaps")\
            .select("section_type, status")\
            .eq("draft_id", draft_id)\
            .execute()

        # A2: Fetch feedback_type to exclude strengths from actionable badge count
        feedback_res = supabase.table("reviewer_feedback")\
            .select("section_type, status, feedback_type")\
            .eq("draft_id", draft_id)\
            .execute()

        # Aggregate in Python
        from collections import defaultdict
        counts: dict = defaultdict(lambda: {"new": 0, "saved": 0, "dismissed": 0})

        for row in (claims_res.data or []) + (gaps_res.data or []):
            section = row.get("section_type") or "introduction"
            status = row.get("status") or "new"
            if status in ("new", "saved", "dismissed"):
                counts[section][status] += 1

        # A2: Strengths are shown in a read-only accordion — exclude from badge count
        for row in (feedback_res.data or []):
            if row.get("feedback_type") == "strength":
                continue  # strengths don't count toward actionable badge
            section = row.get("section_type") or "introduction"
            status = row.get("status") or "new"
            if status in ("new", "saved", "dismissed"):
                counts[section][status] += 1

        section_summaries = []
        total_new = total_saved = total_dismissed = 0

        for section, c in counts.items():
            n, s, d = c["new"], c["saved"], c["dismissed"]
            section_summaries.append({
                "section_type": section,
                "new_count": n,
                "saved_count": s,
                "dismissed_count": d,
                "total_count": n + s + d,
            })
            total_new += n
            total_saved += s
            total_dismissed += d

        return {
            "sections": section_summaries,
            "total_new": total_new,
            "total_saved": total_saved,
            "total_dismissed": total_dismissed,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get section summary for draft {draft_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get section summary: {str(e)}")


@router.post("/{draft_id}/assign-sections")
async def assign_sections(
    draft_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Trigger section type assignment for draft feedback.

    This endpoint is called:
    1. Automatically when user opens an old draft (auto-migration)
    2. Manually if section assignments need to be regenerated

    Uses the section_mapping service to detect section types from GROBID/GPT-4
    structure and assign them to all feedback items.

    Args:
        draft_id: Draft UUID
        user_id: Current user ID from auth token

    Returns:
        {
            "message": "Section types assigned",
            "claims_updated": 10,
            "gaps_updated": 5,
            "feedback_updated": 8,
            "sections_identified": 7
        }
    """
    try:
        # Verify draft ownership
        draft_response = supabase.table("drafts")\
            .select("id")\
            .eq("id", draft_id)\
            .eq("user_id", user_id)\
            .execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found")

        # Import section mapping service
        from app.services.section_mapping import assign_section_types_to_feedback

        # Assign section types
        result = await assign_section_types_to_feedback(draft_id)

        logger.info(
            f"Section assignment complete for draft {draft_id}: "
            f"{result.get('claims_updated')} claims, "
            f"{result.get('gaps_updated')} gaps, "
            f"{result.get('feedback_updated')} feedback"
        )

        return {
            "message": "Section types assigned",
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to assign sections for draft {draft_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to assign sections: {str(e)}")


class FeedbackReactionBody(BaseModel):
    action: str  # 'helpful' | 'dispute'


@router.post("/{draft_id}/feedback/{feedback_id}/react")
@limiter.limit("30/minute")
async def react_to_feedback(
    request: Request,
    draft_id: str,
    feedback_id: str,
    body: FeedbackReactionBody,
    user_id: str = Depends(get_current_user)
):
    """
    Record a user reaction on a reviewer feedback item.

    Stores 'helpful' or 'dispute' reactions for each feedback item.
    Disputes are used to suppress repeated false-positive flags.
    Uses upsert so the user can change their reaction.

    Args:
        draft_id: Draft UUID
        feedback_id: UUID of the reviewer_feedback row
        body: {action: 'helpful' | 'dispute'}

    Returns:
        {success: true, action: str, feedback_id: str}
    """
    if body.action not in ("helpful", "dispute"):
        raise HTTPException(status_code=400, detail="action must be 'helpful' or 'dispute'")

    # Verify draft belongs to user
    draft_response = supabase.table("drafts")\
        .select("id")\
        .eq("id", draft_id)\
        .eq("user_id", user_id)\
        .execute()

    if not draft_response.data:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Upsert reaction (one per user per feedback item)
    supabase.table("user_feedback_on_analysis").upsert({
        "draft_id": draft_id,
        "feedback_id": feedback_id,
        "user_id": user_id,
        "user_action": body.action,
    }, on_conflict="draft_id,feedback_id,user_id").execute()

    logger.info(f"User {user_id} marked feedback {feedback_id} as {body.action}")

    return {"success": True, "action": body.action, "feedback_id": feedback_id}


@router.websocket("/{draft_id}/analysis-stream")
async def draft_analysis_stream(
    draft_id: str,
    websocket: WebSocket,
    token: str = Query(...),
):
    """Stream draft analysis progress via WebSocket."""
    # Validate token via Supabase
    try:
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            await websocket.close(code=4001)
            return
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()

    r = aioredis.from_url(REDIS_URL)

    # Send the latest known progress immediately so late subscribers don't start blank
    try:
        latest = await r.get(f"progress:{draft_id}:latest")
        if latest:
            if isinstance(latest, bytes):
                latest = latest.decode()
            await websocket.send_text(latest)
    except Exception:
        pass

    pubsub = r.pubsub()
    await pubsub.subscribe(f"progress:{draft_id}")

    try:
        # 20 minute hard timeout
        deadline = asyncio.get_running_loop().time() + 1200
        async for message in pubsub.listen():
            if asyncio.get_running_loop().time() > deadline:
                break
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                await websocket.send_text(data)
                event = json.loads(data)
                if event.get("progress", 0) >= 100:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WebSocket error for draft {draft_id}: {e}")
    finally:
        await pubsub.unsubscribe(f"progress:{draft_id}")
        await r.close()
        try:
            await websocket.close()
        except Exception:
            pass
