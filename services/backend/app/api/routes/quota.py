"""
Quota and Cost Analytics API Endpoints

Provides endpoints for:
- User quota/usage limits
- OpenAI cost tracking per user
- Admin cost analytics for pricing optimization
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
from app.services.quota_management import (
    get_user_quota_info,
    get_user_cost_summary
)
from typing import Optional
from datetime import datetime, timedelta
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"
        )

    # Use secure token validator
    token = SecureAuthValidator.validate_bearer_token(authorization)

    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


@router.get("/me")
async def get_my_quota(user_id: str = Depends(get_current_user)):
    """
    Get current user's quota usage and limits.

    Returns:
        - plan_tier: Current subscription tier
        - documents: Usage and limits for document uploads
        - drafts: Usage and limits for draft uploads
        - chat_messages: Usage and limits for chat messages
        - quota_reset_date: When quota resets
    """
    try:
        quota_info = await get_user_quota_info(user_id)
        return quota_info
    except Exception as e:
        logger.error(f"Failed to get quota info: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve quota information")


@router.get("/me/cost-summary")
async def get_my_cost_summary(
    user_id: str = Depends(get_current_user),
    start_date: Optional[str] = Query(None, description="ISO format start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="ISO format end date (YYYY-MM-DD)")
):
    """
    Get current user's OpenAI cost summary.

    Query parameters:
        - start_date: Optional start date (defaults to current month start)
        - end_date: Optional end date (defaults to now)

    Returns:
        - total_cost: Total estimated cost in USD
        - total_tokens: Total tokens used
        - by_operation: Breakdown by operation type (document_analysis, chat, etc.)
        - by_model: Breakdown by model (gpt-4o, gpt-4o-mini, etc.)
        - date_range: Date range for the summary
    """
    try:
        # Parse dates if provided
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        cost_summary = await get_user_cost_summary(user_id, start, end)
        return cost_summary
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to get cost summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve cost summary")


@router.get("/admin/all-users-cost-summary")
async def get_all_users_cost_summary(
    user_id: str = Depends(get_current_user),
    days: int = Query(30, description="Number of days to look back (default: 30)")
):
    """
    Get cost summary for ALL users (admin only).

    IMPORTANT: Add admin role check before production use!

    Returns aggregated cost data for pricing optimization:
        - total_users: Number of users with usage
        - total_cost: Total cost across all users
        - average_cost_per_user: Mean cost per user
        - median_cost_per_user: Median cost per user
        - users: List of users with their costs (sorted by cost descending)
    """
    # TODO: Add admin role check
    # For now, this is a placeholder - you should restrict this to admin users only

    try:
        start_date = datetime.now() - timedelta(days=days)
        end_date = datetime.now()

        # Get all usage records for the date range
        response = (supabase.table('openai_usage_tracking')
            .select('user_id, operation_type, model, total_tokens, estimated_cost_usd')
            .gte('created_at', start_date.isoformat())
            .lte('created_at', end_date.isoformat())
            .execute())

        if not response.data:
            return {
                'total_users': 0,
                'total_cost': 0,
                'average_cost_per_user': 0,
                'median_cost_per_user': 0,
                'users': [],
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat(),
                    'days': days
                }
            }

        # Aggregate by user
        user_costs = {}
        for record in response.data:
            uid = record['user_id']
            cost = float(record['estimated_cost_usd'])
            tokens = record['total_tokens']

            if uid not in user_costs:
                user_costs[uid] = {
                    'user_id': uid,
                    'total_cost': 0,
                    'total_tokens': 0,
                    'operation_count': 0
                }

            user_costs[uid]['total_cost'] += cost
            user_costs[uid]['total_tokens'] += tokens
            user_costs[uid]['operation_count'] += 1

        # Sort by cost descending
        users_list = sorted(user_costs.values(), key=lambda x: x['total_cost'], reverse=True)

        # Calculate statistics
        costs = [u['total_cost'] for u in users_list]
        total_cost = sum(costs)
        total_users = len(users_list)
        average_cost = total_cost / total_users if total_users > 0 else 0

        # Median calculation
        sorted_costs = sorted(costs)
        median_cost = 0
        if total_users > 0:
            mid = total_users // 2
            if total_users % 2 == 0:
                median_cost = (sorted_costs[mid - 1] + sorted_costs[mid]) / 2
            else:
                median_cost = sorted_costs[mid]

        return {
            'total_users': total_users,
            'total_cost': round(total_cost, 6),
            'average_cost_per_user': round(average_cost, 6),
            'median_cost_per_user': round(median_cost, 6),
            'percentile_90': round(sorted_costs[int(total_users * 0.9)], 6) if total_users > 0 else 0,
            'percentile_95': round(sorted_costs[int(total_users * 0.95)], 6) if total_users > 0 else 0,
            'top_10_users': users_list[:10],  # Most expensive users
            'users': users_list,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days
            }
        }

    except Exception as e:
        logger.error(f"Failed to get admin cost summary: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve admin cost summary")


@router.get("/admin/cost-by-operation")
async def get_cost_by_operation(
    user_id: str = Depends(get_current_user),
    days: int = Query(30, description="Number of days to look back")
):
    """
    Get cost breakdown by operation type (admin only).

    Useful for understanding which features are most expensive.

    Returns:
        - by_operation: Cost breakdown by operation type
        - recommendations: Cost optimization suggestions
    """
    # TODO: Add admin role check

    try:
        start_date = datetime.now() - timedelta(days=days)
        end_date = datetime.now()

        # Get all usage records
        response = (supabase.table('openai_usage_tracking')
            .select('operation_type, model, total_tokens, estimated_cost_usd')
            .gte('created_at', start_date.isoformat())
            .lte('created_at', end_date.isoformat())
            .execute())

        if not response.data:
            return {'by_operation': {}, 'total_cost': 0}

        # Aggregate by operation type
        by_operation = {}
        total_cost = 0

        for record in response.data:
            op_type = record['operation_type']
            cost = float(record['estimated_cost_usd'])
            tokens = record['total_tokens']

            if op_type not in by_operation:
                by_operation[op_type] = {
                    'count': 0,
                    'total_tokens': 0,
                    'total_cost': 0
                }

            by_operation[op_type]['count'] += 1
            by_operation[op_type]['total_tokens'] += tokens
            by_operation[op_type]['total_cost'] += cost
            total_cost += cost

        # Add percentage breakdown
        for op_type in by_operation:
            by_operation[op_type]['percentage'] = round(
                (by_operation[op_type]['total_cost'] / total_cost * 100) if total_cost > 0 else 0,
                2
            )

        return {
            'by_operation': by_operation,
            'total_cost': round(total_cost, 6),
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat(),
                'days': days
            }
        }

    except Exception as e:
        logger.error(f"Failed to get cost by operation: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve operation cost breakdown")
