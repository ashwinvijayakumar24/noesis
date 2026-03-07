"""
Analytics Service

Provides business metrics and analytics for the platform
"""

from typing import Dict, Any, List
from datetime import datetime, timedelta

from app.core.supabase_client import get_supabase_client


def get_platform_analytics() -> Dict[str, Any]:
    """
    Get comprehensive platform analytics

    Returns:
        Dictionary with key metrics: MAU, DAU, activation, retention, etc.
    """
    supabase = get_supabase_client()

    try:
        # Use analytics_dashboard view
        dashboard = supabase.table("analytics_dashboard").select("*").execute()

        if dashboard.data and len(dashboard.data) > 0:
            data = dashboard.data[0]
            return {
                "mau": data.get("mau", 0),
                "dau": data.get("dau", 0),
                "dau_mau_ratio": round(data.get("dau", 0) / max(data.get("mau", 1), 1) * 100, 2),
                "new_signups_30d": data.get("new_signups_30d", 0),
                "drafts_analyzed_30d": data.get("drafts_analyzed_30d", 0),
                "papers_uploaded_30d": data.get("papers_uploaded_30d", 0),
                "paying_users": data.get("paying_users", 0),
                "last_updated": data.get("last_updated", datetime.utcnow().isoformat())
            }

    except Exception as e:
        pass

    # Fallback to manual calculation
    return get_manual_analytics()


def get_manual_analytics() -> Dict[str, Any]:
    """
    Manually calculate analytics metrics
    """
    supabase = get_supabase_client()

    # MAU: Users active in last 30 days
    thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()
    mau_result = supabase.table("analytics_events").select("user_id").gte("created_at", thirty_days_ago).execute()
    mau = len(set(event["user_id"] for event in mau_result.data)) if mau_result.data else 0

    # DAU: Users active in last 24 hours
    one_day_ago = (datetime.utcnow() - timedelta(days=1)).isoformat()
    dau_result = supabase.table("analytics_events").select("user_id").gte("created_at", one_day_ago).execute()
    dau = len(set(event["user_id"] for event in dau_result.data)) if dau_result.data else 0

    # New signups
    signups = supabase.table("auth.users").select("id", count="exact").gte("created_at", thirty_days_ago).execute()
    new_signups = signups.count if signups.count else 0

    # Drafts analyzed
    drafts = supabase.table("drafts").select("id", count="exact").gte("created_at", thirty_days_ago).execute()
    drafts_count = drafts.count if drafts.count else 0

    # Papers uploaded
    papers = supabase.table("documents").select("id", count="exact").gte("created_at", thirty_days_ago).execute()
    papers_count = papers.count if papers.count else 0

    # Paying users
    paying = supabase.table("subscriptions").select("id", count="exact").neq("plan_tier", "free").execute()
    paying_count = paying.count if paying.count else 0

    return {
        "mau": mau,
        "dau": dau,
        "dau_mau_ratio": round(dau / max(mau, 1) * 100, 2),
        "new_signups_30d": new_signups,
        "drafts_analyzed_30d": drafts_count,
        "papers_uploaded_30d": papers_count,
        "paying_users": paying_count,
        "last_updated": datetime.utcnow().isoformat()
    }


def get_activation_metrics() -> Dict[str, Any]:
    """
    Calculate activation rate

    Activated user = uploaded ≥1 paper AND analyzed ≥1 draft
    """
    supabase = get_supabase_client()

    try:
        result = supabase.rpc("get_activation_rate").execute()

        if result.data and len(result.data) > 0:
            data = result.data[0]
            return {
                "total_signups": data.get("total_signups", 0),
                "activated_users": data.get("activated_users", 0),
                "activation_rate": data.get("activation_rate", 0.0)
            }

    except Exception as e:
        pass

    # Fallback
    return {
        "total_signups": 0,
        "activated_users": 0,
        "activation_rate": 0.0
    }


def get_power_users(min_drafts: int = 3) -> List[Dict[str, Any]]:
    """
    Get list of power users

    Args:
        min_drafts: Minimum number of drafts to be considered a power user

    Returns:
        List of power users with stats
    """
    supabase = get_supabase_client()

    try:
        result = supabase.rpc("get_power_users", {"min_drafts": min_drafts}).execute()

        if result.data:
            return result.data

    except Exception as e:
        pass

    return []


def get_retention_metrics(days: int = 7) -> List[Dict[str, Any]]:
    """
    Get retention cohort analysis

    Args:
        days: Number of days for retention calculation (default: 7-day retention)

    Returns:
        List of cohort retention data
    """
    supabase = get_supabase_client()

    try:
        result = supabase.rpc("get_retention_rate", {"days": days}).execute()

        if result.data:
            return result.data

    except Exception as e:
        pass

    return []


def get_feature_usage() -> List[Dict[str, Any]]:
    """
    Get feature usage statistics

    Returns:
        List of features with usage counts
    """
    supabase = get_supabase_client()

    try:
        result = supabase.rpc("get_feature_usage_stats").execute()

        if result.data:
            return result.data

    except Exception as e:
        pass

    return []


def track_event(
    user_id: str,
    event_type: str,
    event_data: Dict[str, Any] = None
):
    """
    Track an analytics event

    Args:
        user_id: User ID
        event_type: Type of event (e.g., 'draft_analyzed', 'paper_uploaded')
        event_data: Additional event metadata
    """
    supabase = get_supabase_client()

    try:
        event = {
            "user_id": user_id,
            "event_type": event_type,
            "event_data": event_data or {}
        }

        supabase.table("analytics_events").insert(event).execute()

    except Exception as e:
        # Don't fail if analytics tracking fails
        pass
