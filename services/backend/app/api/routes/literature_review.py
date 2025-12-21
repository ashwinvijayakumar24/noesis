"""
Literature Review API Endpoints

Provides endpoints for generating literature reviews from analyzed documents.
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import Response
from app.core.supabase_client import supabase
from typing import Optional
from pydantic import BaseModel, Field

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


class LiteratureReviewRequest(BaseModel):
    structure: str = Field(default="thematic", description="Review structure: chronological, thematic, or methodological")
    theme: Optional[str] = Field(default=None, description="Optional specific theme to focus on")
    target_words: int = Field(default=1500, ge=500, le=3000, description="Target word count (500-3000)")


@router.get("/templates")
def get_literature_review_templates():
    """
    Get available literature review templates.

    Returns list of templates with their descriptions.
    """
    from app.services.literature_review import get_review_templates

    templates = get_review_templates()
    return {"templates": templates}


@router.post("/projects/{project_id}/generate")
def generate_project_literature_review(
    project_id: str,
    request: LiteratureReviewRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Generate a literature review for a project.

    This endpoint:
    1. Fetches all analyzed documents in the project
    2. Generates a structured literature review using GPT-4o
    3. Returns the review with proper author-year citations

    Structures available:
    - chronological: Organizes by publication date
    - thematic: Organizes by themes/topics
    - methodological: Organizes by research methods

    Requirements:
    - All documents in the project must be analyzed
    - Documents must have citation metadata extracted
    """
    print(f"[LIT-REVIEW] Generating review for project_id={project_id}, structure={request.structure}")

    # 1. Verify project belongs to user
    project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Get all documents for this project
    documents_res = supabase.table("documents").select("id, title, status, analysis")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not documents_res.data or len(documents_res.data) == 0:
        raise HTTPException(status_code=400, detail="No documents in project. Add documents first.")

    documents = documents_res.data

    # 3. Verify all documents are analyzed
    unanalyzed_docs = []
    docs_without_citations = []

    for doc in documents:
        if doc.get('status') != 'analyzed' or not doc.get('analysis'):
            unanalyzed_docs.append(doc['title'])
        elif not doc.get('analysis', {}).get('citation_metadata'):
            docs_without_citations.append(doc['title'])

    if unanalyzed_docs:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "All documents must be analyzed before generating literature review",
                "unanalyzed_documents": unanalyzed_docs
            }
        )

    if docs_without_citations:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Some documents are missing citation metadata. Please re-analyze them.",
                "documents_missing_citations": docs_without_citations
            }
        )

    # 4. Validate structure
    valid_structures = ["chronological", "thematic", "methodological"]
    if request.structure not in valid_structures:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid structure. Must be one of: {', '.join(valid_structures)}"
        )

    # 5. Generate literature review
    try:
        from app.services.literature_review import generate_literature_review

        result = generate_literature_review(
            documents=documents,
            structure=request.structure,
            theme=request.theme,
            target_words=request.target_words
        )

        print(f"[LIT-REVIEW] Successfully generated {request.structure} review")

        return {
            "review": result["review"],
            "review_body": result["review_body"],
            "references": result["references"],
            "metadata": result["metadata"]
        }

    except Exception as e:
        print(f"[LIT-REVIEW] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate literature review: {str(e)}")


@router.post("/projects/{project_id}/generate/export")
def export_literature_review(
    project_id: str,
    request: LiteratureReviewRequest,
    format: str = "pdf",
    user_id: str = Depends(get_current_user)
):
    """
    Generate and export a literature review in the specified format.

    Supported formats:
    - pdf: PDF document (priority 1)
    - latex: LaTeX source (.tex) (priority 2)
    - markdown: Markdown (.md) (priority 3)

    This endpoint generates the review and returns it as a downloadable file.
    """
    print(f"[LIT-REVIEW-EXPORT] Generating {format} export for project_id={project_id}")

    # Validate format
    valid_formats = ["pdf", "latex", "markdown"]
    if format not in valid_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid format. Must be one of: {', '.join(valid_formats)}"
        )

    # Generate the review first (reuse the generation logic)
    # This is a simplified version - in production, you might cache the generated review
    try:
        # Generate review using the same logic as the generate endpoint
        from app.services.literature_review import generate_literature_review

        # 1. Verify project and get documents (same as generate endpoint)
        project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        documents_res = supabase.table("documents").select("id, title, status, analysis")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        if not documents_res.data or len(documents_res.data) == 0:
            raise HTTPException(status_code=400, detail="No documents in project")

        documents = documents_res.data

        # Verify all analyzed
        unanalyzed = [d['title'] for d in documents if d.get('status') != 'analyzed' or not d.get('analysis')]
        if unanalyzed:
            raise HTTPException(status_code=400, detail={"message": "All documents must be analyzed", "unanalyzed_documents": unanalyzed})

        # 2. Generate review
        result = generate_literature_review(
            documents=documents,
            structure=request.structure,
            theme=request.theme,
            target_words=request.target_words
        )

        # 3. Export to requested format
        from app.services.export import export_to_markdown, export_to_latex, markdown_to_pdf

        if format == "markdown":
            content = export_to_markdown(result["review"], result["metadata"])
            media_type = "text/markdown"
            filename = f"literature_review_{request.structure}.md"

        elif format == "latex":
            content = export_to_latex(result["review"], result["metadata"])
            media_type = "application/x-latex"
            filename = f"literature_review_{request.structure}.tex"

        elif format == "pdf":
            # Generate PDF from markdown
            pdf_bytes = markdown_to_pdf(result["review"], result["metadata"])
            return Response(
                content=pdf_bytes,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=literature_review_{request.structure}.pdf"
                }
            )

        # Return text-based formats
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[LIT-REVIEW-EXPORT] ERROR: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to export literature review: {str(e)}")
