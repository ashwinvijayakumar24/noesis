"""
Stripe Payment Processing Service

Handles subscription creation, checkout, and webhooks
"""

import stripe
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import settings
from app.core.supabase_client import get_supabase_client


# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


PLAN_CONFIGS = {
    "pro": {
        "name": "Pro Plan",
        "price_monthly": 12.00,
        "features": [
            "Unlimited draft analyses",
            "Unlimited papers in library",
            "Advanced feedback (severity levels, line references)",
            "Priority support",
            "Export analysis as PDF"
        ],
        "limits": {
            "monthly_draft_limit": 9999,
            "library_size_limit": 9999,
            "monthly_chat_limit": 9999
        }
    },
    "team": {
        "name": "Research Group Plan",
        "price_per_user_monthly": 20.00,  # $20/user/month
        "minimum_seats": 2,
        "maximum_seats": 3,
        "features": [
            "All Pro features for 2–3 users",
            "Shared project workspaces",
            "Team collaboration features",
            "Lab member invite link",
            "Dedicated support"
        ],
        "limits": {
            "monthly_draft_limit": 9999,
            "library_size_limit": 9999,
            "monthly_chat_limit": 9999,
            "team_members": 3
        }
    }
}


def create_checkout_session(
    user_id: str,
    plan_tier: str,
    success_url: str,
    cancel_url: str,
    team_seats: Optional[int] = None
) -> Dict[str, Any]:
    """
    Create a Stripe Checkout session for subscription

    Args:
        user_id: User ID
        plan_tier: Plan tier (pro, team)
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if user cancels
        team_seats: Number of team seats (required for team plan, minimum 3)

    Returns:
        Dictionary with checkout session URL
    """
    if plan_tier not in PLAN_CONFIGS:
        raise ValueError(f"Invalid plan tier: {plan_tier}")

    plan_config = PLAN_CONFIGS[plan_tier]

    # Validate team seats for team plan
    if plan_tier == "team":
        if team_seats is None:
            team_seats = plan_config["minimum_seats"]
        if team_seats < plan_config["minimum_seats"]:
            raise ValueError(f"Team plan requires minimum {plan_config['minimum_seats']} seats")
        if team_seats > plan_config["maximum_seats"]:
            raise ValueError(f"Team plan allows maximum {plan_config['maximum_seats']} seats")

    supabase = get_supabase_client()

    try:
        # Get or create Stripe customer
        subscription_record = supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()

        stripe_customer_id = None
        if subscription_record.data and len(subscription_record.data) > 0:
            stripe_customer_id = subscription_record.data[0].get("stripe_customer_id")

        # Get user email
        user = supabase.table("auth.users").select("email").eq("id", user_id).execute()
        user_email = user.data[0]["email"] if user.data else None

        if not stripe_customer_id:
            # Create new Stripe customer
            customer = stripe.Customer.create(
                email=user_email,
                metadata={"user_id": user_id}
            )
            stripe_customer_id = customer.id

            # Update subscription record
            if subscription_record.data:
                supabase.table("subscriptions").update({
                    "stripe_customer_id": stripe_customer_id
                }).eq("user_id", user_id).execute()

        # Get price ID from environment or create price
        price_id = None
        if plan_tier == "pro":
            price_id = settings.STRIPE_PRICE_ID_PRO
        elif plan_tier == "team":
            price_id = settings.STRIPE_PRICE_ID_TEAM

        # If no price ID configured, create one dynamically
        if not price_id:
            if plan_tier == "pro":
                price = stripe.Price.create(
                    product_data={
                        "name": plan_config["name"],
                        "metadata": {"plan_tier": plan_tier}
                    },
                    unit_amount=int(plan_config["price_monthly"] * 100),  # Convert to cents
                    currency="usd",
                    recurring={"interval": "month"}
                )
                price_id = price.id
            elif plan_tier == "team":
                # Team plan uses per-user pricing
                price = stripe.Price.create(
                    product_data={
                        "name": f"{plan_config['name']} (per user)",
                        "metadata": {"plan_tier": plan_tier}
                    },
                    unit_amount=int(plan_config["price_per_user_monthly"] * 100),  # Convert to cents
                    currency="usd",
                    recurring={"interval": "month"}
                )
                price_id = price.id

        # Create checkout session
        line_items = [{
            "price": price_id,
            "quantity": team_seats if plan_tier == "team" else 1
        }]

        # For team plan, allow adjustable quantity
        session_params = {
            "customer": stripe_customer_id,
            "payment_method_types": ["card"],
            "line_items": line_items,
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {
                "user_id": user_id,
                "plan_tier": plan_tier
            }
        }

        if plan_tier == "team":
            # Allow users to adjust quantity at checkout (minimum 2, maximum 3)
            session_params["line_items"][0]["adjustable_quantity"] = {
                "enabled": True,
                "minimum": plan_config["minimum_seats"],
                "maximum": plan_config["maximum_seats"]
            }

        session = stripe.checkout.Session.create(**session_params)

        return {
            "checkout_url": session.url,
            "session_id": session.id
        }

    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")


def handle_checkout_completed(session_data: Dict[str, Any]):
    """
    Handle successful checkout completion

    Called from webhook when checkout.session.completed event received

    Args:
        session_data: Stripe session data from webhook
    """
    supabase = get_supabase_client()

    try:
        user_id = session_data["metadata"]["user_id"]
        plan_tier = session_data["metadata"]["plan_tier"]
        subscription_id = session_data.get("subscription")
        customer_id = session_data.get("customer")

        # Update subscription record
        update_data = {
            "plan_tier": plan_tier,
            "stripe_subscription_id": subscription_id,
            "stripe_customer_id": customer_id,
            "status": "active",
            "updated_at": datetime.utcnow().isoformat()
        }

        supabase.table("subscriptions").update(update_data).eq("user_id", user_id).execute()

        # Update usage limits
        supabase.rpc("set_usage_limits", {
            "user_id_param": user_id,
            "tier": plan_tier
        }).execute()

    except Exception as e:
        # Log error but don't fail webhook
        print(f"Error handling checkout completion: {str(e)}")


