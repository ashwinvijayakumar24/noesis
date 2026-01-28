"""
Quota Management Service

Prevents cost explosion by enforcing usage limits and tracking OpenAI costs.

Key Features:
- Check user quotas before expensive operations
- Track OpenAI token usage and costs
- Atomic quota increment operations
- Monthly quota reset support
"""

from typing import Optional, Dict, Any
from datetime import datetime
from app.core.supabase_client import supabase


class QuotaExceededError(Exception):
    """Raised when user exceeds their quota limits."""
    def __init__(self, message: str, quota_type: str, limit: int, current: int):
        self.quota_type = quota_type
        self.limit = limit
        self.current = current
        super().__init__(message)


async def check_quota(user_id: str, operation_type: str) -> bool:
    """
    Check if user has quota available for the operation.

    Args:
        user_id: User UUID
        operation_type: One of "document", "draft", "chat"

    Returns:
        True if quota available

    Raises:
        QuotaExceededError: If user has exceeded their quota
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    # Get user quota
    response = supabase.table('user_quotas').select('*').eq('user_id', user_id).execute()

    if not response.data or len(response.data) == 0:
        # Create default quota for user if it doesn't exist
        await create_default_quota(user_id)
        response = supabase.table('user_quotas').select('*').eq('user_id', user_id).execute()

    quota = response.data[0]

    # Check if quota needs reset
    quota_reset_date = datetime.fromisoformat(quota['quota_reset_date'].replace('Z', '+00:00'))
    if datetime.now(quota_reset_date.tzinfo) > quota_reset_date:
        await reset_quota(user_id)
        response = supabase.table('user_quotas').select('*').eq('user_id', user_id).execute()
        quota = response.data[0]

    # Check limits based on operation type
    if operation_type == "document":
        current = quota['current_month_documents']
        limit = quota['monthly_document_limit']

        if current >= limit:
            raise QuotaExceededError(
                f"Monthly document limit exceeded ({limit} documents/month)",
                quota_type="documents",
                limit=limit,
                current=current
            )

    elif operation_type == "draft":
        current = quota['current_month_drafts']
        limit = quota['monthly_draft_limit']

        if current >= limit:
            raise QuotaExceededError(
                f"Monthly draft limit exceeded ({limit} drafts/month)",
                quota_type="drafts",
                limit=limit,
                current=current
            )

    elif operation_type == "chat":
        current = quota['current_month_chat_messages']
        limit = quota['monthly_chat_messages_limit']

        if current >= limit:
            raise QuotaExceededError(
                f"Monthly chat message limit exceeded ({limit} messages/month)",
                quota_type="chat_messages",
                limit=limit,
                current=current
            )

    return True


async def increment_quota_usage(user_id: str, operation_type: str) -> None:
    """
    Increment quota counter after successful operation.

    Uses database function for atomic increment.

    Args:
        user_id: User UUID
        operation_type: One of "document", "draft", "chat"
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    field_map = {
        "document": "current_month_documents",
        "draft": "current_month_drafts",
        "chat": "current_month_chat_messages"
    }

    field_name = field_map.get(operation_type)
    if not field_name:
        return

    # Call database function for atomic increment
    supabase.rpc('increment_quota_field', {
        'user_id_param': user_id,
        'field_name': field_name
    }).execute()


