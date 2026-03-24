"""
Celery application configuration for Noesis background task processing.

Phase 3.1: Replaces ThreadPoolExecutor with Celery + Redis for production-ready
task queue with persistence, retry logic, and horizontal scaling.
"""

from celery import Celery
from kombu import Queue
import os

# Redis configuration from environment
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "0")

# Construct broker URL
BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Create Celery app
celery_app = Celery(
    "noesis",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
    include=[
        "app.tasks.document_analysis",
        "app.tasks.draft_analysis",
        "app.tasks.insights_analysis",
        "app.tasks.bibtex_resolution_task",
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task routing
    task_default_queue="default",
    task_queues=(
        Queue("default", routing_key="task.#"),
        Queue("analysis", routing_key="analysis.#"),
        Queue("insights", routing_key="insights.#"),
    ),

    # Task execution settings
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,

    # Retry configuration
    task_acks_late=True,  # Task acknowledged after completion
    task_reject_on_worker_lost=True,  # Reject task if worker crashes
    task_default_retry_delay=60,  # 60 seconds between retries
    task_max_retries=3,  # Maximum 3 retry attempts

    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,  # Persist results to Redis

    # Worker settings
    worker_prefetch_multiplier=1,  # Only fetch 1 task at a time (long-running tasks)
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks (prevent memory leaks)

    # Rate limiting
    task_annotations={
        "app.tasks.document_analysis.analyze_document": {
            "rate_limit": "10/m",  # Max 10 document analyses per minute
            "queue": "analysis",
        },
        "app.tasks.draft_analysis.analyze_draft": {
            "rate_limit": "10/m",  # Max 10 draft analyses per minute
            "queue": "analysis",
        },
        "app.tasks.insights_analysis.generate_insights": {
            "rate_limit": "5/m",  # Max 5 insights generations per minute
            "queue": "insights",
        },
    },

    # Task time limits
    task_soft_time_limit=600,  # Soft limit: 10 minutes
    task_time_limit=900,  # Hard limit: 15 minutes

    # Logging
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format="[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s",
)

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.tasks"])

if __name__ == "__main__":
    celery_app.start()
