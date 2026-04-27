"""
Celery task for populating project paper recommendations in the background.
"""

from celery import Task

from app.celery_app import celery_app


class PaperRecommendationTask(Task):
    """Custom task class with retry logic."""

    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": 2, "countdown": 60}
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True


@celery_app.task(
    bind=True,
    base=PaperRecommendationTask,
    name="app.tasks.paper_recommendations.generate_project_recommendations",
    queue="analysis",
)
def generate_paper_recommendations_task(self, project_id: str, user_id: str):
    """
    Populate paper recommendations for a project without blocking the caller.
    """
    print(f"[CELERY-PAPER-REC] Starting task for project_id={project_id}")
    print(f"[CELERY-PAPER-REC] Retry {self.request.retries}/{self.max_retries}")

    from app.api.routes.paper_recommendations import _generate_and_store_recommendations

    result = _generate_and_store_recommendations(
        project_id=project_id,
        user_id=user_id,
        discovery_type="recommended",
        search_query=None,
    )

    print(f"[CELERY-PAPER-REC] Completed task for project_id={project_id}: {result}")
    return result
