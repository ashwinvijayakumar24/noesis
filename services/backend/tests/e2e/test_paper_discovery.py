"""
E2E tests: Paper discovery agent — search PubMed/arXiv/Semantic Scholar.

Note: These tests use mocked external APIs where possible to avoid
rate limits. Mark slow tests appropriately.
"""

import pytest
import httpx
from unittest.mock import patch, AsyncMock


# NOTE: the standalone `/api/paper-discovery/search` endpoint these tests were
# written against no longer exists. External paper discovery is now exposed via
# `/paper-recommendations/projects/{project_id}/search` (project-scoped, different
# request/response contract). The behavior tests below are skipped pending a
# rewrite against that contract; the auth-contract test is repointed to the live
# library search endpoint so the auth guarantee stays covered.
_DISCOVERY_REWRITE = "paper-discovery replaced by /paper-recommendations/projects/{id}/search; needs contract rewrite"


@pytest.mark.integration
class TestPaperDiscovery:
    async def test_discovery_endpoint_requires_auth(
        self, async_client: httpx.AsyncClient
    ):
        # Library search requires auth (replacement surface for discovery).
        resp = await async_client.get("/search/?q=machine+learning")
        assert resp.status_code in (401, 403)

    @pytest.mark.skip(reason=_DISCOVERY_REWRITE)
    async def test_discovery_search_returns_results(self, async_client, auth_headers):
        ...

    @pytest.mark.skip(reason=_DISCOVERY_REWRITE)
    async def test_discovery_empty_query_fails(self, async_client, auth_headers):
        ...

    @pytest.mark.skip(reason=_DISCOVERY_REWRITE)
    async def test_discovery_quota_tracked(self, async_client, auth_headers):
        ...


@pytest.mark.integration
class TestPaperDiscoverySources:
    @pytest.mark.skip(reason=_DISCOVERY_REWRITE)
    @pytest.mark.parametrize("source", ["arxiv", "pubmed", "semantic_scholar"])
    async def test_search_by_source(self, async_client, auth_headers, source):
        ...
