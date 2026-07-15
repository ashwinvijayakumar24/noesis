"""
Stripe Payment Processing Service

Handles subscription creation, checkout, and webhook event processing.

Handler contract
----------------
Every handle_* function:
  - Accepts the Stripe event data object as a dict.
  - Catches all exceptions internally and logs them rather than raising.
    The webhook endpoint records the event as processed before calling
    handlers, so raising here would prevent Stripe retries but leave the
    DB in a partially-updated state.  Logging + Sentry alerting is the
    correct failure mode.
  - Returns None.
"""

import logging
import stripe
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.core.config import settings
from app.core.supabase_client import get_supabase_client
from app.services.quota_management import (
    PLAN_BIB_LIMITS,
    PLAN_DRAFT_LIMITS,
    PLAN_PDF_LIMITS,
    ensure_user_quota,
    get_plan_limits,
    get_project_limit,
    normalize_plan_tier,
    sync_user_quota_plan,
)

logger = logging.getLogger(__name__)

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------------------------------------------------------------------------
# Plan configuration
# ---------------------------------------------------------------------------

PLAN_CONFIGS = {
    "pro": {
        "name": "Pro Plan",
        "price_monthly": 12.00,
        "features": [
            "20 draft analyses per month",
            "100 PDF uploads per month total",
            "100 BibTeX references per month total",
            "50 Discover searches per day",
            "Unlimited Literature Map refreshes",
            "Priority support",
            "Export analysis as PDF",
        ],
        "limits": get_plan_limits("pro"),
    },
    "team": {
        "name": "Research Group Plan",
        "price_per_user_monthly": 20.00,
        "minimum_seats": 2,
        "maximum_seats": 3,
        "features": [
            "All Pro features for 2-3 users",
            "Effectively unlimited usage",
            "Shared project workspaces",
            "Team collaboration features",
            "Shared literature libraries",
            "Dedicated support",
        ],
        "limits": {
            **get_plan_limits("team"),
            "project_limit": get_project_limit("team"),
        },
    },
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalize_plan_tier(plan_tier: Optional[str]) -> str:
    return normalize_plan_tier(plan_tier)


def _to_iso8601(timestamp: Optional[int]) -> Optional[str]:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def _get_plan_tier_from_subscription_data(
    subscription_data: Dict[str, Any],
    current_plan_tier: str = "free",
) -> str:
    metadata = subscription_data.get("metadata") or {}
    metadata_plan = metadata.get("plan_tier")
    if metadata_plan:
        return _normalize_plan_tier(metadata_plan)

    items = (((subscription_data.get("items") or {}).get("data")) or [])
    price_ids = {
        (item.get("price") or {}).get("id")
        for item in items
        if item.get("price")
    }

    if settings.STRIPE_PRICE_ID_PRO and settings.STRIPE_PRICE_ID_PRO in price_ids:
        return "pro"
    if settings.STRIPE_PRICE_ID_TEAM and settings.STRIPE_PRICE_ID_TEAM in price_ids:
        return "team"

    return _normalize_plan_tier(current_plan_tier)


def _get_seat_count(subscription_data: Dict[str, Any]) -> Optional[int]:
    """
    Extract the seat count from a subscription object.

    For team plans this is items.data[0].quantity.  For other plans
    this returns None so the column is left as NULL rather than
    incorrectly storing 1.
    """
    items = (((subscription_data.get("items") or {}).get("data")) or [])
    if not items:
        return None
    quantity = items[0].get("quantity")
    return int(quantity) if quantity is not None else None


def _get_subscription_id_and_user(
    subscription_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Look up a subscription record by stripe_subscription_id.

    Returns a dict with at least {user_id, plan_tier} or None if not found.
    """
    db = get_supabase_client()
    result = (
        db.table("subscriptions")
        .select("user_id, plan_tier")
        .eq("stripe_subscription_id", subscription_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ---------------------------------------------------------------------------
# Checkout session creation
# ---------------------------------------------------------------------------

def create_checkout_session(
    user_id: str,
    plan_tier: str,
    success_url: str,
    cancel_url: str,
    team_seats: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Create a Stripe Checkout session for a subscription.

    Returns a dict with checkout_url and session_id.
    """
    if plan_tier not in PLAN_CONFIGS:
        raise ValueError(f"Invalid plan tier: {plan_tier}")

    plan_config = PLAN_CONFIGS[plan_tier]

    if plan_tier == "team":
        if team_seats is None:
            team_seats = plan_config["minimum_seats"]
        if team_seats < plan_config["minimum_seats"]:
            raise ValueError(f"Team plan requires minimum {plan_config['minimum_seats']} seats")
        if team_seats > plan_config["maximum_seats"]:
            raise ValueError(f"Team plan allows maximum {plan_config['maximum_seats']} seats")

    db = get_supabase_client()

    try:
        subscription_record = (
            db.table("subscriptions").select("*").eq("user_id", user_id).execute()
        )

        stripe_customer_id = None
        if subscription_record.data:
            stripe_customer_id = subscription_record.data[0].get("stripe_customer_id")

        user = db.table("auth.users").select("email").eq("id", user_id).execute()
        user_email = user.data[0]["email"] if user.data else None

        if not stripe_customer_id:
            customer = stripe.Customer.create(
                email=user_email,
                metadata={"user_id": user_id},
            )
            stripe_customer_id = customer.id
            db.table("subscriptions").upsert(
                {"user_id": user_id, "stripe_customer_id": stripe_customer_id},
                on_conflict="user_id",
            ).execute()

        price_id = None
        if plan_tier == "pro":
            price_id = settings.STRIPE_PRICE_ID_PRO
        elif plan_tier == "team":
            price_id = settings.STRIPE_PRICE_ID_TEAM

        if not price_id:
            raise ValueError(
                f"STRIPE_PRICE_ID_{plan_tier.upper()} is not configured. "
                "Set this env var to the Stripe price ID for this plan."
            )

        line_items = [{"price": price_id, "quantity": team_seats if plan_tier == "team" else 1}]

        session_params = {
            "customer": stripe_customer_id,
            "payment_method_types": ["card"],
            "line_items": line_items,
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"user_id": user_id, "plan_tier": plan_tier},
        }

        if plan_tier == "team":
            session_params["line_items"][0]["adjustable_quantity"] = {
                "enabled": True,
                "minimum": plan_config["minimum_seats"],
                "maximum": plan_config["maximum_seats"],
            }

        session = stripe.checkout.Session.create(**session_params)
        return {"checkout_url": session.url, "session_id": session.id}

    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")


# ---------------------------------------------------------------------------
# Webhook event handlers
# ---------------------------------------------------------------------------

def handle_checkout_completed(session_data: Dict[str, Any]) -> None:
    """
    checkout.session.completed

    Upserts the subscription record and syncs the quota plan tier.
    """
    db = get_supabase_client()
    try:
        metadata = session_data.get("metadata") or {}
        user_id = metadata.get("user_id")
        plan_tier = _normalize_plan_tier(metadata.get("plan_tier"))
        if not user_id:
            logger.warning(
                "checkout.session.completed missing user_id in metadata, session=%s",
                session_data.get("id"),
            )
            return
        subscription_id = session_data.get("subscription")
        customer_id = session_data.get("customer")

        db.table("subscriptions").upsert(
            {
                "user_id": user_id,
                "plan_tier": plan_tier,
                "stripe_subscription_id": subscription_id,
                "stripe_customer_id": customer_id,
                "status": "active",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            on_conflict="user_id",
        ).execute()

        sync_user_quota_plan(user_id, plan_tier)

    except Exception as e:
        logger.exception("handle_checkout_completed failed: %s", e)


def handle_subscription_updated(subscription_data: Dict[str, Any]) -> None:
    """
    customer.subscription.updated

    Updates plan tier, status, billing period, cancellation flag, and seat
    count.  Seat count (items.data[0].quantity) is persisted so the app can
    show how many paid seats exist without a Stripe API call.

    Enforced quota tier:
      active | trialing | past_due -> keep paid plan tier (past_due retains
      access per Noesis dunning policy; see subscriptions.last_payment_failed_at
      for UI hints).
      Any other status -> downgrade to free.
    """
    db = get_supabase_client()
    try:
        subscription_id = subscription_data["id"]
        status = subscription_data["status"]

        existing = _get_subscription_id_and_user(subscription_id)
        if not existing:
            return

        current_plan_tier = existing.get("plan_tier", "free")
        user_id = existing["user_id"]
        plan_tier = _get_plan_tier_from_subscription_data(subscription_data, current_plan_tier)

        update_payload: Dict[str, Any] = {
            "plan_tier": plan_tier,
            "status": status,
            "current_period_start": _to_iso8601(subscription_data.get("current_period_start")),
            "current_period_end": _to_iso8601(subscription_data.get("current_period_end")),
            "cancel_at_period_end": subscription_data.get("cancel_at_period_end", False),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persist seat count for team plans.
        seat_count = _get_seat_count(subscription_data)
        if plan_tier == "team" and seat_count is not None:
            update_payload["seats"] = seat_count

        db.table("subscriptions").update(update_payload).eq(
            "stripe_subscription_id", subscription_id
        ).execute()

        enforced_tier = plan_tier if status in {"active", "trialing", "past_due"} else "free"
        sync_user_quota_plan(user_id, enforced_tier)

    except Exception as e:
        logger.exception("handle_subscription_updated failed: %s", e)


def handle_subscription_deleted(subscription_data: Dict[str, Any]) -> None:
    """
    customer.subscription.deleted

    Downgrades the user to the free tier.
    """
    db = get_supabase_client()
    try:
        subscription_id = subscription_data["id"]
        existing = _get_subscription_id_and_user(subscription_id)
        if not existing:
            return

        user_id = existing["user_id"]

        db.table("subscriptions").update(
            {
                "plan_tier": "free",
                "status": "canceled",
                "seats": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("stripe_subscription_id", subscription_id).execute()

        sync_user_quota_plan(user_id, "free")

    except Exception as e:
        logger.exception("handle_subscription_deleted failed: %s", e)


def handle_invoice_payment_failed(invoice_data: Dict[str, Any]) -> None:
    """
    invoice.payment_failed

    Marks the subscription status as past_due and records the failure
    timestamp.  Quota access is preserved (past_due retains the paid tier
    per Noesis dunning policy) so users are not immediately locked out on
    the first retry attempt.

    A notification hook placeholder is emitted here.  When the transactional
    email service is integrated (Issue #7) it should be triggered from this
    point using the user_id and customer email.
    """
    db = get_supabase_client()
    try:
        subscription_id = invoice_data.get("subscription")
        if not subscription_id:
            logger.warning(
                "invoice.payment_failed received with no subscription id: %s",
                invoice_data.get("id"),
            )
            return

        existing = _get_subscription_id_and_user(subscription_id)
        if not existing:
            return

        user_id = existing["user_id"]
        failed_at = datetime.now(timezone.utc).isoformat()

        db.table("subscriptions").update(
            {
                "status": "past_due",
                "last_payment_failed_at": failed_at,
                "updated_at": failed_at,
            }
        ).eq("stripe_subscription_id", subscription_id).execute()

        # Quota tier is deliberately kept at the paid plan for past_due
        # subscriptions.  Stripe will retry the payment; we do not downgrade
        # until the subscription transitions to unpaid or deleted.
        current_plan_tier = existing.get("plan_tier", "free")
        sync_user_quota_plan(user_id, current_plan_tier)

        # Notification hook placeholder -- replace with email dispatch (Issue #7).
        logger.info(
            "NOTIFICATION_HOOK payment_failed user_id=%s subscription_id=%s",
            user_id,
            subscription_id,
        )

    except Exception as e:
        logger.exception("handle_invoice_payment_failed failed: %s", e)


def handle_invoice_payment_succeeded(invoice_data: Dict[str, Any]) -> None:
    """
    invoice.payment_succeeded

    Clears the past_due status and last_payment_failed_at, restoring the
    subscription to active.  Re-syncs quota to the current paid tier.

    This fires on every successful invoice, including the initial charge
    after checkout.session.completed, so it is idempotent and safe to
    run repeatedly.
    """
    db = get_supabase_client()
    try:
        subscription_id = invoice_data.get("subscription")
        if not subscription_id:
            return

        existing = _get_subscription_id_and_user(subscription_id)
        if not existing:
            return

        user_id = existing["user_id"]
        current_plan_tier = existing.get("plan_tier", "free")

        db.table("subscriptions").update(
            {
                "status": "active",
                "last_payment_failed_at": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("stripe_subscription_id", subscription_id).execute()

        sync_user_quota_plan(user_id, current_plan_tier)

    except Exception as e:
        logger.exception("handle_invoice_payment_succeeded failed: %s", e)


# ---------------------------------------------------------------------------
# Subscription management
# ---------------------------------------------------------------------------

def cancel_subscription(user_id: str, cancel_at_period_end: bool = True) -> Dict[str, Any]:
    """Cancel a user's Stripe subscription."""
    db = get_supabase_client()
    try:
        subscription_record = (
            db.table("subscriptions").select("*").eq("user_id", user_id).execute()
        )
        if not subscription_record.data or not subscription_record.data[0].get(
            "stripe_subscription_id"
        ):
            raise ValueError("No active subscription found")

        stripe_subscription_id = subscription_record.data[0]["stripe_subscription_id"]

        if cancel_at_period_end:
            subscription = stripe.Subscription.modify(
                stripe_subscription_id, cancel_at_period_end=True
            )
            message = "Subscription will be canceled at the end of the billing period"
        else:
            subscription = stripe.Subscription.delete(stripe_subscription_id)
            message = "Subscription canceled immediately"

        db.table("subscriptions").update(
            {
                "cancel_at_period_end": cancel_at_period_end,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", user_id).execute()

        return {
            "success": True,
            "message": message,
            "effective_date": (
                datetime.fromtimestamp(
                    subscription["current_period_end"], tz=timezone.utc
                ).isoformat()
                if cancel_at_period_end
                else datetime.now(timezone.utc).isoformat()
            ),
        }

    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")


def get_usage_limits(user_id: str) -> Dict[str, Any]:
    """Return the user's current usage counters and plan limits."""
    try:
        limit_data = ensure_user_quota(user_id)
        document_limit = limit_data.get("monthly_document_limit", PLAN_PDF_LIMITS["free"])
        bib_limit = limit_data.get("monthly_bib_refs_limit", PLAN_BIB_LIMITS["free"])
        draft_limit = limit_data.get("monthly_draft_limit", PLAN_DRAFT_LIMITS["free"])
        documents_used = limit_data.get("current_month_documents", 0)
        bib_refs_used = limit_data.get("current_month_bib_refs", 0)
        drafts_used = limit_data.get("current_month_drafts", 0)

        return {
            "plan_tier": normalize_plan_tier(limit_data.get("plan_tier", "free")),
            "documents_uploaded": documents_used,
            "documents_limit": document_limit,
            "bib_refs_imported": bib_refs_used,
            "bib_refs_limit": bib_limit,
            "drafts_analyzed": drafts_used,
            "drafts_limit": draft_limit,
            "papers_count": documents_used + bib_refs_used,
            "papers_limit": document_limit + bib_limit,
            "can_analyze_draft": drafts_used < draft_limit or draft_limit >= 9999,
            "can_upload_document": documents_used < document_limit or document_limit >= 9999,
            "can_import_bib": bib_refs_used < bib_limit or bib_limit >= 9999,
            "can_add_paper": (
                documents_used < document_limit
                or bib_refs_used < bib_limit
                or document_limit >= 9999
                or bib_limit >= 9999
            ),
            "documents": {
                "current": documents_used,
                "limit": document_limit,
                "remaining": max(document_limit - documents_used, 0),
            },
            "bib_refs": {
                "current": bib_refs_used,
                "limit": bib_limit,
                "remaining": max(bib_limit - bib_refs_used, 0),
            },
            "quota_reset_date": limit_data.get("quota_reset_date"),
        }

    except Exception as e:
        raise Exception(f"Failed to get usage limits: {str(e)}")
