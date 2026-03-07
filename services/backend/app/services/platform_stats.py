"""
Platform Statistics Service

Provides real-time stats for landing page and marketing
"""

from typing import Dict, Any
from datetime import datetime, timedelta

from app.core.supabase_client import get_supabase_client


def get_platform_stats() -> Dict[str, Any]:
    """
    Get current platform statistics

    Returns:
        Dictionary with stats for display on landing page
    """
    supabase = get_supabase_client()

    try:
        # Get cached stats from platform_stats table
        stats_result = supabase.table("platform_stats").select("*").execute()

        if not stats_result.data:
            # Initialize stats
            initialize_platform_stats()
            stats_result = supabase.table("platform_stats").select("*").execute()

        # Convert to dictionary
        stats_dict = {row["stat_name"]: row["stat_value"] for row in stats_result.data}

        # Get additional computed stats
        # Count active users (logged in within last 30 days)
        thirty_days_ago = (datetime.utcnow() - timedelta(days=30)).isoformat()

        # Use analytics_events to count active users
        active_users_result = supabase.rpc(
            "count_active_users",
            {"days_back": 30}
        ).execute()

        active_users = active_users_result.data if active_users_result.data else stats_dict.get("total_researchers", 0)

        return {
            "total_researchers": stats_dict.get("total_researchers", 0),
            "active_researchers": active_users,
            "drafts_analyzed": stats_dict.get("drafts_analyzed", 0),
            "papers_processed": stats_dict.get("papers_processed", 0),
            "universities_count": stats_dict.get("universities_count", 0),
            "last_updated": stats_result.data[0].get("last_updated") if stats_result.data else datetime.utcnow().isoformat()
        }

    except Exception as e:
        # Fallback to basic counts
        return get_basic_stats()


def get_basic_stats() -> Dict[str, Any]:
    """
    Fallback method to get basic stats without platform_stats table
    """
    supabase = get_supabase_client()

    try:
        # Count users
        users = supabase.table("auth.users").select("id", count="exact").execute()
        total_users = users.count if users.count else 0

        # Count drafts
        drafts = supabase.table("drafts").select("id", count="exact").eq("status", "completed").execute()
        total_drafts = drafts.count if drafts.count else 0

        # Count papers
        papers = supabase.table("documents").select("id", count="exact").eq("status", "completed").execute()
        total_papers = papers.count if papers.count else 0

        return {
            "total_researchers": total_users,
            "active_researchers": total_users,  # Assume all are active
            "drafts_analyzed": total_drafts,
            "papers_processed": total_papers,
            "universities_count": 10,  # Placeholder
            "last_updated": datetime.utcnow().isoformat()
        }

    except:
        # Ultimate fallback
        return {
            "total_researchers": 0,
            "active_researchers": 0,
            "drafts_analyzed": 0,
            "papers_processed": 0,
            "universities_count": 0,
            "last_updated": datetime.utcnow().isoformat()
        }


def initialize_platform_stats():
    """
    Initialize platform_stats table with initial values
    """
    supabase = get_supabase_client()

    try:
        # Call the update function (which initializes if needed)
        supabase.rpc("update_platform_stats").execute()
    except Exception as e:
        # If function doesn't exist, manually insert
        try:
            stats = [
                {"stat_name": "total_researchers", "stat_value": 0},
                {"stat_name": "drafts_analyzed", "stat_value": 0},
                {"stat_name": "universities_count", "stat_value": 0},
                {"stat_name": "papers_processed", "stat_value": 0}
            ]
            supabase.table("platform_stats").insert(stats).execute()
        except:
            pass


def update_platform_stats_cache():
    """
    Manually trigger platform stats update

    Should be called periodically (e.g., every hour) via cron job
    """
    supabase = get_supabase_client()

    try:
        supabase.rpc("update_platform_stats").execute()
        return {"success": True, "message": "Platform stats updated"}
    except Exception as e:
        return {"success": False, "error": str(e)}
