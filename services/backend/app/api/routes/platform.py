"""
API routes for platform-wide data (stats, analytics)
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional

from app.core.security_middleware import SecureAuthValidator
from app.core.supabase_client import get_supabase_client
from app.services.platform_stats import get_platform_stats, update_platform_stats_cache
from app.services.analytics_service import (
    get_platform_analytics,
    get_activation_metrics,
    get_power_users,
    get_retention_metrics,
    get_feature_usage
)


router = APIRouter()


def _require_user(authorization: str = Header(None)) -> str:
    """Validate the Bearer token and return the user id (401 on failure)."""
    token = SecureAuthValidator.validate_bearer_token(authorization)
    supabase = get_supabase_client()
    user_response = supabase.auth.get_user(token)
    if not user_response or not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_response.user.id


@router.get("/platform/stats")
async def platform_stats():
    """
    Get public platform statistics

    Used for landing page social proof
    """
    try:
        stats = get_platform_stats()

        return {
            "total_researchers": stats.get("total_researchers", 0),
            "active_researchers": stats.get("active_researchers", 0),
            "drafts_analyzed": stats.get("drafts_analyzed", 0),
            "papers_processed": stats.get("papers_processed", 0),
            "universities": stats.get("universities_count", 0),
            "last_updated": stats.get("last_updated")
        }

    except Exception as e:
        # Return fallback stats
        return {
            "total_researchers": 0,
            "active_researchers": 0,
            "drafts_analyzed": 0,
            "papers_processed": 0,
            "universities": 0,
            "last_updated": None
        }


@router.post("/platform/stats/refresh")
async def refresh_platform_stats():
    """
    Manually trigger platform stats update

    Admin endpoint - should be called periodically via cron
    """
    try:
        result = update_platform_stats_cache()
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh stats: {str(e)}")


@router.get("/analytics/dashboard")
async def analytics_dashboard(user_id: str = Depends(_require_user)):
    """
    Get comprehensive analytics dashboard

    Admin endpoint - requires authentication
    """
    try:
        # Core metrics
        analytics = get_platform_analytics()

        # Activation metrics
        activation = get_activation_metrics()

        # Power users
        power_users = get_power_users(min_drafts=3)

        # Retention metrics
        retention_7d = get_retention_metrics(days=7)
        retention_30d = get_retention_metrics(days=30)

        # Feature usage
        feature_usage = get_feature_usage()

        return {
            "overview": {
                "mau": analytics.get("mau", 0),
                "dau": analytics.get("dau", 0),
                "dau_mau_ratio": analytics.get("dau_mau_ratio", 0),
                "new_signups_30d": analytics.get("new_signups_30d", 0),
                "paying_users": analytics.get("paying_users", 0)
            },
            "engagement": {
                "drafts_analyzed_30d": analytics.get("drafts_analyzed_30d", 0),
                "papers_uploaded_30d": analytics.get("papers_uploaded_30d", 0)
            },
            "activation": {
                "total_signups": activation.get("total_signups", 0),
                "activated_users": activation.get("activated_users", 0),
                "activation_rate": activation.get("activation_rate", 0)
            },
            "retention": {
                "7_day": retention_7d[:5] if retention_7d else [],
                "30_day": retention_30d[:5] if retention_30d else []
            },
            "power_users": {
                "count": len(power_users),
                "top_users": power_users[:10]
            },
            "feature_usage": feature_usage,
            "last_updated": analytics.get("last_updated")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch analytics: {str(e)}")


@router.get("/analytics/metrics")
async def get_metrics(
    metric: Optional[str] = None
):
    """
    Get specific analytics metric

    Available metrics:
    - mau: Monthly Active Users
    - dau: Daily Active Users
    - activation: Activation rate
    - retention: Retention cohorts
    - power_users: Power user list
    - feature_usage: Feature usage stats
    """
    try:
        if metric == "mau" or metric == "dau":
            analytics = get_platform_analytics()
            return {
                "mau": analytics.get("mau", 0),
                "dau": analytics.get("dau", 0),
                "dau_mau_ratio": analytics.get("dau_mau_ratio", 0)
            }

        elif metric == "activation":
            return get_activation_metrics()

        elif metric == "retention":
            return {
                "7_day": get_retention_metrics(days=7),
                "30_day": get_retention_metrics(days=30)
            }

        elif metric == "power_users":
            return {
                "power_users": get_power_users(min_drafts=3)
            }

        elif metric == "feature_usage":
            return {
                "features": get_feature_usage()
            }

        else:
            # Return all metrics
            return {
                "platform": get_platform_analytics(),
                "activation": get_activation_metrics(),
                "retention_7d": get_retention_metrics(days=7),
                "power_users_count": len(get_power_users(min_drafts=3)),
                "features": get_feature_usage()
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics: {str(e)}")
