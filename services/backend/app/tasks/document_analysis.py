"""
Celery task for document analysis with LangGraph extraction.

Phase 3.2: Production-ready document analysis task with retry logic and error handling.
"""

from celery import Task
from app.celery_app import celery_app
import traceback
import os
from openai import APIConnectionError, APIError, RateLimitError

from app.core.api_errors import build_error_detail
from app.services.progress_tracking import store_progress_snapshot

_DEV = os.environ.get("ENVIRONMENT", "development") != "production"


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


def _merge_metadata(existing: dict | None, **updates) -> dict:
    merged = dict(existing or {})
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    return merged


class DocumentAnalysisTask(Task):
    """Custom task class with retry logic and error handling."""

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}  # Retry 3 times with 60s delay
    retry_backoff = True  # Exponential backoff
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True  # Add random jitter to prevent thundering herd


@celery_app.task(
    bind=True,
    base=DocumentAnalysisTask,
    name="app.tasks.document_analysis.analyze_document",
    queue="analysis",
)
def analyze_document_task(self, document_id: str, user_id: str, project_id: str = ""):
    """
    Celery task to analyze a document using LangGraph workflow.

    This task:
    1. Fetches document from Supabase
    2. Downloads PDF from storage
    3. Processes with GROBID for structure extraction
    4. Runs LangGraph workflow to extract claims, methods, findings
    5. Generates comprehensive analysis with GPT-4o
    6. Stores structured data in database (document_claims, document_methods, document_findings)
    7. Auto-regenerates insights if project previously analyzed
    8. Auto-re-analyzes drafts if first document uploaded

    Args:
        document_id: Document ID to analyze
        user_id: User ID (for quota tracking, not used but kept for API compatibility)
        project_id: Project ID (not used but kept for API compatibility)

    Returns:
        dict: Analysis results with status and metadata

    Raises:
        Retry: If analysis fails (up to 3 retries)
    """
    print(f"[CELERY-DOC] ========== STARTING DOCUMENT ANALYSIS TASK ==========")
    print(f"[CELERY-DOC] Task ID: {self.request.id}")
    print(f"[CELERY-DOC] Document ID: {document_id}")
    print(f"[CELERY-DOC] Retry: {self.request.retries}/{self.max_retries}")

    try:
        # Fetch document to get file_url (needed by _run_analysis_task)
        from app.core.supabase_client import supabase
        doc_response = supabase.table("documents").select("file_url").eq("id", document_id).execute()

        if not doc_response.data:
            raise ValueError(f"Document {document_id} not found")

        file_url = doc_response.data[0].get("file_url")
        if not file_url:
            raise ValueError(f"Document {document_id} has no file_url")

        print(f"[CELERY-DOC] File URL retrieved")

        # Import the existing analysis function
        from app.api.routes.documents import _run_analysis_task

        # Run the analysis with correct signature (document_id, file_url)
        _run_analysis_task(document_id, file_url)

        print(f"[CELERY-DOC] ✓ Document analysis completed successfully")
        print(f"[CELERY-DOC] ========== DOCUMENT ANALYSIS TASK COMPLETE ==========")

        return {
            "status": "success",
            "document_id": document_id,
            "task_id": self.request.id,
            "retries": self.request.retries,
        }

    except Exception as e:
        print(f"[CELERY-DOC] ========== DOCUMENT ANALYSIS TASK FAILED ==========")
        print(f"[CELERY-DOC] ERROR: {type(e).__name__}")
        print(f"[CELERY-DOC] Retry {self.request.retries + 1}/{self.max_retries}")
        if _DEV:
            print(f"[CELERY-DOC] Detail: {str(e)}")
            print(f"[CELERY-DOC] Traceback:\n{traceback.format_exc()}")

        is_retryable = self.request.retries < self.max_retries
        transient_provider_error = _is_transient_provider_error(e)
        error_detail = build_error_detail(
            code="transient_provider_error" if transient_provider_error else "document_analysis_failed",
            title="Service under load" if transient_provider_error else "Analysis failed",
            message=(
                "The analysis service is under load. We're retrying automatically."
                if is_retryable
                else "We couldn't analyze this PDF."
            ),
            details=[str(e)] if str(e) else None,
            next_action="retry",
            retryable=True,
        )

        stage = "retrying_provider" if transient_provider_error else "retrying"
        label = "Retrying after provider rate limit" if transient_provider_error else "Retrying analysis"
        store_progress_snapshot(
            "document",
            document_id,
            stage,
            65,
            label,
            retrying=is_retryable,
            attempt=self.request.retries + 1,
            max_attempts=self.max_retries,
        )

        # Update document status. Keep it active while retries remain.
        try:
            from app.core.supabase_client import supabase
            import datetime
            metadata_response = supabase.table("documents").select("metadata").eq("id", document_id).execute()
            existing_metadata = (
                metadata_response.data[0].get("metadata") or {}
                if metadata_response.data
                else {}
            )
            supabase.table("documents").update({
                "status": "failed" if not is_retryable else "analyzing",
                "updated_at": datetime.datetime.utcnow().isoformat(),
                "metadata": _merge_metadata(
                    existing_metadata,
                    error=str(e),
                    error_type=type(e).__name__,
                    error_detail=error_detail,
                    task_id=self.request.id,
                    retries=self.request.retries,
                ),
            }).eq("id", document_id).execute()
        except Exception as update_error:
            print(f"[CELERY-DOC] WARNING: Failed to update document status: {update_error}")

        # Re-raise to trigger retry
        raise
