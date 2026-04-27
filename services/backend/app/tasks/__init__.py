"""
Celery tasks for Noesis background processing.

Phase 3: Production-ready task queue with persistence, retry logic, and horizontal scaling.
"""

from .document_analysis import analyze_document_task
from .draft_analysis import analyze_draft_task
from .insights_analysis import generate_insights_task
from .bibtex_resolution_task import resolve_bibtex_task
from .paper_recommendation_tasks import generate_paper_recommendations_task

__all__ = [
    "analyze_document_task",
    "analyze_draft_task",
    "generate_insights_task",
    "resolve_bibtex_task",
    "generate_paper_recommendations_task",
]
