import datetime
import logging
import os
from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Header, Response, UploadFile, File, Request
from pydantic import BaseModel, Field

from app.core.api_errors import build_error_detail, raise_api_error
from app.core.security_middleware import SecureAuthValidator, limiter
from app.core.supabase_client import supabase
from app.schemas.projects import ProjectBundle, Dataset, Document, ProjectCreate, ProjectUpdate
from app.services.citation_management import format_citation_bibtex, parse_bibtex_file
from app.services.progress_tracking import (
    clear_progress_snapshot,
    get_progress_snapshot,
    store_progress_snapshot,
)
from app.services.quota_management import get_project_limit

router = APIRouter()
logger = logging.getLogger(__name__)
ACTIVE_INSIGHTS_STATUSES = {"analyzing"}
INSIGHTS_DAILY_LIMITS = {
    "free": 5,
    "pro": None,
    "team": None,
    "enterprise": None,
    "admin": None,
}


def _merge_project_metadata(existing: Optional[dict], **updates) -> dict:
    merged = dict(existing or {})
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    return merged

# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"  # Don't expose environment details
        )

    try:
        return SecureAuthValidator.get_user_id(authorization, supabase)
    except Exception as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


def _validate_bibtex_entry(entry: dict) -> list:
    issues = []
    if not entry.get("title") or entry.get("title") == "Untitled":
        issues.append("missing title")
    if not entry.get("authors"):
        issues.append("missing authors")
    if not entry.get("year"):
        issues.append("missing year")
    return issues


