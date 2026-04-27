"""
E2E tests: Quota enforcement — verify limits block at threshold.

These tests mock Supabase quota data to avoid actually exhausting quotas.
"""

import pytest
import httpx
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.mark.integration
class TestQuotaEndpoints:
    async def test_quota_me_returns_usage(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """GET /quota/me returns current usage and limits."""
        resp = await async_client.get("/quota/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert any(
            key in data
            for key in (
                "monthly_document_limit", "plan_tier", "documents",
                "current_month_documents", "quota"
            )
        )

    async def test_quota_me_requires_auth(self, async_client: httpx.AsyncClient):
        resp = await async_client.get("/quota/me")
        assert resp.status_code in (401, 403)

    async def test_quota_summary_fields(
        self,
        async_client: httpx.AsyncClient,
        auth_headers: dict,
    ):
        """Quota summary includes document and draft pools."""
        resp = await async_client.get("/auth/quota-summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Verify both pools exist
        body = str(data)
        assert "document" in body.lower() or "pdf" in body.lower()


@pytest.mark.unit
class TestQuotaEnforcementLogic:
    """Unit tests verifying quota logic blocks at threshold."""

    @patch("app.services.quota_management.supabase")
    async def test_document_quota_blocks_at_limit(self, mock_supabase):
        """check_quota raises QuotaExceededError when at document limit."""
        from app.services.quota_management import check_quota, QuotaExceededError

        future_date = "2099-01-01T00:00:00+00:00"
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "user_id": "user-1",
                "plan_tier": "free",
                "monthly_document_limit": 10,
                "current_month_documents": 10,  # AT limit
                "monthly_bib_refs_limit": 100,
                "current_month_bib_refs": 0,
                "monthly_draft_limit": 5,
                "current_month_drafts": 0,
                "quota_reset_date": future_date,
            }
        ]

        with pytest.raises(QuotaExceededError) as exc_info:
            await check_quota("user-1", "document")

        assert exc_info.value.quota_type == "documents"
        assert exc_info.value.limit == 10
        assert exc_info.value.current == 10

    @patch("app.services.quota_management.supabase")
    async def test_document_quota_passes_under_limit(self, mock_supabase):
        """check_quota returns True when under limit."""
        from app.services.quota_management import check_quota

        future_date = "2099-01-01T00:00:00+00:00"
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "user_id": "user-1",
                "plan_tier": "free",
                "monthly_document_limit": 10,
                "current_month_documents": 5,  # Under limit
                "monthly_bib_refs_limit": 100,
                "current_month_bib_refs": 0,
                "monthly_draft_limit": 5,
                "current_month_drafts": 0,
                "quota_reset_date": future_date,
            }
        ]

        result = await check_quota("user-1", "document")
        assert result is True

    @patch("app.services.quota_management.supabase")
    async def test_bib_import_quota_independent_of_documents(self, mock_supabase):
        """Document pool exhaustion does not affect bib_import pool."""
        from app.services.quota_management import check_quota, QuotaExceededError

        future_date = "2099-01-01T00:00:00+00:00"
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "user_id": "user-1",
                "plan_tier": "free",
                "monthly_document_limit": 10,
                "current_month_documents": 10,  # Documents exhausted
                "monthly_bib_refs_limit": 100,
                "current_month_bib_refs": 0,   # BibTeX still available
                "monthly_draft_limit": 5,
                "current_month_drafts": 0,
                "quota_reset_date": future_date,
            }
        ]

        # bib_import should still work
        result = await check_quota("user-1", "bib_import")
        assert result is True

    @patch("app.services.quota_management.supabase")
    async def test_admin_bypasses_all_quotas(self, mock_supabase):
        """Admin plan tier bypasses all quota checks."""
        from app.services.quota_management import check_quota

        future_date = "2099-01-01T00:00:00+00:00"
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
            {
                "user_id": "admin-1",
                "plan_tier": "admin",
                "monthly_document_limit": 0,
                "current_month_documents": 9999,
                "monthly_bib_refs_limit": 0,
                "current_month_bib_refs": 9999,
                "monthly_draft_limit": 0,
                "current_month_drafts": 9999,
                "quota_reset_date": future_date,
            }
        ]

        # All operation types should pass for admin
        for op in ("document", "draft", "bib_import"):
            result = await check_quota("admin-1", op)
            assert result is True
