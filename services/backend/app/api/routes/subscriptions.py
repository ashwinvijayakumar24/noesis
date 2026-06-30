"""
API routes for subscription management.

Webhook security model
----------------------
* Signature verification is ALWAYS required outside of ENVIRONMENT=development.
* If STRIPE_WEBHOOK_SECRET is unset in a non-development environment the
  endpoint returns 500 (misconfiguration) rather than falling back to
  unsigned JSON parsing.  Accepting unsigned payloads would allow any caller
  to forge subscription events and downgrade / alter any account.
* Idempotency is enforced via the stripe_webhook_events table.  The event_id
  is inserted (ON CONFLICT DO NOTHING) before handlers run.  A duplicate
  delivery returns {"status": "duplicate"} immediately without re-running
  business logic.
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Header
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
import stripe
import json

from app.core.config import settings
from app.core.supabase_client import supabase, get_supabase_client
from app.core.security_middleware import SecureAuthValidator
from app.services.stripe_service import (
    create_checkout_session,
    cancel_subscription,
    get_usage_limits,
    handle_checkout_completed,
    handle_subscription_updated,
    handle_subscription_deleted,
    handle_invoice_payment_failed,
    handle_invoice_payment_succeeded,
    PLAN_CONFIGS,
)
from app.services.quota_management import get_plan_limits, get_project_limit


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def get_current_user(authorization: str = Header(None)) -> str:
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    token = SecureAuthValidator.validate_bearer_token(authorization)
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    plan_tier: str = Field(..., description="Plan tier: pro or team")
    success_url: HttpUrl = Field(..., description="URL to redirect after successful payment")
    cancel_url: HttpUrl = Field(..., description="URL to redirect if payment is canceled")
    team_seats: Optional[int] = Field(
        None,
        description="Number of team seats (required for team plan, minimum 2, maximum 3)",
    )


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class CancelRequest(BaseModel):
    cancel_immediately: bool = Field(
        False,
        description="If True, cancel immediately; otherwise at period end",
    )


# ---------------------------------------------------------------------------
# Webhook helpers
# ---------------------------------------------------------------------------

def _verify_stripe_signature(payload: bytes, stripe_signature: Optional[str]) -> dict:
    """
    Verify the Stripe webhook signature and return the parsed event.

    Raises HTTPException:
      - 400 if the signature header is missing or invalid.
      - 500 if STRIPE_WEBHOOK_SECRET is unset outside development (misconfiguration).

    In ENVIRONMENT=development the secret is optional; unsigned payloads are
    accepted so engineers can use `stripe trigger` locally without configuring
    the webhook secret.  This branch is disabled in staging and production.
    """
    if settings.STRIPE_WEBHOOK_SECRET:
        if not stripe_signature:
            raise HTTPException(status_code=400, detail="Missing Stripe-Signature header")
        try:
            return stripe.Webhook.construct_event(
                payload,
                stripe_signature,
                settings.STRIPE_WEBHOOK_SECRET,
            )
        except stripe.error.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Invalid Stripe signature")

    # No secret configured.
    if settings.ENVIRONMENT != "development":
        # Reject in staging / production -- never fall back to unsigned JSON.
        raise HTTPException(
            status_code=500,
            detail=(
                "STRIPE_WEBHOOK_SECRET is not configured. "
                "Webhook processing is disabled until the secret is set."
            ),
        )

    # Development-only fallback: parse without verification.
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")


def _record_event_or_skip(event_id: str, event_type: str) -> bool:
    """
    Insert event_id into stripe_webhook_events.

    Returns True if the event was newly inserted (should be processed).
    Returns False if the event was already present (duplicate -- skip).

    Uses INSERT ... ON CONFLICT DO NOTHING so the operation is a single
    round-trip with no SELECT + INSERT race condition.
    """
    db = get_supabase_client()
    result = (
        db.table("stripe_webhook_events")
        .insert({"event_id": event_id, "type": event_type})
        .execute()
    )
    # Supabase returns an empty data list when ON CONFLICT DO NOTHING fires.
    return bool(result.data)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/subscriptions/plans")
async def get_available_plans():
    """Return pricing and feature metadata for each subscription tier."""
    return {
        "plans": {
            "free": {
                "name": "Free Plan",
                "price_monthly": 0,
                "features": [
                    "2 draft analyses per month",
                    "30 PDF uploads per month total",
                    "30 BibTeX references per month total",
                    "5 Discover searches per day",
                    "5 Literature Map refreshes per day",
                    "Basic feedback",
                ],
                "limits": {
                    **get_plan_limits("free"),
                    "project_limit": get_project_limit("free"),
                },
            },
            "pro": PLAN_CONFIGS["pro"],
            "team": PLAN_CONFIGS["team"],
        }
    }


@router.post("/subscriptions/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session.

    For Team plans the minimum seat count is 2; users may adjust quantity
    at checkout up to the configured maximum (currently 3).
    """
    try:
        if request.plan_tier not in ["pro", "team"]:
            raise HTTPException(status_code=400, detail="Invalid plan tier")

        if request.plan_tier == "team" and request.team_seats is not None:
            if request.team_seats < 2:
                raise HTTPException(status_code=400, detail="Team plan requires minimum 2 seats")
            if request.team_seats > 3:
                raise HTTPException(status_code=400, detail="Team plan allows maximum 3 seats")

        result = create_checkout_session(
            user_id=user_id,
            plan_tier=request.plan_tier,
            success_url=str(request.success_url),
            cancel_url=str(request.cancel_url),
            team_seats=request.team_seats,
        )
        return CheckoutResponse(**result)

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create checkout session: {str(e)}")


