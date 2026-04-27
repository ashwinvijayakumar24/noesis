"""
E2E tests: Security — auth required on all routes, no token leakage.

Every protected route must return 401/403 with no access token in the body.
"""

import pytest
import httpx


# All routes that MUST require authentication
PROTECTED_ROUTES = [
    ("GET", "/projects/"),
    ("GET", "/documents/"),
    ("GET", "/drafts/"),
    ("GET", "/quota/me"),
    ("GET", "/analytics/dashboard"),
    ("GET", "/citations/"),
    ("GET", "/api/referrals/stats"),
    ("GET", "/api/paper-discovery/search?q=test"),
    ("GET", "/search?q=test"),
]

# Routes that should be publicly accessible (no auth)
PUBLIC_ROUTES = [
    ("GET", "/health"),
    ("GET", "/api/platform/stats"),
]


@pytest.mark.integration
class TestSecurityAuthRequired:
    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    async def test_route_requires_auth(
        self, async_client: httpx.AsyncClient, method: str, path: str
    ):
        """No auth header → 401 or 403, never 200."""
        resp = await async_client.request(method, path)
        assert resp.status_code in (401, 403), (
            f"{method} {path} returned {resp.status_code} without auth"
        )

    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    async def test_no_token_leakage_in_error(
        self, async_client: httpx.AsyncClient, method: str, path: str
    ):
        """Error responses must not include access tokens or sensitive data."""
        resp = await async_client.request(method, path)
        body = resp.text.lower()
        assert "access_token" not in body
        assert "service_role_key" not in body
        assert "supabase_url" not in body

    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    async def test_invalid_token_is_rejected(
        self, async_client: httpx.AsyncClient, method: str, path: str
    ):
        """Forged/invalid Bearer token → 401 or 403."""
        resp = await async_client.request(
            method, path,
            headers={"Authorization": "Bearer invalid.jwt.token.here"}
        )
        assert resp.status_code in (401, 403), (
            f"{method} {path} accepted invalid token (status {resp.status_code})"
        )


@pytest.mark.integration
class TestPublicRoutes:
    @pytest.mark.parametrize("method,path", PUBLIC_ROUTES)
    async def test_public_route_accessible(
        self, async_client: httpx.AsyncClient, method: str, path: str
    ):
        """Public routes must be accessible without auth."""
        resp = await async_client.request(method, path)
        assert resp.status_code == 200, (
            f"{method} {path} should be public but returned {resp.status_code}"
        )


@pytest.mark.integration
class TestSecurityHeaders:
    async def test_security_headers_present(self, async_client: httpx.AsyncClient):
        """Response must include critical security headers."""
        resp = await async_client.get("/health")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        # X-Content-Type-Options prevents MIME sniffing
        assert "x-content-type-options" in headers
        # X-Frame-Options prevents clickjacking
        assert "x-frame-options" in headers

    async def test_cors_does_not_allow_arbitrary_origins(
        self, async_client: httpx.AsyncClient, auth_headers: dict
    ):
        """CORS should not echo back arbitrary origins."""
        resp = await async_client.get(
            "/health",
            headers={"Origin": "https://evil.example.com"},
        )
        cors = resp.headers.get("access-control-allow-origin", "")
        assert cors != "https://evil.example.com", "CORS echoes arbitrary origin"
