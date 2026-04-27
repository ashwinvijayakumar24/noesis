"""
Celery task for project insights generation.

Phase 3.2: Production-ready insights analysis task with retry logic and error handling.
"""

from celery import Task
from app.celery_app import celery_app
import traceback

from app.core.api_errors import build_error_detail
from app.services.progress_tracking import store_progress_snapshot


def _merge_metadata(existing: dict | None, **updates) -> dict:
    merged = dict(existing or {})
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    return merged


class InsightsAnalysisTask(Task):
    """Custom task class with retry logic and error handling."""

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3, 'countdown': 60}  # Retry 3 times with 60s delay
    retry_backoff = True  # Exponential backoff
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True  # Add random jitter to prevent thundering herd


@celery_app.task(
    bind=True,
    base=InsightsAnalysisTask,
    name="app.tasks.insights_analysis.generate_insights",
    queue="insights",
)
def generate_insights_task(self, project_id: str, user_id: str):
    """
    Celery task to generate project insights from analyzed documents.

    This task:
    1. Fetches all analyzed documents from project
    2. Runs cross-paper analysis using GPT-4o
    3. Uses LangGraph structured data (claims, methods, findings) for enriched results
    4. Identifies research gaps, emerging themes, and methodological patterns
    5. Stores insights in project record
    6. Tracks quota usage and OpenAI costs

    Args:
        project_id: Project ID
        user_id: User ID (for quota tracking)

    Returns:
        dict: Analysis results with status and metadata

    Raises:
        Retry: If analysis fails (up to 3 retries)
    """
    print(f"[CELERY-INSIGHTS] ========== STARTING INSIGHTS ANALYSIS TASK ==========")
    print(f"[CELERY-INSIGHTS] Task ID: {self.request.id}")
    print(f"[CELERY-INSIGHTS] Project ID: {project_id}")
    print(f"[CELERY-INSIGHTS] User ID: {user_id}")
    print(f"[CELERY-INSIGHTS] Retry: {self.request.retries}/{self.max_retries}")

    try:
        # Import the existing analysis function
        from app.api.routes.projects import _run_insights_analysis_task

        # Run the analysis (this is the existing function that does all the work)
        _run_insights_analysis_task(project_id, user_id)

        print(f"[CELERY-INSIGHTS] ✓ Insights analysis completed successfully")
        print(f"[CELERY-INSIGHTS] ========== INSIGHTS ANALYSIS TASK COMPLETE ==========")

        return {
            "status": "success",
            "project_id": project_id,
            "task_id": self.request.id,
            "retries": self.request.retries,
        }

    except Exception as e:
        print(f"[CELERY-INSIGHTS] ========== INSIGHTS ANALYSIS TASK FAILED ==========")
        print(f"[CELERY-INSIGHTS] ERROR: {type(e).__name__}: {str(e)}")
        print(f"[CELERY-INSIGHTS] Traceback:\n{traceback.format_exc()}")
        print(f"[CELERY-INSIGHTS] Retry {self.request.retries + 1}/{self.max_retries}")

        is_retryable = self.request.retries < self.max_retries
        error_detail = build_error_detail(
            code="transient_provider_error",
            title="Service under load",
            message=(
                "The Literature Map service is under load. We're retrying automatically."
                if is_retryable
                else "We couldn't generate the Literature Map."
            ),
            details=[str(e)] if str(e) else None,
            next_action="retry",
            retryable=True,
        )
        store_progress_snapshot(
            "insights",
            project_id,
            "retrying_provider",
            70,
            "Retrying Literature Map analysis",
            retrying=is_retryable,
            attempt=self.request.retries + 1,
            max_attempts=self.max_retries,
        )

        # Update project status. Keep it active while retries remain.
        try:
            from app.core.supabase_client import supabase
            import datetime
            metadata_response = supabase.table("projects").select("insights_metadata").eq("id", project_id).execute()
            existing_metadata = (
                metadata_response.data[0].get("insights_metadata") or {}
                if metadata_response.data
                else {}
            )
            supabase.table("projects").update({
                "insights_status": "failed" if not is_retryable else "analyzing",
                "updated_at": datetime.datetime.utcnow().isoformat(),
                "insights_metadata": _merge_metadata(
                    existing_metadata,
                    error=str(e),
                    error_type=type(e).__name__,
                    error_detail=error_detail,
                    task_id=self.request.id,
                    retries=self.request.retries,
                ),
            }).eq("id", project_id).execute()
        except Exception as update_error:
            print(f"[CELERY-INSIGHTS] WARNING: Failed to update project status: {update_error}")

        # Re-raise to trigger retry
        raise
