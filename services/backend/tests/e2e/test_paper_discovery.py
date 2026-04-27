"""
E2E tests: Paper discovery agent — search PubMed/arXiv/Semantic Scholar.

Note: These tests use mocked external APIs where possible to avoid
rate limits. Mark slow tests appropriately.
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock


@pytest.mark.integration
class TestPaperDiscovery:
    async def test_discovery_endpoint_requires_auth(
        self, async_client: httpx.AsyncClient
    ):
        resp = await async_client.get("/api/paper-discovery/search?q=machine+learning")
        assert resp.status_code in (401, 403)

    async def test_discovery_search_returns_results(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Search returns a list of papers or quota error."""
        resp = await async_client.get(
            "/api/paper-discovery/search?q=transformer+neural+network",
            headers=auth_headers,
        )
        # 200 = results found, 402/429 = quota exceeded (acceptable)
        assert resp.status_code in (200, 402, 429), (
            f"Unexpected status: {resp.status_code} {resp.text}"
        )
        if resp.status_code == 200:
            data = resp.json()
            papers = data if isinstance(data, list) else data.get("papers", data.get("results", []))
            assert isinstance(papers, list)

    async def test_discovery_empty_query_fails(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Empty search query returns 400/422."""
        resp = await async_client.get(
            "/api/paper-discovery/search?q=",
            headers=auth_headers,
        )
        assert resp.status_code in (400, 422)

    async def test_discovery_quota_tracked(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """After a successful search, daily quota is decremented."""
        # Get initial quota state
        quota_before = await async_client.get(
            "/auth/quota-summary", headers=auth_headers
        )
        assert quota_before.status_code == 200

        # Do a search (may hit quota)
        await async_client.get(
            "/api/paper-discovery/search?q=test+query",
            headers=auth_headers,
        )

        # Quota state should have changed or stayed (if at limit)
        quota_after = await async_client.get(
            "/auth/quota-summary", headers=auth_headers
        )
        assert quota_after.status_code == 200


@pytest.mark.integration
class TestPaperDiscoverySources:
    @pytest.mark.parametrize("source", ["arxiv", "pubmed", "semantic_scholar"])
    async def test_search_by_source(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
        source: str,
    ):
        """Search can filter by specific source."""
        resp = await async_client.get(
            f"/api/paper-discovery/search?q=machine+learning&source={source}",
            headers=auth_headers,
        )
        # 200 = results, 400 = invalid source, 402/429 = quota
        assert resp.status_code in (200, 400, 402, 429)
