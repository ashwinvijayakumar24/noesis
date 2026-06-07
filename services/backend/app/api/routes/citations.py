"""
Citations API Endpoints

Provides endpoints for citation management, suggestions, formatting, and analysis.
Supports real-time citation suggestions, multiple citation styles, and citation quality assessment.

Requirements: Phase 1 Tasks 3.1, 3.2
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.core.supabase_client import supabase
from app.services.citation_management import (
    extract_citations_from_draft,
    format_citation_all_styles,
    generate_citation_suggestions,
    validate_citation_format,
    detect_duplicate_citations,
    parse_citation_format
)
from app.services.draft_analysis_runs import active_run_filter
from app.core.logging_config import get_logger
import datetime

router = APIRouter()
logger = get_logger(__name__)


# ============================================
# Pydantic Models
# ============================================

class CitationSuggestionRequest(BaseModel):
    """Request model for citation suggestions"""
    claim_text: str = Field(..., description="Text of the claim needing citation support")
    project_id: str = Field(..., description="Project ID to search within")
    draft_id: str = Field(..., description="Draft ID for tracking suggestions")
    existing_citations: List[str] = Field(default=[], description="Existing citations for this claim")
    max_suggestions: int = Field(default=5, ge=1, le=10, description="Maximum number of suggestions (1-10)")


class CitationFormatRequest(BaseModel):
    """Request model for citation formatting"""
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(..., description="List of author names")
    year: str = Field(..., description="Publication year")
    journal: Optional[str] = Field(None, description="Journal name")
    volume: Optional[str] = Field(None, description="Volume number")
    issue: Optional[str] = Field(None, description="Issue number")
    pages: Optional[str] = Field(None, description="Page range")
    doi: Optional[str] = Field(None, description="Digital Object Identifier")
    url: Optional[str] = Field(None, description="Paper URL")
    styles: List[str] = Field(default=["apa", "ieee", "mla", "chicago"], description="Citation styles to generate")


class CitationCreateRequest(BaseModel):
    """Request model for creating a citation"""
    project_id: str
    document_id: Optional[str] = None
    title: str
    authors: List[str]
    year: Optional[int] = None
    journal_name: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    url: Optional[str] = None


class CitationSuggestionResponse(BaseModel):
    """Response model for accepting/rejecting a suggestion"""
    suggestion_id: str
    status: str = Field(..., description="Status: accepted, rejected, dismissed, applied")
    user_feedback: Optional[str] = None


# ============================================
# Helper Functions
# ============================================

def get_current_user(authorization: str = Header(None)):
    """Extract and validate user from Authorization header"""
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"
        )
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    token = authorization.split("Bearer ")[-1]
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")


# ============================================
# Citation Suggestion Endpoints
# ============================================

@router.post("/suggestions/generate")
async def generate_suggestions(
    request: CitationSuggestionRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Generate AI-powered citation suggestions for a claim.

    Uses semantic search to find relevant papers from the project's literature
    database and scores them by relevance, recency, and impact factor.

    Returns:
        List of citation suggestions with confidence scores and reasoning

    Requirements: Task 3.1 - Real-time citation suggestion endpoint
    """
    try:
        logger.info(f"Generating citation suggestions for user={user_id}, draft={request.draft_id}")

        # Verify user has access to the draft
        draft_response = supabase.table("drafts").select("*").eq("id", request.draft_id).eq("user_id", user_id).single().execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found or access denied")

        # Generate suggestions
        logger.info(f"Calling generate_citation_suggestions with project_id={request.project_id}, max_suggestions={request.max_suggestions}")
        suggestions = await generate_citation_suggestions(
            claim_text=request.claim_text,
            project_id=request.project_id,
            draft_id=request.draft_id,
            existing_citations=request.existing_citations,
            max_suggestions=request.max_suggestions
        )
        
        logger.info(f"generate_citation_suggestions returned {len(suggestions)} suggestions")
        
        if not suggestions:
            logger.warning(f"No suggestions generated. Possible reasons: no documents in project, no embeddings, or search returned no results.")

        # Store suggestions in database
        suggestion_records = []
        for suggestion in suggestions:
            record = {
                "draft_id": request.draft_id,
                "user_id": user_id,
                "claim_text": request.claim_text[:500],  # Truncate for storage
                "section_location": None,  # Can be added if provided
                "suggestion_type": suggestion["suggestion_type"],
                "suggested_paper": suggestion["suggested_paper"],
                "confidence_score": suggestion["confidence_score"],
                "relevance_score": suggestion["relevance_score"],
                "reasoning": suggestion["reasoning"],
                "impact_level": suggestion["impact_level"],
                "priority_score": suggestion["priority_score"],
                "status": "pending"
            }
            suggestion_records.append(record)

        if suggestion_records:
            insert_response = supabase.table("citation_suggestions").insert(suggestion_records).execute()

            # Add IDs to response
            if insert_response.data:
                for i, record in enumerate(insert_response.data):
                    if i < len(suggestions):
                        suggestions[i]["suggestion_id"] = record["id"]

        logger.info(f"Generated and stored {len(suggestions)} citation suggestions")

        return {
            "success": True,
            "suggestions": suggestions,
            "total_suggestions": len(suggestions)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Citation suggestion generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {str(e)}")


@router.post("/suggestions/{suggestion_id}/respond")
async def respond_to_suggestion(
    suggestion_id: str,
    response: CitationSuggestionResponse,
    user_id: str = Depends(get_current_user)
):
    """
    Accept, reject, or dismiss a citation suggestion.

    Args:
        suggestion_id: ID of the suggestion
        response: User's response (accepted, rejected, dismissed, applied)

    Returns:
        Updated suggestion record

    Requirements: Task 3.1 - Citation suggestion interaction tracking
    """
    try:
        logger.info(f"User {user_id} responding to suggestion {suggestion_id}: {response.status}")

        # Verify suggestion exists and belongs to user
        suggestion_response = supabase.table("citation_suggestions").select("*").eq("id", suggestion_id).eq("user_id", user_id).single().execute()

        if not suggestion_response.data:
            raise HTTPException(status_code=404, detail="Suggestion not found or access denied")

        # Update suggestion status
        update_data = {
            "status": response.status,
            "user_feedback": response.user_feedback,
            "responded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }

        updated = supabase.table("citation_suggestions").update(update_data).eq("id", suggestion_id).execute()

        logger.info(f"Updated suggestion {suggestion_id} to status: {response.status}")

        return {
            "success": True,
            "suggestion": updated.data[0] if updated.data else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to respond to suggestion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update suggestion: {str(e)}")


@router.get("/suggestions/draft/{draft_id}")
async def get_draft_suggestions(
    draft_id: str,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Get all citation suggestions for a draft.

    Args:
        draft_id: Draft ID
        status: Optional filter by status (pending, accepted, rejected, dismissed, applied)

    Returns:
        List of citation suggestions for the draft

    Requirements: Task 3.1 - Citation suggestion retrieval
    """
    try:
        logger.info(f"Fetching suggestions for draft={draft_id}, status={status}")

        # Verify user has access to the draft
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).single().execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found or access denied")

        # Fetch suggestions for the currently published analysis run only.
        active_run_id = draft_response.data.get("active_analysis_run_id")
        query = active_run_filter(
            supabase.table("citation_suggestions").select("*").eq("draft_id", draft_id),
            active_run_id,
        ).order("priority_score", desc=True)

        if status:
            query = query.eq("status", status)

        suggestions_response = query.execute()

        return {
            "success": True,
            "suggestions": suggestions_response.data,
            "total": len(suggestions_response.data)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch draft suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch suggestions: {str(e)}")


# ============================================
# Citation Formatting Endpoints
# ============================================

@router.post("/format")
async def format_citation(
    request: CitationFormatRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Generate formatted citations in multiple styles.

    Supports APA, IEEE, MLA, and Chicago citation styles.

    Returns:
        Formatted citations in requested styles

    Requirements: Task 3.1 - Citation formatting endpoint
    """
    try:
        logger.info(f"Formatting citation for: {request.title[:50]}...")

        formatted_citations = format_citation_all_styles(
            title=request.title,
            authors=request.authors,
            year=request.year,
            journal=request.journal,
            volume=request.volume,
            issue=request.issue,
            pages=request.pages,
            doi=request.doi,
            url=request.url
        )

        # Filter to requested styles
        filtered_citations = {
            style: citation
            for style, citation in formatted_citations.items()
            if style in request.styles
        }

        return {
            "success": True,
            "citations": filtered_citations
        }

    except Exception as e:
        logger.error(f"Citation formatting failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to format citation: {str(e)}")


@router.post("/format/batch")
async def format_citations_batch(
    citations: List[CitationFormatRequest],
    user_id: str = Depends(get_current_user)
):
    """
    Format multiple citations at once.

    Args:
        citations: List of citation metadata to format

    Returns:
        List of formatted citations in requested styles

    Requirements: Task 3.1 - Batch citation formatting
    """
    try:
        logger.info(f"Batch formatting {len(citations)} citations")

        results = []
        for citation_request in citations:
            formatted = format_citation_all_styles(
                title=citation_request.title,
                authors=citation_request.authors,
                year=citation_request.year,
                journal=citation_request.journal,
                volume=citation_request.volume,
                issue=citation_request.issue,
                pages=citation_request.pages,
                doi=citation_request.doi,
                url=citation_request.url
            )

            # Filter to requested styles
            filtered = {
                style: citation
                for style, citation in formatted.items()
                if style in citation_request.styles
            }

            results.append({
                "title": citation_request.title,
                "citations": filtered
            })

        return {
            "success": True,
            "formatted_citations": results,
            "total": len(results)
        }

    except Exception as e:
        logger.error(f"Batch citation formatting failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to format citations: {str(e)}")


# ============================================
# Citation Management Endpoints
# ============================================

@router.post("/create")
async def create_citation(
    request: CitationCreateRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Create a new citation in the project's citation library.

    Args:
        request: Citation metadata

    Returns:
        Created citation with formatted versions in all styles

    Requirements: Task 3.1 - Citation management API
    """
    try:
        logger.info(f"Creating citation for: {request.title[:50]}...")

        # Generate formatted citations
        formatted = format_citation_all_styles(
            title=request.title,
            authors=request.authors,
            year=str(request.year) if request.year else "n.d.",
            journal=request.journal,
            doi=request.doi,
            url=request.url
        )

        # Generate citation key (e.g., "Smith2023")
        first_author = request.authors[0] if request.authors else "Unknown"
        author_last_name = first_author.split()[-1] if " " in first_author else first_author
        citation_key = f"{author_last_name}{request.year}" if request.year else author_last_name

        # Create citation record
        citation_data = {
            "project_id": request.project_id,
            "user_id": user_id,
            "document_id": request.document_id,
            "title": request.title,
            "authors": request.authors,
            "year": request.year,
            "journal_name": request.journal_name,
            "doi": request.doi,
            "arxiv_id": request.arxiv_id,
            "url": request.url,
            "formatted_citations": formatted,
            "citation_key": citation_key,
            "is_from_project": request.document_id is not None,
            "times_used": 0
        }

        insert_response = supabase.table("citations").insert(citation_data).execute()

        logger.info(f"Created citation with ID: {insert_response.data[0]['id'] if insert_response.data else 'unknown'}")

        return {
            "success": True,
            "citation": insert_response.data[0] if insert_response.data else None
        }

    except Exception as e:
        logger.error(f"Citation creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create citation: {str(e)}")


@router.get("/project/{project_id}")
async def get_project_citations(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get all citations for a project.

    Args:
        project_id: Project ID

    Returns:
        List of all citations in the project's citation library

    Requirements: Task 3.1 - Citation retrieval
    """
    try:
        logger.info(f"Fetching citations for project={project_id}")

        # Verify user has access to project
        project_response = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).single().execute()

        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found or access denied")

        # Fetch citations
        citations_response = supabase.table("citations").select("*").eq("project_id", project_id).order("created_at", desc=True).execute()

        return {
            "success": True,
            "citations": citations_response.data,
            "total": len(citations_response.data)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch project citations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch citations: {str(e)}")


# ============================================
# Citation Analysis Endpoints
# ============================================

@router.post("/analyze/draft/{draft_id}")
async def analyze_draft_citations(
    draft_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Analyze all citations in a draft.

    Extracts citations, detects duplicates, assesses quality, and identifies patterns.

    Returns:
        Comprehensive citation analysis report

    Requirements: Task 3.2 - Citation analysis endpoint
    """
    try:
        logger.info(f"Analyzing citations for draft={draft_id}")

        # Verify user has access to draft
        draft_response = supabase.table("drafts").select("*").eq("id", draft_id).eq("user_id", user_id).single().execute()

        if not draft_response.data:
            raise HTTPException(status_code=404, detail="Draft not found or access denied")

        draft = draft_response.data

        # Download draft text
        file_url = draft.get("file_url")
        if not file_url:
            raise HTTPException(status_code=400, detail="Draft has no file URL")

        # Extract storage path and download
        path_parts = file_url.split("/drafts/")
        if len(path_parts) < 2:
            raise HTTPException(status_code=400, detail="Invalid file URL format")

        storage_path = path_parts[1]
        file_bytes = supabase.storage.from_("drafts").download(storage_path)

        # Extract text
        from app.services.draft_processing import extract_text
        file_type = draft.get("file_type", "pdf")
        extracted_data = await extract_text(file_bytes, file_type)
        draft_text = extracted_data["full_text"]

        # Extract citations
        citations = extract_citations_from_draft(draft_text)

        # Detect duplicates
        duplicates = detect_duplicate_citations(citations)

        # Calculate statistics
        citation_count = len(citations)
        unique_citations = len(set(c.get("citation_string", "") for c in citations))
        citation_formats = {}
        for citation in citations:
            fmt = citation.get("format", "unknown")
            citation_formats[fmt] = citation_formats.get(fmt, 0) + 1

        # Calculate citation quality score (simple version)
        quality_score = 0.0
        if citation_count > 0:
            # Base score on number of citations
            if citation_count >= 20:
                quality_score = 0.8
            elif citation_count >= 10:
                quality_score = 0.6
            else:
                quality_score = 0.4

            # Bonus for diversity (unique citations)
            if unique_citations > 0:
                diversity_ratio = unique_citations / citation_count
                quality_score += diversity_ratio * 0.2

            quality_score = min(1.0, quality_score)

        # Update draft with citation analysis
        update_data = {
            "citation_count": citation_count,
            "citation_quality_score": quality_score,
            "citation_analysis": {
                "total_citations": citation_count,
                "unique_citations": unique_citations,
                "citation_formats": citation_formats,
                "duplicates_found": len(duplicates),
                "analyzed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
        }

        supabase.table("drafts").update(update_data).eq("id", draft_id).execute()

        logger.info(f"Citation analysis complete: {citation_count} citations found")

        return {
            "success": True,
            "analysis": {
                "total_citations": citation_count,
                "unique_citations": unique_citations,
                "citation_formats": citation_formats,
                "duplicates": duplicates,
                "quality_score": round(quality_score, 2),
                "citations": citations[:20]  # Return first 20 for preview
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Citation analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze citations: {str(e)}")


@router.post("/validate")
async def validate_citation(
    citation_string: str,
    expected_format: str = "apa",
    user_id: str = Depends(get_current_user)
):
    """
    Validate a citation string against a specific format.

    Args:
        citation_string: Citation to validate
        expected_format: Expected format (apa, ieee, mla, chicago, any)

    Returns:
        Validation result with errors and warnings

    Requirements: Task 3.2 - Citation validation endpoint
    """
    try:
        logger.info(f"Validating citation: {citation_string[:50]}...")

        result = validate_citation_format(citation_string, expected_format)

        return {
            "success": True,
            "validation": result
        }

    except Exception as e:
        logger.error(f"Citation validation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate citation: {str(e)}")


# ============================================
# Citation Deletion Endpoints
# ============================================

@router.delete("/citations/{citation_id}")
async def delete_citation(
    citation_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a citation.

    This will:
    - Remove the citation record
    - Set citation_suggestions.suggested_citation_id to NULL (CASCADE handled by DB)

    Args:
        citation_id: ID of citation to delete

    Returns:
        Deletion confirmation
    """
    try:
        # Verify citation exists and user owns the project
        citation_res = supabase.table("citations")\
            .select("*, projects!inner(user_id)")\
            .eq("id", citation_id)\
            .execute()

        if not citation_res.data:
            raise HTTPException(status_code=404, detail="Citation not found")

        citation = citation_res.data[0]
        if citation["projects"]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this citation")

        # Delete citation (CASCADE will handle citation_suggestions)
        delete_res = supabase.table("citations").delete().eq("id", citation_id).execute()

        if not delete_res.data:
            raise HTTPException(status_code=404, detail="Citation not found or already deleted")

        logger.info(f"Citation {citation_id} deleted by user {user_id}")

        return {
            "success": True,
            "message": "Citation deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete citation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete citation: {str(e)}")


@router.delete("/projects/{project_id}/citations")
async def delete_project_citations(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete all citations for a project.

    Args:
        project_id: ID of project

    Returns:
        Deletion count
    """
    try:
        # Verify project ownership
        project_res = supabase.table("projects")\
            .select("id")\
            .eq("id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Delete all citations for project
        delete_res = supabase.table("citations")\
            .delete()\
            .eq("project_id", project_id)\
            .execute()

        deleted_count = len(delete_res.data) if delete_res.data else 0

        logger.info(f"Deleted {deleted_count} citations from project {project_id}")

        return {
            "success": True,
            "message": f"Deleted {deleted_count} citation(s)",
            "deleted_count": deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete project citations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete citations: {str(e)}")


@router.delete("/suggestions/{suggestion_id}")
async def delete_citation_suggestion(
    suggestion_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a citation suggestion.

    Args:
        suggestion_id: ID of citation suggestion to delete

    Returns:
        Deletion confirmation
    """
    try:
        # Verify suggestion exists and user owns the draft
        suggestion_res = supabase.table("citation_suggestions")\
            .select("*, drafts!inner(user_id)")\
            .eq("id", suggestion_id)\
            .execute()

        if not suggestion_res.data:
            raise HTTPException(status_code=404, detail="Citation suggestion not found")

        suggestion = suggestion_res.data[0]
        if suggestion["drafts"]["user_id"] != user_id:
            raise HTTPException(status_code=403, detail="Unauthorized to delete this suggestion")

        # Delete suggestion
        delete_res = supabase.table("citation_suggestions")\
            .delete()\
            .eq("id", suggestion_id)\
            .execute()

        if not delete_res.data:
            raise HTTPException(status_code=404, detail="Suggestion not found or already deleted")

        logger.info(f"Citation suggestion {suggestion_id} deleted by user {user_id}")

        return {
            "success": True,
            "message": "Citation suggestion deleted successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete citation suggestion: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete suggestion: {str(e)}")


@router.delete("/drafts/{draft_id}/suggestions")
async def delete_draft_citation_suggestions(
    draft_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete all citation suggestions for a draft.

    Args:
        draft_id: ID of draft

    Returns:
        Deletion count
    """
    try:
        # Verify draft ownership
        draft_res = supabase.table("drafts")\
            .select("id, active_analysis_run_id")\
            .eq("id", draft_id)\
            .eq("user_id", user_id)\
            .execute()

        if not draft_res.data:
            raise HTTPException(status_code=404, detail="Draft not found")
        active_run_id = draft_res.data[0].get("active_analysis_run_id")

        # Delete all suggestions for draft
        delete_query = supabase.table("citation_suggestions")\
            .delete()\
            .eq("draft_id", draft_id)
        if active_run_id:
            delete_query = delete_query.eq("analysis_run_id", active_run_id).eq("is_published", True)
        else:
            delete_query = delete_query.eq("is_published", True)
        delete_res = delete_query.execute()

        deleted_count = len(delete_res.data) if delete_res.data else 0

        logger.info(f"Deleted {deleted_count} citation suggestions from draft {draft_id}")

        return {
            "success": True,
            "message": f"Deleted {deleted_count} citation suggestion(s)",
            "deleted_count": deleted_count
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete draft citation suggestions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete suggestions: {str(e)}")
