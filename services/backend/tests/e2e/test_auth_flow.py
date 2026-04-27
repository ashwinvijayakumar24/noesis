"""
E2E tests: Auth flow
Tests: login, /auth/me, /auth/quota-summary, invalid credentials.
"""

import os
import pytest
import httpx


TEST_EMAIL = os.getenv("TEST_USER_EMAIL", "test@noesis.dev")
TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "testpassword123")


@pytest.mark.integration
class TestAuthFlow:
    async def test_login_returns_access_token(self, async_client: httpx.AsyncClient):
        resp = await async_client.post(
            "/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert resp.status_code == 200
        data = resp.json()
        token = data.get("access_token") or data.get("session", {}).get("access_token")
        assert token is not None
        assert len(token) > 20

    async def test_invalid_credentials_returns_401(self, async_client: httpx.AsyncClient):
        resp = await async_client.post(
            "/auth/login",
            json={"email": "bad@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code in (400, 401, 422)

    async def test_me_endpoint_returns_user(
        self, async_client: httpx.AsyncClient, auth_headers: dict
    ):
        resp = await async_client.get("/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data or "user_id" in data or "email" in data

    async def test_me_endpoint_requires_auth(self, async_client: httpx.AsyncClient):
        resp = await async_client.get("/auth/me")
        assert resp.status_code in (401, 403)

    async def test_quota_summary_returns_limits(
        self, async_client: httpx.AsyncClient, auth_headers: dict
    ):
        resp = await async_client.get("/auth/quota-summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Should have at least document quota info
        assert any(
            key in data
            for key in ("monthly_document_limit", "documents", "plan_tier", "quota")
        )

    async def test_quota_summary_requires_auth(self, async_client: httpx.AsyncClient):
        resp = await async_client.get("/auth/quota-summary")
        assert resp.status_code in (401, 403)