def _get_redis_client():
    import redis as redis_lib

    return redis_lib.Redis(
        host=os.getenv("REDIS_HOST", "redis"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        decode_responses=True,
    )


def _get_insights_quota(user_id: str, plan_tier: str) -> Dict[str, Any]:
    normalized_plan = (plan_tier or "free").lower()
    limit = INSIGHTS_DAILY_LIMITS.get(normalized_plan, 5)

    if limit is None:
        return {
            "used": 0,
            "limit": None,
            "remaining": None,
            "is_unlimited": True,
        }

    key = f"daily_insights:{user_id}:{date.today().isoformat()}"
    try:
        used = int(_get_redis_client().get(key) or 0)
    except Exception as exc:
        logger.warning(f"[INSIGHTS] Redis quota read failed (fail open): {exc}")
        used = 0

    return {
        "used": used,
        "limit": limit,
        "remaining": max(limit - used, 0),
        "is_unlimited": False,
    }


def _enforce_insights_refresh_quota(user_id: str, plan_tier: str) -> Dict[str, Any]:
    quota = _get_insights_quota(user_id, plan_tier)
    if quota["is_unlimited"]:
        return quota

    if quota["used"] >= quota["limit"]:
        raise_api_error(
            429,
            code="quota_exceeded",
            title="Literature Map refresh limit reached",
            message=f"Free plan includes {quota['limit']} Literature Map refreshes per day.",
            next_action="upgrade",
            retryable=False,
            quota_type="literature_map_refreshes",
            used=quota["used"],
            limit=quota["limit"],
            remaining=quota["remaining"],
        )

    key = f"daily_insights:{user_id}:{date.today().isoformat()}"
    try:
        pipe = _get_redis_client().pipeline()
        pipe.incr(key)
        pipe.expire(key, 90000)
        pipe.execute()
        quota["used"] += 1
        quota["remaining"] = max(quota["limit"] - quota["used"], 0)
    except Exception as exc:
        logger.warning(f"[INSIGHTS] Redis quota increment failed (fail open): {exc}")

    return quota


def _build_insights_staleness(
    *,
    insights_updated_at: Optional[str],
    insights_doc_count: int,
    current_analyzed_count: int,
    latest_document_updated_at: Optional[str],
) -> Dict[str, Any]:
    count_changed = current_analyzed_count != (insights_doc_count or 0)

    document_changed = False
    if insights_updated_at and latest_document_updated_at:
        try:
            document_changed = latest_document_updated_at > insights_updated_at
        except Exception:
            document_changed = False

    is_stale = count_changed or document_changed
    if count_changed and document_changed:
        stale_reason = "documents_changed_and_count_changed"
    elif count_changed:
        stale_reason = "document_count_changed"
    elif document_changed:
        stale_reason = "documents_changed"
    else:
        stale_reason = None

    return {
        "is_stale": is_stale,
        "stale_reason": stale_reason,
    }


def _group_recommendations_by_context(recommendations: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary_recommendations: List[Dict[str, Any]] = []
    gap_recommendations_by_title: Dict[str, List[Dict[str, Any]]] = {}
    conflict_recommendations_by_topic: Dict[str, List[Dict[str, Any]]] = {}

    for recommendation in recommendations:
        if recommendation.get("status") == "dismissed":
            continue

        summary_recommendations.append(recommendation)

        context = recommendation.get("recommendation_context") or {}
        for gap_title in context.get("gap_titles", []) or []:
            gap_recommendations_by_title.setdefault(gap_title, []).append(recommendation)
        for topic in context.get("conflict_topics", []) or []:
            conflict_recommendations_by_topic.setdefault(topic, []).append(recommendation)

    return {
        "summary_recommendations": summary_recommendations[:5],
        "gap_recommendations_by_title": {
            title: grouped[:3] for title, grouped in gap_recommendations_by_title.items()
        },
        "conflict_recommendations_by_topic": {
            topic: grouped[:3] for topic, grouped in conflict_recommendations_by_topic.items()
        },
    }


# CREATE
@router.post("/")
def create_project(payload: ProjectCreate, user_id: str = Depends(get_current_user)):
    # Enforce per-plan project limit
    quota_res = supabase.table('user_quotas').select('plan_tier').eq('user_id', user_id).execute()
    plan_tier = quota_res.data[0]['plan_tier'] if quota_res.data else 'free'
    project_limit = get_project_limit(plan_tier)

    count_res = supabase.table('projects').select('id', count='exact').eq('user_id', user_id).execute()
    project_count = count_res.count or 0

    if project_count >= project_limit:
        upgrade_hint = " Upgrade to Pro for more projects." if plan_tier == 'free' else ""
        raise HTTPException(
            status_code=403,
            detail={
                "message": f"{plan_tier.title()} plan is limited to {project_limit} projects.{upgrade_hint}",
                "quota_type": "projects",
                "limit": project_limit,
                "current": project_count,
            }
        )

    data = {
        "user_id": user_id,
        "title": payload.title,
        "description": payload.description,
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
    projects = res.data or []

    if not projects:
        return []

    # Batch-load related project_ids once instead of issuing one count query per project.
    project_ids = {project["id"] for project in projects}
    document_counts: dict[str, int] = {project_id: 0 for project_id in project_ids}
    draft_counts: dict[str, int] = {project_id: 0 for project_id in project_ids}
    documents_res = supabase.table("documents").select("project_id").eq("user_id", user_id).execute()
    drafts_res = supabase.table("drafts").select("project_id").eq("user_id", user_id).execute()

    for document in documents_res.data or []:
        project_id = document.get("project_id")
        if project_id in document_counts:
            document_counts[project_id] += 1

    for draft in drafts_res.data or []:
        project_id = draft.get("project_id")
        if project_id in draft_counts:
            draft_counts[project_id] += 1

    for project in projects:
        project["document_count"] = document_counts.get(project["id"], 0)
        project["draft_count"] = draft_counts.get(project["id"], 0)

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
def update_project(project_id: str, payload: ProjectUpdate, user_id: str = Depends(get_current_user)):
    updates = {"updated_at": datetime.datetime.utcnow().isoformat()}
    if payload.title is not None:
        updates["title"] = payload.title
    if "description" in payload.model_fields_set:
        updates["description"] = payload.description
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

# BIBTEX IMPORT
@router.post("/{project_id}/import-bibtex")
@limiter.limit("10/minute")
async def import_bibtex(
    request: Request,
    project_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user)
):
    """
    Import a BibTeX (.bib) file into a project as metadata-only document records.

    Each BibTeX entry becomes a document with source_type='bibtex_import' and
    resolution_status='resolving'. A background Celery task then attempts to find
    open-access PDFs and run full analysis for each entry.

    Supports entries exported from Zotero, Mendeley, Endnote, and most reference managers.
    """
    from app.services.quota_management import check_quota, increment_quota_usage, QuotaExceededError

    # Verify project exists and belongs to user
    project_res = supabase.table("projects").select("id").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise_api_error(
            404,
            code="project_not_found",
            title="Project not found",
            message="We could not find that project.",
            next_action="refresh",
        )

    # Validate file type
    filename = file.filename or ""
    if not filename.lower().endswith('.bib'):
        raise_api_error(
            400,
            code="invalid_file_type",
            title="Invalid file type",
            message="The selected file must be a BibTeX (.bib) file.",
            next_action="fix_file",
            retryable=False,
        )

    # Read and parse file
    try:
        content_bytes = await file.read()
        try:
            bibtex_content = content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            bibtex_content = content_bytes.decode('latin-1')
    except Exception as e:
        raise_api_error(
            400,
            code="file_parse_failed",
            title="BibTeX file could not be read",
            message="We could not read this BibTeX file.",
            details=[str(e)[:200]],
            next_action="fix_file",
            retryable=False,
        )

    # Parse BibTeX entries
    try:
        parsed_entries = parse_bibtex_file(bibtex_content)
    except Exception as e:
        logger.error(f"BibTeX parse error: {e}")
        raise_api_error(
            400,
            code="file_parse_failed",
            title="BibTeX file could not be processed",
            message="This BibTeX file appears incorrectly formatted and could not be parsed.",
            details=[
                "Ensure the file is a valid .bib export from Zotero, Mendeley, or another reference manager.",
                str(e)[:200],
            ],
            next_action="fix_file",
            retryable=False,
        )

    if not parsed_entries:
        raise_api_error(
            400,
            code="file_parse_failed",
            title="BibTeX file could not be processed",
            message="No valid BibTeX entries were found. The file appears empty or incorrectly formatted.",
            details=[
                "Ensure the file is a valid .bib export from Zotero, Mendeley, or another reference manager."
            ],
            next_action="fix_file",
            retryable=False,
        )

    # Cap at 500 entries per import to prevent abuse
    MAX_ENTRIES = 500
    if len(parsed_entries) > MAX_ENTRIES:
        parsed_entries = parsed_entries[:MAX_ENTRIES]

    # Check bib_import quota (10 refs/month on free tier)
    # Only check — we'll increment after all records are created
    try:
        await check_quota(user_id, "bib_import")
    except QuotaExceededError as qe:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "quota_exceeded",
                "quota_type": qe.quota_type,
                "limit": qe.limit,
                "current": qe.current,
                "message": str(qe),
            }
        )

    # Create document records for each entry
    now = datetime.datetime.utcnow().isoformat()
    imported = 0
    skipped = 0
    entry_errors: List[Dict[str, Any]] = []
    created_ids: List[str] = []

    for i, entry in enumerate(parsed_entries, start=1):
        title = entry.get('title', 'Untitled').strip() or 'Untitled'
        authors = entry.get('authors', [])
        year = entry.get('year', '')
        issues = _validate_bibtex_entry(entry)

        if issues:
            skipped += 1
            entry_errors.append({
                "index": i,
                "title": entry.get("title", "Unknown"),
                "warnings": issues,
                "status": "skipped",
            })
            continue

        try:
            doc_record = {
                "user_id": user_id,
                "project_id": project_id,
                "title": title,
                "description": None,
                "file_url": "",
                "file_type": "bibtex_import",
                "file_size": 0,
                "status": "imported",
                "source_type": "bibtex_import",
                "resolution_status": "resolving",
                "metadata": {
                    "import_source": "bibtex",
                    "bibtex_key": entry.get('bibtex_key', ''),
                    "entry_type": entry.get('entry_type', 'article'),
                    "authors": authors,
                    "year": year,
                    "abstract": entry.get('abstract', ''),
                    "doi": entry.get('doi', ''),
                    "url": entry.get('url', ''),
                    "journal": entry.get('journal', ''),
                    "booktitle": entry.get('booktitle', ''),
                    "volume": entry.get('volume', ''),
                    "pages": entry.get('pages', ''),
                    "publisher": entry.get('publisher', ''),
                    "import_timestamp": now,
                },
                "created_at": now,
                "updated_at": now,
            }

            res = supabase.table("documents").insert(doc_record).execute()
            if res.data:
                imported += 1
                doc_id = res.data[0]["id"]
                created_ids.append(doc_id)
            else:
                skipped += 1
                entry_errors.append({
                    "index": i,
                    "title": title,
                    "warnings": ["insert failed"],
                    "status": "skipped",
                })
        except Exception as e:
            logger.warning(f"Failed to import BibTeX entry '{title}': {e}")
            skipped += 1
            entry_errors.append({
                "index": i,
                "title": title,
                "warnings": [str(e)[:200] or "import failed"],
                "status": "skipped",
            })

    if imported == 0:
        detail_lines = []
        for error in entry_errors[:5]:
            warnings = ", ".join(error.get("warnings") or [])
            title = error.get("title") or "Untitled entry"
            detail_lines.append(f"\"{title}\": {warnings or 'entry could not be imported'}")

        raise_api_error(
            400,
            code="file_parse_failed",
            title="BibTeX file could not be processed",
            message="No importable references were found. The BibTeX file appears incorrectly formatted or is missing required fields.",
            details=detail_lines or [
                "Ensure each entry includes at least a title, author list, and year."
            ],
            next_action="fix_file",
            retryable=False,
            entry_errors=entry_errors[:50],
        )

    # Increment bib quota by actual number of records created
    if imported > 0:
        try:
            await increment_quota_usage(user_id, "bib_import", count=imported)
        except Exception as e:
            logger.warning(f"Failed to increment bib quota: {e}")

    # Submit background Celery task for OA PDF resolution
    resolution_started = False
    if created_ids:
        try:
            from app.tasks.bibtex_resolution_task import resolve_bibtex_task
            task = resolve_bibtex_task.delay(created_ids, user_id, project_id)
            logger.info(f"[BIBTEX] Submitted resolution task {task.id} for {len(created_ids)} entries")
            resolution_started = True
        except Exception as e:
            logger.warning(f"[BIBTEX] Failed to submit resolution task: {e}")
            # Non-fatal — documents still imported without resolution

    return {
        "message": f"Imported {imported} references from BibTeX file",
        "imported": imported,
        "skipped": skipped,
        "total_in_file": len(parsed_entries),
        "entry_errors": entry_errors[:50],
        "document_ids": created_ids,
        "resolution_started": resolution_started,
    }


