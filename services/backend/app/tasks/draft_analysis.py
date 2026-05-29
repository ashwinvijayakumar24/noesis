"""
Celery task for draft analysis with LangGraph extraction.

Phase 3.2: Production-ready draft analysis task with retry logic and error handling.
"""

from celery import Task
from app.celery_app import celery_app
from app.core.privacy import safe_exception
import os

_DEV = os.environ.get("ENVIRONMENT", "development") != "production"


class DraftAnalysisTask(Task):
    """Custom task class with retry logic and error handling."""

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}  # Retry 3 times with 60s delay
    retry_backoff = True  # Exponential backoff
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True  # Add random jitter to prevent thundering herd


@celery_app.task(
    bind=True,
    base=DraftAnalysisTask,
    name="app.tasks.draft_analysis.analyze_draft",
    queue="analysis",
)
def analyze_draft_task(self, draft_id: str, project_id: str):
    """
    Celery task to analyze a draft using LangGraph workflow.

    This task:
    1. Downloads draft from storage
    2. Extracts text based on file type (PDF, DOCX, TXT)
    3. Runs LangGraph workflow (structure → claims → citations → gaps → feedback)
    4. Stores analysis results in database (draft_claims, coverage_gaps, reviewer_feedback, citation_suggestions)
    5. Updates draft status
    6. Tracks quota usage and OpenAI costs

    Args:
        draft_id: Draft ID to analyze
        project_id: Project ID

    Returns:
        dict: Analysis results with status and metadata

    Raises:
        Retry: If analysis fails (up to 3 retries)
    """
    print(f"[CELERY-DRAFT] ========== STARTING DRAFT ANALYSIS TASK ==========")
    print(f"[CELERY-DRAFT] Task ID: {self.request.id}")
    print(f"[CELERY-DRAFT] Draft ID: {draft_id}")
    print(f"[CELERY-DRAFT] Project ID: {project_id}")
    print(f"[CELERY-DRAFT] Retry: {self.request.retries}/{self.max_retries}")

    try:
        # Import the existing analysis function
        from app.api.routes.drafts import _run_draft_analysis_task

        # Run the analysis (this is the existing function that does all the work)
        _run_draft_analysis_task(draft_id, project_id)

        print(f"[CELERY-DRAFT] ✓ Draft analysis completed successfully")
        print(f"[CELERY-DRAFT] ========== DRAFT ANALYSIS TASK COMPLETE ==========")

        return {
            "status": "success",
            "draft_id": draft_id,
            "project_id": project_id,
            "task_id": self.request.id,
            "retries": self.request.retries,
        }

    except Exception as e:
        print(f"[CELERY-DRAFT] ========== DRAFT ANALYSIS TASK FAILED ==========")
        print(f"[CELERY-DRAFT] ERROR: {type(e).__name__}")
        print(f"[CELERY-DRAFT] Attempt {self.request.retries + 1}/{self.max_retries + 1}")
        if _DEV:
            print(f"[CELERY-DRAFT] Detail: {safe_exception(e)}")

        is_last_attempt = self.request.retries >= self.max_retries
        if is_last_attempt:
            # Only mark as failed after all retries are exhausted
            print(f"[CELERY-DRAFT] All retries exhausted — marking draft as 'failed'")
            try:
                from app.core.supabase_client import supabase
                import datetime
                supabase.table("drafts").update({
                    "status": "failed",
                    "updated_at": datetime.datetime.utcnow().isoformat(),
                    "metadata": {
                        "error": safe_exception(e),
                        "error_type": type(e).__name__,
                        "task_id": self.request.id,
                        "retries": self.request.retries,
                    }
                }).eq("id", draft_id).execute()
            except Exception as update_error:
                print(f"[CELERY-DRAFT] WARNING: Failed to update draft status: {update_error}")
        else:
            print(f"[CELERY-DRAFT] Transient failure — keeping status 'processing', will retry in 60s")

        # Re-raise to trigger retry
        raise