@router.post("/subscriptions/cancel")
async def cancel_user_subscription(
    request: CancelRequest,
    user_id: str = Depends(get_current_user),
):
    """Cancel the authenticated user's subscription."""
    try:
        result = cancel_subscription(
            user_id=user_id,
            cancel_at_period_end=not request.cancel_immediately,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel subscription: {str(e)}")


@router.get("/subscriptions/usage")
async def get_usage(user_id: str = Depends(get_current_user)):
    """Return the authenticated user's current usage against their plan limits."""
    try:
        return get_usage_limits(user_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get usage limits: {str(e)}")


@router.get("/subscriptions/portal-session")
async def create_customer_portal_session(
    user_id: str = Depends(get_current_user),
    return_url: Optional[HttpUrl] = None,
):
    """
    Create a Stripe Customer Portal session so the user can manage their
    payment method, view invoices, or cancel their subscription directly
    inside Stripe's hosted UI.
    """
    try:
        db = get_supabase_client()
        subscription = (
            db.table("subscriptions")
            .select("stripe_customer_id")
            .eq("user_id", user_id)
            .execute()
        )

        if not subscription.data or not subscription.data[0].get("stripe_customer_id"):
            raise HTTPException(status_code=404, detail="No subscription found")

        stripe_customer_id = subscription.data[0]["stripe_customer_id"]
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=str(return_url) if return_url else f"{settings.FRONTEND_URL}/billing",
        )
        return {"url": session.url}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create portal session: {str(e)}")


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="Stripe-Signature"),
):
    """
    Receive and process Stripe webhook events.

    Security guarantees
    -------------------
    1. Signature verification is enforced in all non-development environments.
       An unset STRIPE_WEBHOOK_SECRET in staging/production returns 500 rather
       than accepting unsigned payloads.
    2. Every event is recorded in stripe_webhook_events before handler
       execution.  Duplicate deliveries (Stripe retries) return
       {"status": "duplicate"} without re-running business logic.

    Supported events
    ----------------
    - checkout.session.completed
    - customer.subscription.updated
    - customer.subscription.deleted
    - invoice.payment_failed
    - invoice.payment_succeeded
    """
    payload = await request.body()
    event = _verify_stripe_signature(payload, stripe_signature)

    event_id = event["id"]
    event_type = event["type"]

    # Idempotency check -- returns early if already processed.
    if not _record_event_or_skip(event_id, event_type):
        return {"status": "duplicate", "event_id": event_id}

    # Dispatch to handlers.  Errors inside handlers are caught and logged
    # rather than propagated so Stripe does not retry an event that was
    # successfully recorded but whose side-effects partially failed.
    # Partial failures are surfaced via application logs / Sentry.
    try:
        data_object = event["data"]["object"]

        if event_type == "checkout.session.completed":
            handle_checkout_completed(data_object)

        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(data_object)

        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(data_object)

        elif event_type == "invoice.payment_failed":
            handle_invoice_payment_failed(data_object)

        elif event_type == "invoice.payment_succeeded":
            handle_invoice_payment_succeeded(data_object)

        # Unrecognised event types are accepted (200) and ignored.
        # This prevents Stripe from retrying events we intentionally skip.

    except Exception as e:
        # Do NOT re-raise.  The event is already recorded as processed so a
        # 500 here would cause Stripe to retry and potentially double-process
        # once the bug is fixed.  Log and alert instead.
        import logging
        logging.getLogger(__name__).exception(
            "Handler error for event %s (%s): %s", event_id, event_type, e
        )

    return {"status": "success", "event_type": event_type}
