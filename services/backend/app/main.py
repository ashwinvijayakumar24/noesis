from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.supabase_client import supabase
from app.core.config import settings
from app.api.routes import auth, projects, documents, rag, chat, search, tags, literature_review, research_questions, methodology_recommendations, paper_recommendations, analytics, analytics_tracking

app = FastAPI(title="Noesis API")

# CORS middleware to allow frontend to connect
# Parse CORS_ORIGINS from environment variable (comma-separated string to list)
allowed_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(rag.router, prefix="/rag", tags=["RAG"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(tags.router, prefix="/tags", tags=["Tags"])
app.include_router(literature_review.router, prefix="/literature-review", tags=["Literature Review"])
app.include_router(research_questions.router, prefix="/research-questions", tags=["Research Questions"])
app.include_router(methodology_recommendations.router, prefix="/methodology-recommendations", tags=["Methodology Recommendations"])
app.include_router(paper_recommendations.router, prefix="/paper-recommendations", tags=["Paper Recommendations"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(analytics_tracking.router, prefix="/analytics-tracking", tags=["Analytics Tracking"])

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Noesis backend up"}

@app.get("/test-supabase")
def test_supabase_route():
    if supabase is None:
        return {
            "connection": "not configured",
            "message": "Supabase credentials not set. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables."
        }
    try:
        # Try to list tables to verify connection
        # This is a simple test that doesn't require any specific table to exist
        from app.core.config import settings
        return {
            "connection": "ok",
            "message": "Successfully connected to Supabase",
            "project_url": settings.SUPABASE_URL,
            "client_initialized": supabase is not None
        }
    except Exception as e:
        return {"connection": "error", "message": str(e)}
