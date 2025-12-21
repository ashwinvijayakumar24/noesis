"""
Analytics Tracking API Endpoints

Provides endpoints for tracking user analytics events.
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, Field
from app.core.supabase_client import supabase
from typing import Optional, Dict, Any, List
from datetime import datetime

router = APIRouter()


# Pydantic models
class AnalyticsEvent(BaseModel):
    event_name: str = Field(..., description="Name of the event (e.g., sign_up, project_created)")
    event_properties: Optional[Dict[str, Any]] = Field(default=None, description="Additional event properties")
    session_id: Optional[str] = Field(default=None, description="Session identifier")


class BatchAnalyticsEvents(BaseModel):
    events: List[AnalyticsEvent] = Field(..., description="List of analytics events to track")


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split("Bearer ")[-1]
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")


@router.post("/track")
async def track_event(
    event: AnalyticsEvent,
    request: Request,
    user_id: str = Depends(get_current_user)
):
    """
    Track a single analytics event.

    This endpoint stores user analytics events in the database for:
    - Feature usage tracking
    - User engagement metrics
    - Product analytics
    - Conversion funnels
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Extract user agent and IP address from request
        user_agent = request.headers.get("user-agent")
        # Note: In production, consider using X-Forwarded-For or similar
        ip_address = request.client.host if request.client else None

        # Insert event into database
        result = supabase.table("analytics_events").insert({
            "user_id": user_id,
            "event_name": event.event_name,
            "event_properties": event.event_properties or {},
            "user_agent": user_agent,
            "ip_address": ip_address,
            "session_id": event.session_id,
            "created_at": datetime.utcnow().isoformat()
        }).execute()

        return {
            "success": True,
            "event_id": result.data[0]["id"] if result.data else None
        }

    except Exception as e:
        print(f"[ANALYTICS] Failed to track event: {e}")
        # Don't fail the request if analytics tracking fails
        # This ensures analytics doesn't break user experience
        return {
            "success": False,
            "error": "Analytics tracking failed but request succeeded"
        }


@router.post("/track/batch")
async def track_batch_events(
    batch: BatchAnalyticsEvents,
    request: Request,
    user_id: str = Depends(get_current_user)
):
    """
    Track multiple analytics events in a single request.

    Useful for:
    - Reducing network requests
    - Offline event buffering
    - Bulk event uploads
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    if not batch.events:
        return {"success": True, "events_tracked": 0}

    try:
        # Extract user agent and IP address from request
        user_agent = request.headers.get("user-agent")
        ip_address = request.client.host if request.client else None

        # Prepare batch insert
        events_to_insert = []
        for event in batch.events:
            events_to_insert.append({
                "user_id": user_id,
                "event_name": event.event_name,
                "event_properties": event.event_properties or {},
                "user_agent": user_agent,
                "ip_address": ip_address,
                "session_id": event.session_id,
                "created_at": datetime.utcnow().isoformat()
            })

        # Insert all events
        result = supabase.table("analytics_events").insert(events_to_insert).execute()

        return {
            "success": True,
            "events_tracked": len(result.data) if result.data else 0
        }

    except Exception as e:
        print(f"[ANALYTICS] Failed to track batch events: {e}")
        return {
            "success": False,
            "error": "Batch analytics tracking failed but request succeeded"
        }


@router.get("/events")
async def get_user_events(
    limit: int = 100,
    offset: int = 0,
    user_id: str = Depends(get_current_user)
):
    """
    Get analytics events for the current user.

    Useful for:
    - Viewing user activity history
    - Debugging analytics tracking
    - Building user dashboards
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        result = supabase.table("analytics_events")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .offset(offset)\
            .execute()

        return {
            "events": result.data or [],
            "count": len(result.data) if result.data else 0
        }

    except Exception as e:
        print(f"[ANALYTICS] Failed to get events: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics events")


@router.get("/summary")
async def get_analytics_summary(
    user_id: str = Depends(get_current_user)
):
    """
    Get analytics summary for the current user.

    Returns aggregated metrics like:
    - Total events
    - Events by type
    - Recent activity
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Get all user events
        result = supabase.table("analytics_events")\
            .select("event_name, created_at")\
            .eq("user_id", user_id)\
            .execute()

        events = result.data or []

        # Calculate summary statistics
        event_counts = {}
        for event in events:
            event_name = event["event_name"]
            event_counts[event_name] = event_counts.get(event_name, 0) + 1

        # Get first and last event timestamps
        timestamps = [event["created_at"] for event in events]
        first_event = min(timestamps) if timestamps else None
        last_event = max(timestamps) if timestamps else None

        return {
            "total_events": len(events),
            "unique_events": len(event_counts),
            "event_counts": event_counts,
            "first_event": first_event,
            "last_event": last_event
        }

    except Exception as e:
        print(f"[ANALYTICS] Failed to get summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve analytics summary")
