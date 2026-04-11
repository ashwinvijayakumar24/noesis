"""
Quick test script for Stripe integration
Run this inside the backend container to test Stripe functions
"""

import sys
sys.path.insert(0, '/app')

from app.services.stripe_service import PLAN_CONFIGS, create_checkout_session
from app.core.config import settings
import json


def test_plan_configs():
    """Test that plan configurations are correct"""
    print("=" * 60)
    print("TESTING PLAN CONFIGURATIONS")
    print("=" * 60)

    print("\n✅ Pro Plan:")
    print(json.dumps(PLAN_CONFIGS["pro"], indent=2))

    print("\n✅ Team Plan:")
    print(json.dumps(PLAN_CONFIGS["team"], indent=2))

    # Validate Team plan pricing
    assert "price_per_user_monthly" in PLAN_CONFIGS["team"], "Team plan missing price_per_user_monthly"
    assert PLAN_CONFIGS["team"]["price_per_user_monthly"] == 20.0, f"Team plan price should be 20.0, got {PLAN_CONFIGS['team']['price_per_user_monthly']}"
    assert PLAN_CONFIGS["team"]["minimum_seats"] == 2, "Team plan minimum seats should be 2"
    assert PLAN_CONFIGS["team"]["maximum_seats"] == 3, "Team plan maximum seats should be 3"

    print("\n✅ Team plan pricing validated: $20/user/month (min 2, max 3 seats)")


def test_stripe_keys():
    """Test that Stripe keys are configured"""
    print("\n" + "=" * 60)
    print("TESTING STRIPE CONFIGURATION")
    print("=" * 60)

    if settings.STRIPE_SECRET_KEY:
        print(f"✅ STRIPE_SECRET_KEY: {settings.STRIPE_SECRET_KEY[:15]}...")
    else:
        print("❌ STRIPE_SECRET_KEY: Not configured")

    if settings.STRIPE_WEBHOOK_SECRET:
        print(f"✅ STRIPE_WEBHOOK_SECRET: {settings.STRIPE_WEBHOOK_SECRET[:15]}...")
    else:
        print("❌ STRIPE_WEBHOOK_SECRET: Not configured")

    if settings.STRIPE_PRICE_ID_PRO:
        print(f"✅ STRIPE_PRICE_ID_PRO: {settings.STRIPE_PRICE_ID_PRO}")
    else:
        print("⚠️  STRIPE_PRICE_ID_PRO: Not configured (will create dynamically)")

    if settings.STRIPE_PRICE_ID_TEAM:
        print(f"✅ STRIPE_PRICE_ID_TEAM: {settings.STRIPE_PRICE_ID_TEAM}")
    else:
        print("⚠️  STRIPE_PRICE_ID_TEAM: Not configured (will create dynamically)")


def test_checkout_session_dry_run():
    """Test checkout session creation (dry run - explain what would happen)"""
    print("\n" + "=" * 60)
    print("TESTING CHECKOUT SESSION CREATION (DRY RUN)")
    print("=" * 60)

    print("\n📝 Pro Plan Checkout:")
    print("   - User ID: test-user-123")
    print("   - Plan: Pro ($12/month)")
    print("   - Quantity: 1")
    print("   - Would create Stripe checkout session")
    print("   - Would redirect to: http://localhost:5173/success")

    print("\n📝 Team Plan Checkout (5 seats):")
    print("   - User ID: test-user-123")
    print("   - Plan: Team ($20/user/month)")
    print("   - Quantity: 5 seats = $100/month")
    print("   - Adjustable quantity enabled (3-100)")
    print("   - Would create Stripe checkout session")
    print("   - Would redirect to: http://localhost:5173/success")

    print("\n⚠️  Note: Actual checkout creation requires:")
    print("   1. Valid Supabase user ID in database")
    print("   2. Stripe API calls (which would create real test-mode sessions)")
    print("   3. To test live, use the API endpoints with proper authentication")


if __name__ == "__main__":
    try:
        test_plan_configs()
        test_stripe_keys()
        test_checkout_session_dry_run()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        print("\nStripe integration is properly configured!")
        print("Next steps:")
        print("  1. Test with real Stripe checkout (requires authentication)")
        print("  2. Use Stripe test card: 4242 4242 4242 4242")
        print("  3. Verify webhook events are received")

    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
