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
from datetime import datetime, timezone
import os
from app.core.supabase_client import supabase

PLAN_PDF_LIMITS = {'free': 30, 'pro': 100, 'team': 9999, 'enterprise': 9999, 'admin': 9999}
PLAN_DRAFT_LIMITS = {'free': 2, 'pro': 20, 'team': 9999, 'enterprise': 9999, 'admin': 9999}
PLAN_BIB_LIMITS = {'free': 30, 'pro': 100, 'team': 9999, 'enterprise': 9999, 'admin': 9999}
PROJECT_LIMITS = {'free': 3, 'pro': 10, 'team': 999, 'enterprise': 999, 'admin': 999}
DEFAULT_CHAT_LIMIT = 500


def _get_redis_client():
    """Get Redis client for daily rate limiting."""
    import redis as redis_lib
    return redis_lib.Redis(
        host=os.getenv('REDIS_HOST', 'redis'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=int(os.getenv('REDIS_DB', 0)),
        decode_responses=True
    )


class QuotaExceededError(Exception):
    """Raised when user exceeds their quota limits."""
    def __init__(self, message: str, quota_type: str, limit: int, current: int):
        self.quota_type = quota_type
        self.limit = limit
        self.current = current
        super().__init__(message)


def get_plan_limits(plan_tier: str) -> Dict[str, int]:
    """Return per-plan document, draft, and BibTeX limits."""
    normalized_plan = normalize_plan_tier(plan_tier)

    return {
        'monthly_document_limit': PLAN_PDF_LIMITS.get(normalized_plan, PLAN_PDF_LIMITS['free']),
        'monthly_draft_limit': PLAN_DRAFT_LIMITS.get(normalized_plan, PLAN_DRAFT_LIMITS['free']),
        'monthly_bib_refs_limit': PLAN_BIB_LIMITS.get(normalized_plan, PLAN_BIB_LIMITS['free']),
    }


def normalize_plan_tier(plan_tier: Optional[str]) -> str:
    """Normalize plan aliases to canonical quota tiers."""
    normalized_plan = (plan_tier or 'free').lower()
    if normalized_plan == 'lab':
        return 'team'
    return normalized_plan


def get_project_limit(plan_tier: str) -> int:
    """Return the per-user project cap for the given plan tier."""
    normalized_plan = normalize_plan_tier(plan_tier)
    return PROJECT_LIMITS.get(normalized_plan, PROJECT_LIMITS['free'])


def _get_user_plan_tier(user_id: str) -> str:
    """Look up the user's current plan tier when user_quotas does not exist yet."""
    subscription_response = (
        supabase.table('subscriptions')
        .select('plan_tier, status')
        .eq('user_id', user_id)
        .order('updated_at', desc=True)
        .limit(1)
        .execute()
    )

    if not subscription_response.data:
        return 'free'

    subscription = subscription_response.data[0]
    status = (subscription.get('status') or '').lower()
    if status and status not in {'active', 'trialing', 'past_due'}:
        return 'free'

    return normalize_plan_tier(subscription.get('plan_tier', 'free'))


def _get_user_quota_row(user_id: str) -> Optional[Dict[str, Any]]:
    response = supabase.table('user_quotas').select('*').eq('user_id', user_id).execute()
    if not response.data:
        return None
    return response.data[0]


def sync_user_quota_plan(user_id: str, plan_tier: str) -> Dict[str, Any]:
    """Persist effective plan limits into user_quotas without resetting usage counters."""
    if not supabase:
        raise Exception("Supabase client not configured")

    normalized_plan = normalize_plan_tier(plan_tier)
    plan_limits = get_plan_limits(normalized_plan)
    current_quota = _get_user_quota_row(user_id)
    quota_payload = {
        'plan_tier': normalized_plan,
        'monthly_document_limit': plan_limits['monthly_document_limit'],
        'monthly_draft_limit': plan_limits['monthly_draft_limit'],
        'monthly_bib_refs_limit': plan_limits['monthly_bib_refs_limit'],
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }

    if current_quota:
        supabase.table('user_quotas').update(quota_payload).eq('user_id', user_id).execute()
    else:
        supabase.table('user_quotas').insert({
            'user_id': user_id,
            'monthly_chat_messages_limit': DEFAULT_CHAT_LIMIT,
            'current_month_bib_refs': 0,
            **quota_payload,
        }).execute()

    return _get_user_quota_row(user_id) or {}


def ensure_user_quota(user_id: str) -> Dict[str, Any]:
    """Return the user's quota row, creating it from billing state if needed."""
    if not supabase:
        raise Exception("Supabase client not configured")

    quota = _get_user_quota_row(user_id)
    if quota:
        return quota

    return sync_user_quota_plan(user_id, _get_user_plan_tier(user_id))


async def check_quota(user_id: str, operation_type: str) -> bool:
    """
    Check if user has quota available for the operation.

    Args:
        user_id: User UUID
        operation_type: One of "document", "draft", "bib_import"

    Returns:
        True if quota available

    Raises:
        QuotaExceededError: If user has exceeded their quota
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    quota = ensure_user_quota(user_id)

    # Admin accounts bypass all quota checks
    if quota.get('plan_tier') == 'admin':
        return True

    # Check if quota needs reset
    quota_reset_date = datetime.fromisoformat(quota['quota_reset_date'].replace('Z', '+00:00'))
    if datetime.now(quota_reset_date.tzinfo) > quota_reset_date:
        await reset_quota(user_id)
        quota = ensure_user_quota(user_id)

    # Check limits based on operation type
    if operation_type == "document":
        current = quota['current_month_documents']
        limit = quota['monthly_document_limit']

        if current >= limit:
            raise QuotaExceededError(
                f"Monthly document limit exceeded ({limit} PDFs/month)",
                quota_type="documents",
                limit=limit,
                current=current
            )

    elif operation_type == "bib_import":
        current = quota.get('current_month_bib_refs', 0)
        limit = quota.get('monthly_bib_refs_limit', PLAN_BIB_LIMITS['free'])

        if current >= limit:
            raise QuotaExceededError(
                f"Monthly BibTeX reference limit exceeded ({limit} refs/month)",
                quota_type="bib_refs",
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

    return True


async def increment_quota_usage(user_id: str, operation_type: str, count: int = 1) -> None:
    """
    Increment quota counter after successful operation.

    Uses database function for atomic increment.

    Args:
        user_id: User UUID
        operation_type: One of "document", "draft", "bib_import"
        count: Number to increment by (default 1, use for bib_import batches)
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    field_map = {
        "document": "current_month_documents",
        "draft": "current_month_drafts",
        "bib_import": "current_month_bib_refs",
    }

    field_name = field_map.get(operation_type)
    if not field_name:
        return

    # Call database function for atomic increment (once per count)
    for _ in range(count):
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
        model: OpenAI model used (gpt-5.2, gpt-5-mini, text-embedding-3-small, etc.)
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        project_id: Optional project ID
        document_id: Optional document ID
        draft_id: Optional draft ID
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    # Cost estimation (as of March 2026)
    costs = {
        # GPT-5 series (current - March 2026)
        'gpt-5.2': {'input': 0.00175, 'output': 0.014},  # per 1K tokens
        'gpt-5.2-chat-latest': {'input': 0.00175, 'output': 0.014},
        'gpt-5.2-pro': {'input': 0.00350, 'output': 0.028},  # Estimate: 2x gpt-5.2
        'gpt-5-mini': {'input': 0.00025, 'output': 0.002},
        'gpt-5-nano': {'input': 0.00005, 'output': 0.0004},

        # Embeddings (unchanged)
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
    """Create default free tier quota for user.

    Limits are derived from the user's current plan tier where possible.
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    sync_user_quota_plan(user_id, _get_user_plan_tier(user_id))


async def upgrade_quota_to_tier(user_id: str, plan_tier: str) -> Dict[str, Any]:
    """Synchronize an existing user's enforced quotas with a billing tier."""
    return sync_user_quota_plan(user_id, plan_tier)


async def reset_quota(user_id: str) -> None:
    """Reset user quota counters (called when quota_reset_date is passed)."""
    if not supabase:
        raise Exception("Supabase client not configured")

    # Call database function
    supabase.rpc('reset_quota_if_needed', {
        'user_id_param': user_id
    }).execute()


async def get_quota_summary(user_id: str) -> Dict[str, Any]:
    """
    Get a concise quota summary for display in the upload modal.

    Returns both PDF and BibTeX pools.
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    quota = ensure_user_quota(user_id)
    plan_tier = quota.get('plan_tier', 'free')
    project_limit = get_project_limit(plan_tier)

    # Count current projects
    project_count_res = supabase.table('projects').select('id', count='exact').eq('user_id', user_id).execute()
    project_count = project_count_res.count or 0

    return {
        'pdfs': {
            'used': quota.get('current_month_documents', 0),
            'limit': quota.get('monthly_document_limit', PLAN_PDF_LIMITS['free']),
        },
        'bib_refs': {
            'used': quota.get('current_month_bib_refs', 0),
            'limit': quota.get('monthly_bib_refs_limit', PLAN_BIB_LIMITS['free']),
        },
        'projects': {
            'used': project_count,
            'limit': project_limit,
        },
        'plan_tier': plan_tier,
        'reset_date': quota.get('quota_reset_date'),
    }


async def get_user_quota_info(user_id: str) -> Dict[str, Any]:
    """
    Get user's current quota usage and limits.

    Returns:
        Dictionary with quota information
    """
    if not supabase:
        raise Exception("Supabase client not configured")

    quota = ensure_user_quota(user_id)

    return {
        'plan_tier': quota['plan_tier'],
        'documents': {
            'current': quota['current_month_documents'],
            'limit': quota['monthly_document_limit'],
            'remaining': quota['monthly_document_limit'] - quota['current_month_documents']
        },
        'bib_refs': {
            'current': quota.get('current_month_bib_refs', 0),
            'limit': quota.get('monthly_bib_refs_limit', PLAN_BIB_LIMITS['free']),
            'remaining': quota.get('monthly_bib_refs_limit', PLAN_BIB_LIMITS['free']) - quota.get('current_month_bib_refs', 0),
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