async def track_openai_usage(
    user_id: str,
    operation_type: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    project_id: Optional[str] = None,
    document_id: Optional[str] = None,
    draft_id: Optional[str] = None
) -> None:
    """
    Track OpenAI usage for cost monitoring.

    Args:
        user_id: User UUID
        operation_type: Type of operation (document_analysis, chat, etc.)
        model: OpenAI model used (gpt-4o, text-embedding-3-small, etc.)
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        project_id: Optional project ID
        document_id: Optional document ID
        draft_id: Optional draft ID
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    # Cost estimation (as of January 2025)
    costs = {
        'gpt-4o': {'input': 0.0025, 'output': 0.01},  # per 1K tokens
        'gpt-4o-mini': {'input': 0.00015, 'output': 0.0006},
        'text-embedding-3-small': {'input': 0.00002, 'output': 0},
        'text-embedding-3-large': {'input': 0.00013, 'output': 0}
    }

    model_cost = costs.get(model, {'input': 0, 'output': 0})
    estimated_cost = (
        (prompt_tokens / 1000) * model_cost['input'] +
        (completion_tokens / 1000) * model_cost['output']
    )

    total_tokens = prompt_tokens + completion_tokens

    # Insert usage record
    supabase.table('openai_usage_tracking').insert({
        'user_id': user_id,
        'operation_type': operation_type,
        'model': model,
        'prompt_tokens': prompt_tokens,
        'completion_tokens': completion_tokens,
        'total_tokens': total_tokens,
        'estimated_cost_usd': estimated_cost,
        'project_id': project_id,
        'document_id': document_id,
        'draft_id': draft_id
    }).execute()


async def create_default_quota(user_id: str) -> None:
    """Create default free tier quota for user."""
    if not supabase:
        raise Exception("Supabase client not configured")

    supabase.table('user_quotas').insert({
        'user_id': user_id,
        'plan_tier': 'free'
    }).execute()


async def reset_quota(user_id: str) -> None:
    """Reset user quota counters (called when quota_reset_date is passed)."""
    if not supabase:
        raise Exception("Supabase client not configured")

    # Call database function
    supabase.rpc('reset_quota_if_needed', {
        'user_id_param': user_id
    }).execute()


async def get_user_quota_info(user_id: str) -> Dict[str, Any]:
    """
    Get user's current quota usage and limits.

    Returns:
        Dictionary with quota information
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    response = supabase.table('user_quotas').select('*').eq('user_id', user_id).execute()

    if not response.data or len(response.data) == 0:
        # Create default quota if doesn't exist
        await create_default_quota(user_id)
        response = supabase.table('user_quotas').select('*').eq('user_id', user_id).execute()

    quota = response.data[0]

    return {
        'plan_tier': quota['plan_tier'],
        'documents': {
            'current': quota['current_month_documents'],
            'limit': quota['monthly_document_limit'],
            'remaining': quota['monthly_document_limit'] - quota['current_month_documents']
        },
        'drafts': {
            'current': quota['current_month_drafts'],
            'limit': quota['monthly_draft_limit'],
            'remaining': quota['monthly_draft_limit'] - quota['current_month_drafts']
        },
        'chat_messages': {
            'current': quota['current_month_chat_messages'],
            'limit': quota['monthly_chat_messages_limit'],
            'remaining': quota['monthly_chat_messages_limit'] - quota['current_month_chat_messages']
        },
        'quota_reset_date': quota['quota_reset_date']
    }


async def get_user_cost_summary(
    user_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Get user's OpenAI cost summary for a date range.

    Args:
        user_id: User UUID
        start_date: Optional start date (defaults to current month start)
        end_date: Optional end date (defaults to now)

    Returns:
        Dictionary with cost breakdown by operation type
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    # Default to current month if dates not provided
    if not start_date:
        start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if not end_date:
        end_date = datetime.now()

    # Get usage records
    response = (supabase.table('openai_usage_tracking')
        .select('operation_type, model, total_tokens, estimated_cost_usd')
        .eq('user_id', user_id)
        .gte('created_at', start_date.isoformat())
        .lte('created_at', end_date.isoformat())
        .execute())

    if not response.data:
        return {
            'total_cost': 0,
            'total_tokens': 0,
            'by_operation': {},
            'by_model': {}
        }

    # Aggregate by operation type
    by_operation = {}
    by_model = {}
    total_cost = 0
    total_tokens = 0

    for record in response.data:
        op_type = record['operation_type']
        model = record['model']
        tokens = record['total_tokens']
        cost = float(record['estimated_cost_usd'])

        # By operation type
        if op_type not in by_operation:
            by_operation[op_type] = {'count': 0, 'tokens': 0, 'cost': 0}
        by_operation[op_type]['count'] += 1
        by_operation[op_type]['tokens'] += tokens
        by_operation[op_type]['cost'] += cost

        # By model
        if model not in by_model:
            by_model[model] = {'count': 0, 'tokens': 0, 'cost': 0}
        by_model[model]['count'] += 1
        by_model[model]['tokens'] += tokens
        by_model[model]['cost'] += cost

        total_cost += cost
        total_tokens += tokens

    return {
        'total_cost': round(total_cost, 6),
        'total_tokens': total_tokens,
        'by_operation': by_operation,
        'by_model': by_model,
        'date_range': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        }
    }
