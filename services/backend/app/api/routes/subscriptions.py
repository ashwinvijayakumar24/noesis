"""
API routes for subscription management
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Header
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional
import stripe

from app.core.config import settings
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
from app.services.stripe_service import (
    create_checkout_session,
    cancel_subscription,
    get_usage_limits,
    handle_checkout_completed,
    handle_subscription_updated,
    handle_subscription_deleted,
    PLAN_CONFIGS
)


def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    token = SecureAuthValidator.validate_bearer_token(authorization)
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


router = APIRouter()


class CheckoutRequest(BaseModel):
    plan_tier: str = Field(..., description="Plan tier: pro or team")
    success_url: HttpUrl = Field(..., description="URL to redirect after successful payment")
    cancel_url: HttpUrl = Field(..., description="URL to redirect if payment is canceled")
    team_seats: Optional[int] = Field(None, description="Number of team seats (required for team plan, minimum 3)")


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str


class CancelRequest(BaseModel):
    cancel_immediately: bool = Field(False, description="If True, cancel immediately; otherwise at period end")


@router.get("/subscriptions/plans")
async def get_available_plans():
    """
    Get available subscription plans

    Returns pricing and features for each tier
    """
    return {
        "plans": {
            "free": {
                "name": "Free Plan",
                "price_monthly": 0,
                "features": [
                    "1 draft analysis per month",
                    "5 papers in library",
                    "20 chat messages per month",
                    "Basic feedback"
                ],
                "limits": {
                    "monthly_draft_limit": 1,
                    "library_size_limit": 5,
                    "monthly_chat_limit": 20
                }
            },
            "pro": PLAN_CONFIGS["pro"],
            "team": PLAN_CONFIGS["team"]
        }
    }


@router.post("/subscriptions/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Create a Stripe Checkout session

    Redirects user to Stripe payment page

    For Team plans:
    - Minimum 2 seats required
    - Users can adjust quantity at checkout (2-3 seats)
    - Priced at $20/user/month
    """
    try:
        if request.plan_tier not in ["pro", "team"]:
            raise HTTPException(status_code=400, detail="Invalid plan tier")

        # Validate team_seats for team plan
        if request.plan_tier == "team" and request.team_seats is not None:
            if request.team_seats < 3:
                raise HTTPException(status_code=400, detail="Team plan requires minimum 3 seats")
            if request.team_seats > 100:
                raise HTTPException(status_code=400, detail="Team plan allows maximum 100 seats")

        result = create_checkout_session(
            user_id=user_id,
            plan_tier=request.plan_tier,
            success_url=str(request.success_url),
            cancel_url=str(request.cancel_url),
            team_seats=request.team_seats
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
    user_id: str = Depends(get_current_user)
):
    """
    Cancel user's subscription

    Can cancel immediately or at end of billing period
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        result = cancel_subscription(
            user_id=user_id,
            cancel_at_period_end=not request.cancel_immediately
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel subscription: {str(e)}")


@router.get("/subscriptions/usage")
async def get_usage(
    user_id: str = Depends(get_current_user)
):
    """
    Get user's current usage and limits
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        usage = get_usage_limits(user_id)

        return usage

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get usage limits: {str(e)}")


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature")
):
    """
    Handle Stripe webhooks

    ⚠️ IMPORTANT: This endpoint requires webhook secret to be configured
    You'll need to set STRIPE_WEBHOOK_SECRET in environment variables

    To get webhook secret:
    1. Go to https://dashboard.stripe.com/test/webhooks
    2. Add endpoint: https://your-domain.com/api/webhooks/stripe
    3. Select events: checkout.session.completed, customer.subscription.updated, customer.subscription.deleted
    4. Copy webhook signing secret
    5. Add to .env as STRIPE_WEBHOOK_SECRET
    """
    try:
        payload = await request.body()

        # Verify webhook signature (if secret is configured)
        if settings.STRIPE_WEBHOOK_SECRET:
            try:
                event = stripe.Webhook.construct_event(
                    payload,
                    stripe_signature,
                    settings.STRIPE_WEBHOOK_SECRET
                )
            except stripe.error.SignatureVerificationError:
                raise HTTPException(status_code=400, detail="Invalid signature")
        else:
            # WARNING: This is insecure - only for development
            import json
            event = json.loads(payload)

        # Handle different event types
        event_type = event["type"]

        if event_type == "checkout.session.completed":
            handle_checkout_completed(event["data"]["object"])

        elif event_type == "customer.subscription.updated":
            handle_subscription_updated(event["data"]["object"])

        elif event_type == "customer.subscription.deleted":
            handle_subscription_deleted(event["data"]["object"])

        return {"status": "success", "event_type": event_type}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook processing failed: {str(e)}")


@router.get("/subscriptions/portal-session")
async def create_customer_portal_session(
    user_id: str = Depends(get_current_user),
    return_url: HttpUrl = None
):
    """
    Create a Stripe Customer Portal session

    Allows users to manage their subscription, payment methods, etc.
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        from app.core.supabase_client import get_supabase_client
        supabase = get_supabase_client()

        # Get Stripe customer ID
        subscription = supabase.table("subscriptions").select("stripe_customer_id").eq("user_id", user_id).execute()

        if not subscription.data or not subscription.data[0].get("stripe_customer_id"):
            raise HTTPException(status_code=404, detail="No subscription found")

        stripe_customer_id = subscription.data[0]["stripe_customer_id"]

        # Create portal session
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=str(return_url) if return_url else "https://noesis.is/dashboard"
        )

        return {"url": session.url}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create portal session: {str(e)}")
