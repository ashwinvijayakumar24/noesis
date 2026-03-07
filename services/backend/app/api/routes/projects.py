from fastapi import APIRouter, HTTPException, Depends, Header, Response
from app.core.supabase_client import supabase
from app.services.citation_management import format_citation_bibtex
from app.core.security_middleware import SecureAuthValidator, limiter
from app.schemas.projects import ProjectBundle, Dataset, Document
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
import datetime
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"  # Don't expose environment details
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
    """
    Delete a project and all associated data:
    - Storage files (documents, drafts)
    - Database records (CASCADE handled by DB constraints)
    """
    try:
        # Verify project exists and belongs to user
        project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Step 1: Clean up document storage files
        documents_res = supabase.table("documents")\
            .select("file_url")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        deleted_documents = 0
        if documents_res.data:
            for doc in documents_res.data:
                if doc.get("file_url"):
                    try:
                        # Extract storage path from URL
                        # Format: https://{project}.supabase.co/storage/v1/object/public/documents/{user_id}/{filename}
                        storage_path = doc["file_url"].split("/documents/")[-1]
                        supabase.storage.from_("documents").remove([storage_path])
                        deleted_documents += 1
                        logger.info(f"Deleted document file: {storage_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete document file {doc['file_url']}: {str(e)}")

        # Step 2: Clean up draft storage files
        drafts_res = supabase.table("drafts")\
            .select("file_url")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()

        deleted_drafts = 0
        if drafts_res.data:
            for draft in drafts_res.data:
                if draft.get("file_url"):
                    try:
                        # Extract storage path from URL
                        storage_path = draft["file_url"].split("/drafts/")[-1]
                        supabase.storage.from_("drafts").remove([storage_path])
                        deleted_drafts += 1
                        logger.info(f"Deleted draft file: {storage_path}")
                    except Exception as e:
                        logger.warning(f"Failed to delete draft file {draft['file_url']}: {str(e)}")

        # Step 3: Delete project (CASCADE will handle all database records)
        res = supabase.table("projects").delete().eq("id", project_id).eq("user_id", user_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Project not found or already deleted")

        logger.info(
            f"Project {project_id} deleted successfully. "
            f"Cleaned up {deleted_documents} document files and {deleted_drafts} draft files."
        )

        return {
            "message": "Project and all associated data deleted successfully",
            "storage_cleanup": {
                "documents_deleted": deleted_documents,
                "drafts_deleted": deleted_drafts
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project {project_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete project: {str(e)}")

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

        # 6. Auto-generate research questions + paper recs on FIRST insights generation only
        existing_rq = supabase.table("research_questions").select("id", count="exact")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()
        rq_count = existing_rq.count if existing_rq.count is not None else 0

        if rq_count == 0:
            print(f"[INSIGHTS-BG] First insights generation — auto-generating research questions")
            try:
                from app.services.research_questions import generate_research_questions
                questions = generate_research_questions(insights)
                for q in questions[:5]:
                    supabase.table("research_questions").insert({
                        "project_id": project_id,
                        "user_id": user_id,
                        "question": q['question'],
                        "rationale": q['rationale'],
                        "suggested_methodology": q['suggested_methodology'],
                        "gap_category": q['gap_category'],
                        "status": "new"
                    }).execute()
                print(f"[INSIGHTS-BG] Auto-generated {min(len(questions), 5)} research questions")
            except Exception as rq_err:
                print(f"[INSIGHTS-BG] Auto-RQ generation failed (non-fatal): {rq_err}")

        existing_pr = supabase.table("paper_recommendations").select("id", count="exact")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .execute()
        pr_count = existing_pr.count if existing_pr.count is not None else 0

        if pr_count == 0:
            print(f"[INSIGHTS-BG] First insights generation — auto-generating paper recommendations")
            try:
                from app.services.paper_recommendations import generate_paper_recommendations
                proj_res = supabase.table("projects").select("title, description").eq("id", project_id).execute()
                project_data = {"title": proj_res.data[0].get("title", "") if proj_res.data else "", "description": proj_res.data[0].get("description", "") if proj_res.data else ""}
                papers = generate_paper_recommendations(
                    project_data=project_data,
                    insights=insights,
                    research_questions=[],
                    limit=5
                )
                for paper in papers[:5]:
                    supabase.table("paper_recommendations").insert({
                        "project_id": project_id,
                        "user_id": user_id,
                        **paper,
                        "status": "new"
                    }).execute()
                print(f"[INSIGHTS-BG] Auto-generated {min(len(papers), 5)} paper recommendations")
            except Exception as pr_err:
                print(f"[INSIGHTS-BG] Auto-PR generation failed (non-fatal): {pr_err}")

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

    # 6. Submit Celery task (Phase 3.3)
    from app.tasks.insights_analysis import generate_insights_task
    task_result = generate_insights_task.delay(project_id, user_id)

    print(f"[INSIGHTS] Celery insights analysis task submitted for project_id={project_id} (task_id={task_result.id})")

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


@router.get("/{project_id}/export-bibtex")
async def export_project_bibtex(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Export all documents in a project as a BibTeX (.bib) file.

    Args:
        project_id: Project ID to export citations from
        user_id: Authenticated user ID (from JWT token)

    Returns:
        BibTeX file content with all project citations
    """
    try:
        # Verify project ownership
        project = supabase.table("projects")\
            .select("*")\
            .eq("id", project_id)\
            .eq("user_id", user_id)\
            .single()\
            .execute()

        if not project.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Fetch all documents in the project
        documents = supabase.table("documents")\
            .select("*")\
            .eq("project_id", project_id)\
            .eq("user_id", user_id)\
            .order("title")\
            .execute()

        if not documents.data:
            raise HTTPException(status_code=404, detail="No documents found in project")

        # Generate BibTeX entries
        bibtex_entries = []
        for doc in documents.data:
            analysis = doc.get("analysis", {})
            citation_metadata = analysis.get("citation_metadata", {})

            # Skip documents without metadata
            if not citation_metadata:
                logger.warning(f"Document {doc['id']} has no citation metadata, skipping")
                continue

            # Extract metadata fields
            title = citation_metadata.get("title", doc.get("title", "Untitled"))
            authors = citation_metadata.get("authors", [])
            year = citation_metadata.get("year", "n.d.")
            journal = citation_metadata.get("venue") or citation_metadata.get("journal")
            volume = citation_metadata.get("volume")
            issue = citation_metadata.get("issue")
            pages = citation_metadata.get("pages")
            doi = citation_metadata.get("doi")
            url = doc.get("file_url")

            # Determine entry type (article vs inproceedings)
            booktitle = citation_metadata.get("booktitle")
            entry_type = "inproceedings" if booktitle else "article"

            # Generate BibTeX entry
            bibtex_entry = format_citation_bibtex(
                title=title,
                authors=authors,
                year=year,
                journal=journal,
                volume=volume,
                issue=issue,
                pages=pages,
                doi=doi,
                url=url,
                booktitle=booktitle,
                entry_type=entry_type
            )

            bibtex_entries.append(bibtex_entry)

        if not bibtex_entries:
            raise HTTPException(status_code=404, detail="No documents with citation metadata found")

        # Combine all entries
        bibtex_content = "\n\n".join(bibtex_entries)

        # Add header comment
        project_title = project.data.get("title", "Noesis Project")
        header = f"% BibTeX export from Noesis\n% Project: {project_title}\n% Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n% Total entries: {len(bibtex_entries)}\n\n"
        bibtex_content = header + bibtex_content

        # Return as downloadable file
        safe_filename = project_title.replace(" ", "_").replace("/", "_")
        return Response(
            content=bibtex_content,
            media_type="application/x-bibtex",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}_citations.bib"'
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export BibTeX: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to export BibTeX: {str(e)}")


# ---------------------------------------------------------------------------
# Draft version history & cross-draft memory
# (Mounted at /projects so paths resolve to /projects/{project_id}/drafts/...)
# ---------------------------------------------------------------------------

@router.get("/{project_id}/drafts/timeline")
def get_drafts_timeline(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """Version history timeline for all analyzed drafts in a project."""
    drafts_response = supabase.table("drafts")\
        .select("id, title, version, created_at")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .eq("status", "analyzed")\
        .order("version", desc=False)\
        .execute()

    drafts = drafts_response.data or []
    if not drafts:
        return {"timeline": []}

    timeline = []
    prev_score = None

    for draft in drafts:
        draft_id = draft["id"]

        feedback_res = supabase.table("reviewer_feedback")\
            .select("severity").eq("draft_id", draft_id).execute()
        gaps_res = supabase.table("coverage_gaps")\
            .select("priority").eq("draft_id", draft_id).execute()
        claims_res = supabase.table("draft_claims")\
            .select("id").eq("draft_id", draft_id).execute()

        feedback_items = feedback_res.data or []
        gap_items = gaps_res.data or []
        claim_count = len(claims_res.data or [])

        critical = sum(1 for f in feedback_items if f.get("severity") == "critical")
        major = sum(1 for f in feedback_items if f.get("severity") == "major")
        high_gaps = sum(1 for g in gap_items if g.get("priority") == "high")
        health_score = max(0, 100 - (critical * 15) - (major * 8) - (high_gaps * 5))

        delta = (health_score - prev_score) if prev_score is not None else None
        prev_score = health_score

        timeline.append({
            "draft_id": draft_id,
            "title": draft["title"],
            "version": draft["version"],
            "created_at": draft["created_at"],
            "health_score": health_score,
            "score_delta": delta,
            "critical_issues": critical,
            "major_issues": major,
            "claim_count": claim_count,
            "gap_count": len(gap_items),
        })

    return {"timeline": timeline}


@router.get("/{project_id}/drafts/recurring-patterns")
async def get_recurring_patterns(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """Identify recurring feedback patterns across all analyzed drafts (3+ needed)."""
    try:
        from app.services.draft_memory import identify_recurring_patterns
        result = await identify_recurring_patterns(project_id, user_id)
        return result
    except Exception as e:
        logger.error(f"Failed to identify recurring patterns for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to identify patterns: {str(e)}")
