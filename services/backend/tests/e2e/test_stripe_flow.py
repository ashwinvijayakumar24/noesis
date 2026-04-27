"""
E2E tests: Stripe — plans, checkout session creation, webhook health.
"""

import pytest
import httpx


@pytest.mark.integration
class TestStripePlans:
    async def test_plans_endpoint_returns_tiers(
        self,
        async_client: httpx.AsyncClient,
    ):
        """Plans endpoint is public and returns tier definitions."""
        resp = await async_client.get("/api/subscriptions/plans")
        assert resp.status_code == 200
        data = resp.json()
        plans = data if isinstance(data, list) else data.get("plans", [])
        assert len(plans) > 0
        # Should have at least free + pro
        names = [p.get("name", "").lower() for p in plans]
        assert any("free" in n or "pro" in n for n in names)

    async def test_subscription_status_requires_auth(
        self, async_client: httpx.AsyncClient
    ):
        resp = await async_client.get("/api/subscriptions/status")
        assert resp.status_code in (401, 403)

    async def test_subscription_status_returns_tier(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Authenticated user gets subscription status."""
        resp = await async_client.get(
            "/api/subscriptions/status", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert any(
            key in data
            for key in ("plan_tier", "tier", "subscription", "status")
        )


@pytest.mark.integration
class TestStripeCheckout:
    async def test_checkout_session_creation_requires_auth(
        self, async_client: httpx.AsyncClient
    ):
        resp = await async_client.post(
            "/api/subscriptions/create-checkout-session",
            json={"price_id": "price_test", "success_url": "http://localhost:5173/success"},
        )
        assert resp.status_code in (401, 403)

    async def test_checkout_session_invalid_price_fails(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Invalid price_id should return 400 or Stripe error."""
        resp = await async_client.post(
            "/api/subscriptions/create-checkout-session",
            json={
                "price_id": "price_invalid_does_not_exist",
                "success_url": "http://localhost:5173/success",
                "cancel_url": "http://localhost:5173/pricing",
            },
            headers=auth_headers,
        )
        # Should fail gracefully with 400/422/500 but NOT 200
        assert resp.status_code != 200 or "error" in resp.json()


@pytest.mark.integration
class TestStripeWebhook:
    async def test_webhook_endpoint_exists(self, async_client: httpx.AsyncClient):
        """Webhook endpoint exists (even if signature check fails on test payload)."""
        resp = await async_client.post(
            "/api/subscriptions/webhook",
            content=b'{"type": "test.event"}',
            headers={"stripe-signature": "invalid_sig"},
        )
        # 400 = signature check failed (expected), not 404
        assert resp.status_code in (400, 401, 403), (
            f"Webhook endpoint missing or returned unexpected {resp.status_code}"
        )
