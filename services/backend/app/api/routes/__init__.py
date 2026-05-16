# API Routes
# This file allows importing routes as: from app.api.routes import module_name

# Existing routes
from . import (
    auth,
    projects,
    documents,
    drafts,
    rag,
    search,
    tags,
    compass,
    research_questions,
    methodology_recommendations,
    paper_recommendations,
    analytics,
    analytics_tracking,
    citations,
    tasks,
    quota
)

# New routes (Week 2-4 implementation)
from . import (
    paper_discovery,
    feedback,
    referrals,
    platform,
    subscriptions,
)

__all__ = [
    "auth",
    "projects",
    "documents",
    "drafts",
    "rag",
    "search",
    "tags",
    "compass",
    "research_questions",
    "methodology_recommendations",
    "paper_recommendations",
    "analytics",
    "analytics_tracking",
    "citations",
    "tasks",
    "quota",
    "paper_discovery",
    "feedback",
    "referrals",
    "platform",
    "subscriptions",
]
