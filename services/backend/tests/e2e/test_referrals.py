"""
E2E tests: Referral system — generate code, stats.
"""

import pytest
import httpx


@pytest.mark.integration
class TestReferrals:
    async def test_generate_referral_code(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """User can generate a referral code."""
        resp = await async_client.post(
            "/api/referrals/generate",
            headers=auth_headers,
        )
        assert resp.status_code in (200, 201), f"Code generation failed: {resp.text}"
        data = resp.json()
        # Should return a code string
        code = data.get("referral_code") or data.get("code") or data.get("referral_url")
        assert code is not None
        assert len(str(code)) > 4

    async def test_referral_stats_returns_data(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Referral stats endpoint returns structured data."""
        resp = await async_client.get(
            "/api/referrals/stats",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have counts
        assert any(
            key in data
            for key in ("total_referrals", "completed", "pending", "referral_code", "stats")
        )

    async def test_referrals_require_auth(self, async_client: httpx.AsyncClient):
        resp = await async_client.get("/api/referrals/stats")
        assert resp.status_code in (401, 403)

    async def test_referral_code_generate_requires_auth(
        self, async_client: httpx.AsyncClient
    ):
        resp = await async_client.post("/api/referrals/generate")
        assert resp.status_code in (401, 403)

    async def test_invalid_referral_code_returns_error(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Using an invalid referral code returns 400 or 404."""
        resp = await async_client.post(
            "/api/referrals/track",
            json={"referral_code": "INVALID_CODE_XYZ999"},
            headers=auth_headers,
        )
        assert resp.status_code in (400, 404, 409, 422)