def handle_subscription_updated(subscription_data: Dict[str, Any]):
    """
    Handle subscription update event

    Args:
        subscription_data: Stripe subscription data from webhook
    """
    supabase = get_supabase_client()

    try:
        subscription_id = subscription_data["id"]
        status = subscription_data["status"]
        current_period_start = datetime.fromtimestamp(subscription_data["current_period_start"]).isoformat()
        current_period_end = datetime.fromtimestamp(subscription_data["current_period_end"]).isoformat()

        # Update subscription
        supabase.table("subscriptions").update({
            "status": status,
            "current_period_start": current_period_start,
            "current_period_end": current_period_end,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("stripe_subscription_id", subscription_id).execute()

    except Exception as e:
        print(f"Error handling subscription update: {str(e)}")


def handle_subscription_deleted(subscription_data: Dict[str, Any]):
    """
    Handle subscription cancellation

    Args:
        subscription_data: Stripe subscription data from webhook
    """
    supabase = get_supabase_client()

    try:
        subscription_id = subscription_data["id"]

        # Get user_id
        subscription = supabase.table("subscriptions").select("user_id").eq("stripe_subscription_id", subscription_id).execute()

        if not subscription.data:
            return

        user_id = subscription.data[0]["user_id"]

        # Downgrade to free tier
        supabase.table("subscriptions").update({
            "plan_tier": "free",
            "status": "canceled",
            "updated_at": datetime.utcnow().isoformat()
        }).eq("stripe_subscription_id", subscription_id).execute()

        # Reset usage limits to free tier
        supabase.rpc("set_usage_limits", {
            "user_id_param": user_id,
            "tier": "free"
        }).execute()

    except Exception as e:
        print(f"Error handling subscription deletion: {str(e)}")


def cancel_subscription(user_id: str, cancel_at_period_end: bool = True) -> Dict[str, Any]:
    """
    Cancel user's subscription

    Args:
        user_id: User ID
        cancel_at_period_end: If True, cancel at end of billing period; if False, cancel immediately

    Returns:
        Dictionary with cancellation status
    """
    supabase = get_supabase_client()

    try:
        # Get subscription
        subscription_record = supabase.table("subscriptions").select("*").eq("user_id", user_id).execute()

        if not subscription_record.data or not subscription_record.data[0].get("stripe_subscription_id"):
            raise ValueError("No active subscription found")

        stripe_subscription_id = subscription_record.data[0]["stripe_subscription_id"]

        # Cancel via Stripe
        if cancel_at_period_end:
            subscription = stripe.Subscription.modify(
                stripe_subscription_id,
                cancel_at_period_end=True
            )
            message = "Subscription will be canceled at the end of the billing period"
        else:
            subscription = stripe.Subscription.delete(stripe_subscription_id)
            message = "Subscription canceled immediately"

        # Update database
        supabase.table("subscriptions").update({
            "cancel_at_period_end": cancel_at_period_end,
            "updated_at": datetime.utcnow().isoformat()
        }).eq("user_id", user_id).execute()

        return {
            "success": True,
            "message": message,
            "effective_date": datetime.fromtimestamp(subscription["current_period_end"]).isoformat() if cancel_at_period_end else datetime.utcnow().isoformat()
        }

    except stripe.error.StripeError as e:
        raise Exception(f"Stripe error: {str(e)}")


def get_usage_limits(user_id: str) -> Dict[str, Any]:
    """
    Get user's current usage and limits

    Args:
        user_id: User ID

    Returns:
        Dictionary with usage stats and limits
    """
    supabase = get_supabase_client()

    try:
        limits = supabase.table("usage_limits").select("*").eq("user_id", user_id).execute()

        if not limits.data:
            # Create default limits
            supabase.rpc("set_usage_limits", {
                "user_id_param": user_id,
                "tier": "free"
            }).execute()

            limits = supabase.table("usage_limits").select("*").eq("user_id", user_id).execute()

        if not limits.data:
            return {
                "plan_tier": "free",
                "drafts_analyzed": 0,
                "drafts_limit": 1,
                "papers_count": 0,
                "papers_limit": 5,
                "can_analyze_draft": True,
                "can_add_paper": True
            }

        limit_data = limits.data[0]

        return {
            "plan_tier": limit_data.get("plan_tier", "free"),
            "drafts_analyzed": limit_data.get("drafts_analyzed_this_month", 0),
            "drafts_limit": limit_data.get("monthly_draft_limit", 1),
            "papers_count": limit_data.get("papers_in_library", 0),
            "papers_limit": limit_data.get("library_size_limit", 5),
            "can_analyze_draft": (
                limit_data.get("monthly_draft_limit", 1) == -1 or
                limit_data.get("drafts_analyzed_this_month", 0) < limit_data.get("monthly_draft_limit", 1)
            ),
            "can_add_paper": (
                limit_data.get("library_size_limit", 5) == -1 or
                limit_data.get("papers_in_library", 0) < limit_data.get("library_size_limit", 5)
            )
        }

    except Exception as e:
        raise Exception(f"Failed to get usage limits: {str(e)}")
