"""
Celery task for document analysis with LangGraph extraction.

Phase 3.2: Production-ready document analysis task with retry logic and error handling.
"""

from celery import Task
from app.celery_app import celery_app
import traceback
import os

_DEV = os.environ.get("ENVIRONMENT", "development") != "production"


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

        # Update document status to failed (will be retried automatically)
        try:
            from app.core.supabase_client import supabase
            import datetime
            supabase.table("documents").update({
                "status": "failed",
                "updated_at": datetime.datetime.utcnow().isoformat(),
                "metadata": {
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "task_id": self.request.id,
                    "retries": self.request.retries,
                }
            }).eq("id", document_id).execute()
        except Exception as update_error:
            print(f"[CELERY-DOC] WARNING: Failed to update document status: {update_error}")

        # Re-raise to trigger retry
        raise