# BIB RESOLUTION STATUS (polled by frontend every 3s while resolving)
@router.get("/{project_id}/bib-resolution-status")
async def get_bib_resolution_status(
    project_id: str,
    user_id: str = Depends(get_current_user),
):
    """
    Return resolution status for all bibtex_import documents in the project.
    Used by the upload modal to show live resolution progress.
    """
    res = supabase.table("documents")\
        .select("id, title, status, source_type, resolution_status, metadata")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .eq("source_type", "bibtex_import")\
        .order("created_at", desc=True)\
        .execute()

    entries = res.data or []
    return {
        "entries": entries,
        "resolving_count": sum(1 for e in entries if e.get("resolution_status") == "resolving"),
        "resolved_count": sum(1 for e in entries if e.get("resolution_status") == "resolved"),
        "unresolved_count": sum(1 for e in entries if e.get("resolution_status") == "unresolved"),
    }


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
        store_progress_snapshot("insights", project_id, "queued", 5, "Queued for Literature Map analysis")

        # 1. Fetch all documents for this project
        store_progress_snapshot("insights", project_id, "collecting_papers", 20, "Collecting analyzed papers")
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
                    'analysis': doc['analysis'],
                    'metadata': doc.get('metadata') or {},
                    'updated_at': doc.get('updated_at'),
                })

        if len(analyzed_docs) == 0:
            raise Exception("No analyzed documents found. Please analyze documents first.")

        print(f"[INSIGHTS-BG] Found {len(analyzed_docs)} analyzed documents")

        # 3. Run insights analysis
        print(f"[INSIGHTS-BG] Running Literature Map analysis")
        store_progress_snapshot("insights", project_id, "building_snapshot", 40, "Building coverage snapshot")
        insights = analyze_project_insights(analyzed_docs)

        # Add timestamp
        insights['analysis_metadata']['timestamp'] = datetime.datetime.utcnow().isoformat()

        # 4. Validate insights
        validate_insights(insights)
        print(f"[INSIGHTS-BG] Insights analysis completed and validated")
        store_progress_snapshot("insights", project_id, "synthesizing_overview", 70, "Synthesizing field overview")

        # 5. Store insights in database (with document count tracking)
        store_progress_snapshot("insights", project_id, "finalizing", 90, "Finalizing Literature Map")
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

        # 6. Always delete and re-generate research questions + paper recommendations on insights regeneration
        print(f"[INSIGHTS-BG] Refreshing research questions — deleting existing and re-generating")
        try:
            supabase.table("research_questions").delete()\
                .eq("project_id", project_id)\
                .eq("user_id", user_id)\
                .execute()
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
            print(f"[INSIGHTS-BG] Re-generated {min(len(questions), 5)} research questions")
        except Exception as rq_err:
            print(f"[INSIGHTS-BG] Auto-RQ generation failed (non-fatal): {rq_err}")

        store_progress_snapshot("insights", project_id, "grouping_recommendations", 82, "Preparing suggested papers")
        print(f"[INSIGHTS-BG] Refreshing auto-generated Discover recommendations")
        try:
            supabase.table("paper_recommendations")\
                .delete()\
                .eq("project_id", project_id)\
                .eq("user_id", user_id)\
                .eq("discovery_type", "recommended")\
                .eq("bib_saved", False)\
                .execute()

            from app.api.routes.paper_recommendations import _generate_and_store_recommendations

            recommendation_result = _generate_and_store_recommendations(
                project_id=project_id,
                user_id=user_id,
                discovery_type="recommended",
                search_query=None,
            )
            print(
                f"[INSIGHTS-BG] Generated {recommendation_result.get('count', 0)} "
                f"Discover recommendations inline for project_id={project_id}"
            )
        except Exception as pr_err:
            print(f"[INSIGHTS-BG] Auto-PR generation failed (non-fatal): {pr_err}")

        store_progress_snapshot("insights", project_id, "finalizing", 100, "Literature Map ready")
        clear_progress_snapshot("insights", project_id)

    except Exception as e:
        print(f"[INSIGHTS-BG] ERROR for project_id={project_id}: {type(e).__name__}: {str(e)}")
        metadata_res = supabase.table("projects").select("insights_metadata").eq("id", project_id).eq("user_id", user_id).execute()
        existing_metadata = (
            metadata_res.data[0].get("insights_metadata") or {}
            if metadata_res.data
            else {}
        )
        error_detail = build_error_detail(
            code="transient_provider_error",
            title="Service under load",
            message="The Literature Map service is under load. We can retry automatically.",
            next_action="retry",
            retryable=True,
            details=[str(e)] if str(e) else None,
        )
        clear_progress_snapshot("insights", project_id)
        # Update status to failed
        supabase.table("projects").update({
            "insights_status": "analyzing",
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "insights_metadata": _merge_project_metadata(
                existing_metadata,
                error=str(e),
                error_type=type(e).__name__,
                error_detail=error_detail,
            ),
        }).eq("id", project_id).eq("user_id", user_id).execute()
        raise


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
    from app.tasks.insights_analysis import generate_insights_task

    # 1. Verify project belongs to user
    project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
    if not project_res.data:
        raise_api_error(
            404,
            code="project_not_found",
            title="Project not found",
            message="We couldn't find that project.",
            next_action="refresh",
        )

    project = project_res.data[0]

    # 2. Check if already analyzing
    if project.get("insights_status") == "analyzing":
        return {
            "message": "Insights analysis already in progress",
            "status": "analyzing"
        }

    # 3. Get all documents for this project (we filter in Python to handle legacy null file_type rows)
    documents_res = supabase.table("documents").select("id, title, status, analysis, source_type, file_type")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not documents_res.data or len(documents_res.data) == 0:
        raise_api_error(
            400,
            code="project_not_ready",
            title="Project not ready",
            message="Add documents before generating a Literature Map.",
            next_action="refresh",
        )

    # Only manually-uploaded PDFs require full analysis to gate insights.
    # BibTeX imports, Zotero imports, and discovered papers are metadata-only and never block.
    NON_PDF_SOURCES = ('bibtex_import', 'zotero_import', 'discovered')
    pdf_docs = [
        d for d in documents_res.data
        if d.get('source_type') not in NON_PDF_SOURCES
        and d.get('file_type') not in ('bibtex_import', 'zotero_import')
    ]

    if not pdf_docs:
        # Project only has BibTeX/discovered references — that's fine, proceed
        print(f"[INSIGHTS] Project {project_id} has no manually-uploaded PDFs; running insights on metadata")

    # 4. Verify all PDF documents are analyzed
    unanalyzed_docs = []
    for doc in pdf_docs:
        if doc.get('status') != 'analyzed':
            unanalyzed_docs.append(doc['title'])

    if unanalyzed_docs:
        raise_api_error(
            400,
            code="project_not_ready",
            title="Documents still processing",
            message="All PDFs must be analyzed before generating a Literature Map.",
            details={"unanalyzed_documents": unanalyzed_docs},
            next_action="refresh",
        )

    print(f"[INSIGHTS] All {len(pdf_docs)} PDF documents are analyzed ({len(documents_res.data)} total)")

    quota_res = supabase.table("user_quotas").select("plan_tier").eq("user_id", user_id).execute()
    plan_tier = quota_res.data[0].get("plan_tier", "free") if quota_res.data else "free"
    quota = _enforce_insights_refresh_quota(user_id, plan_tier)

    # 5. Update status to 'analyzing'
    task_result = generate_insights_task.delay(project_id, user_id)
    queued_progress = store_progress_snapshot("insights", project_id, "queued", 5, "Queued for Literature Map analysis")
    supabase.table("projects").update({
        "insights_status": "analyzing",
        "updated_at": datetime.datetime.utcnow().isoformat(),
        "insights_metadata": _merge_project_metadata(project.get("insights_metadata"), task_id=task_result.id, error_detail=None),
    }).eq("id", project_id).eq("user_id", user_id).execute()

    print(f"[INSIGHTS] Celery insights analysis task submitted for project_id={project_id} (task_id={task_result.id})")

    return {
        "message": "Literature Map analysis started",
        "status": "analyzing",
        "num_documents": len(documents_res.data),
        "quota": quota,
        "task_id": task_result.id,
        "progress": queued_progress,
    }


