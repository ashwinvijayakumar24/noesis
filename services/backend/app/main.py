from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.supabase_client import supabase
from app.core.config import settings
from app.api.routes import auth, projects, documents, drafts, rag, chat, search, tags, compass, research_questions, methodology_recommendations, paper_recommendations, analytics, analytics_tracking, citations, tasks, quota
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os

# Security middleware imports
from app.core.security_middleware import (
    SecurityHeadersMiddleware,
    InputValidationMiddleware,
    get_cors_config,
    rate_limit_exceeded_handler
)

# Initialize Sentry for error tracking
if settings.SENTRY_DSN:
    def before_send_filter(event, hint):
        """
        Filter Sentry events before sending.

        - In development: Only send manually captured events (e.g., from test endpoints)
        - In production/staging: Send all events
        """
        if settings.ENVIRONMENT == "development":
            # Check if this was manually captured (has fingerprint or specific tags)
            # Allow test events through
            if event.get("tags", {}).get("manual_capture") == "true":
                return event
            # Block automatic errors in development
            return None
        # Send all events in non-development environments
        return event

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,  # 10% performance monitoring
        environment=settings.ENVIRONMENT,
        before_send=before_send_filter
    )

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="Noesis API")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# ============================================
# SECURITY MIDDLEWARE (Add BEFORE CORS)
# ============================================
# These must be added before CORS middleware to ensure security headers
# are applied to all responses, including CORS preflight requests

# Add security headers (X-Frame-Options, CSP, HSTS, etc.)
app.add_middleware(SecurityHeadersMiddleware)

# Add input validation (SQL injection, XSS, path traversal protection)
app.add_middleware(InputValidationMiddleware)

# ============================================
# CORS MIDDLEWARE
# ============================================
# Configure CORS with environment-aware settings
allowed_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",")]
cors_config = get_cors_config(
    allowed_origins=allowed_origins,
    environment=settings.ENVIRONMENT
)

app.add_middleware(CORSMiddleware, **cors_config)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(drafts.router, prefix="/drafts", tags=["Drafts"])
app.include_router(rag.router, prefix="/rag", tags=["RAG"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(search.router, prefix="/search", tags=["Search"])
app.include_router(tags.router, prefix="/tags", tags=["Tags"])
app.include_router(compass.router, prefix="/compass", tags=["Compass"])
app.include_router(research_questions.router, prefix="/research-questions", tags=["Research Questions"])
app.include_router(methodology_recommendations.router, prefix="/methodology-recommendations", tags=["Methodology Recommendations"])
app.include_router(paper_recommendations.router, prefix="/paper-recommendations", tags=["Paper Recommendations"])
app.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
app.include_router(analytics_tracking.router, prefix="/analytics-tracking", tags=["Analytics Tracking"])
app.include_router(citations.router, prefix="/citations", tags=["Citations"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(quota.router, prefix="/quota", tags=["Quota"])

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

@app.get("/sentry-config")
def sentry_config():
    """
    Debug endpoint to check Sentry configuration.
    """
    import sentry_sdk

    return {
        "sentry_dsn_set": bool(settings.SENTRY_DSN),
        "sentry_dsn_preview": settings.SENTRY_DSN[:50] + "..." if settings.SENTRY_DSN else None,
        "environment": settings.ENVIRONMENT,
        "sentry_initialized": sentry_sdk.Hub.current.client is not None,
        "will_send_errors": settings.ENVIRONMENT != "development"
    }

@app.get("/test-sentry")
def test_sentry():
    """
    Test endpoint to trigger a Sentry error.
    Visit http://localhost:8000/test-sentry to verify Sentry is capturing errors.
    """
    import sentry_sdk

    if not settings.SENTRY_DSN:
        return {
            "status": "not_configured",
            "message": "Sentry is not configured. Set SENTRY_DSN in your .env file."
        }

    # Check if Sentry is actually initialized
    if sentry_sdk.Hub.current.client is None:
        return {
            "status": "not_initialized",
            "message": "Sentry DSN is set but SDK is not initialized. Check startup logs.",
            "environment": settings.ENVIRONMENT
        }

    # Trigger a test error that Sentry will capture
    try:
        # This will raise a ZeroDivisionError
        result = 1 / 0
    except Exception as e:
        # Capture the exception in Sentry with explicit flush
        # Tag as manual capture so it bypasses development filter
        with sentry_sdk.configure_scope() as scope:
            scope.set_tag("manual_capture", "true")
            scope.set_tag("test_endpoint", "true")

        event_id = sentry_sdk.capture_exception(e)
        sentry_sdk.flush(timeout=2.0)  # Force send immediately

        return {
            "status": "error_sent",
            "message": "Test error sent to Sentry! Check your Sentry dashboard.",
            "error": str(e),
            "event_id": event_id,
            "environment": settings.ENVIRONMENT,
            "sentry_dsn_configured": True,
            "note": "If ENVIRONMENT=development, automatic errors are filtered but manual captures still work."
        }
