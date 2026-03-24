"""
Celery task: BibTeX OA resolution pipeline.

Triggered after import_bibtex creates document records.
Runs in background — does not block the API response.
"""

from celery import Task
from app.celery_app import celery_app
import traceback


class BibTexResolutionTask(Task):
    """Custom task class with retry logic."""

    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 2, 'countdown': 30}
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True


@celery_app.task(
    bind=True,
    base=BibTexResolutionTask,
    name="app.tasks.bibtex_resolution.resolve_bibtex",
    queue="analysis",
)
def resolve_bibtex_task(
    self,
    document_ids: list,
    user_id: str,
    project_id: str,
):
    """
    Celery task: resolve open-access PDFs for a batch of BibTeX document IDs.

    Args:
        document_ids: List of document UUIDs created by import_bibtex
        user_id: Owner user ID
        project_id: Project ID

    Returns:
        dict with resolved/unresolved counts
    """
    print(f"[CELERY-BIB] ========== STARTING BIBTEX RESOLUTION TASK ==========")
    print(f"[CELERY-BIB] Task ID: {self.request.id}")
    print(f"[CELERY-BIB] Documents to resolve: {len(document_ids)}")
    print(f"[CELERY-BIB] Retry: {self.request.retries}/{self.max_retries}")

    try:
        from app.services.bibtex_resolution_service import resolve_bibtex_entries_sync
        result = resolve_bibtex_entries_sync(document_ids, user_id, project_id)

        print(f"[CELERY-BIB] ✓ Resolution complete: {result}")
        print(f"[CELERY-BIB] ========== BIBTEX RESOLUTION TASK COMPLETE ==========")
        return result

    except Exception as exc:
        print(f"[CELERY-BIB] ✗ Task failed: {exc}")
        print(traceback.format_exc())
        raise