@router.get("/{project_id}/insights")
def get_project_insights(project_id: str, user_id: str = Depends(get_current_user)):
    print(f"[GET-INSIGHTS] Fetching insights for project_id={project_id}")

    project_res = supabase.table("projects").select("insights, insights_status, insights_updated_at, insights_doc_count, insights_metadata")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise_api_error(
            404,
            code="project_not_found",
            title="Project not found",
            message="We couldn't find that project.",
            next_action="refresh",
        )

    project = project_res.data[0]
    status = project.get("insights_status", "not_analyzed")
    insights = project.get("insights")
    if insights:
        from app.services.project_insights import validate_insights

        validate_insights(insights)
    insights_updated_at = project.get("insights_updated_at")
    insights_doc_count = project.get("insights_doc_count", 0) or 0

    quota_res = supabase.table("user_quotas").select("plan_tier").eq("user_id", user_id).execute()
    plan_tier = quota_res.data[0].get("plan_tier", "free") if quota_res.data else "free"
    quota = _get_insights_quota(user_id, plan_tier)

    current_docs_res = supabase.table("documents").select("id", count="exact")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .eq("status", "analyzed")\
        .execute()
    current_analyzed_count = current_docs_res.count if current_docs_res.count is not None else 0
    latest_doc_res = supabase.table("documents").select("updated_at")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("updated_at", desc=True)\
        .limit(1)\
        .execute()
    latest_document_updated_at = (
        latest_doc_res.data[0].get("updated_at") if latest_doc_res.data else None
    )

    stale_state = _build_insights_staleness(
        insights_updated_at=insights_updated_at,
        insights_doc_count=insights_doc_count,
        current_analyzed_count=current_analyzed_count,
        latest_document_updated_at=latest_document_updated_at,
    )

    recommendation_rows = supabase.table("paper_recommendations").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .order("relevance_score", desc=True)\
        .execute()
    recommendation_groups = _group_recommendations_by_context(recommendation_rows.data or [])

    response_payload = {
        "status": status,
        "insights": insights,
        "is_stale": stale_state["is_stale"],
        "stale_reason": stale_state["stale_reason"],
        "insights_updated_at": insights_updated_at,
        "latest_document_updated_at": latest_document_updated_at,
        "quota": quota,
        "summary_recommendations": recommendation_groups["summary_recommendations"],
        "gap_recommendations_by_title": recommendation_groups["gap_recommendations_by_title"],
        "conflict_recommendations_by_topic": recommendation_groups["conflict_recommendations_by_topic"],
    }

    if status == "analyzing":
        response_payload["message"] = "Literature Map analysis in progress"
        response_payload["progress"] = get_progress_snapshot("insights", project_id)
    elif status == "failed":
        response_payload["message"] = "Literature Map analysis failed. Please try again."
        error_detail = (project.get("insights_metadata") or {}).get("error_detail")
        if error_detail:
            response_payload["error_detail"] = error_detail
    elif status == "not_analyzed":
        response_payload["message"] = "Literature Map has not been generated yet"

    return response_payload


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
