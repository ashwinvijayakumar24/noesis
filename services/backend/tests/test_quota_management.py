"""
Tests for quota_management.py covering:
- check_quota() for 'document' and 'bib_import' operation types
- Separate pools: hitting PDF quota doesn't affect BibTeX pool (and vice versa)
- increment_quota_usage() with count parameter
- create_default_quota() sets correct plan-aware limits
- get_quota_summary() returns both pools correctly
- QuotaExceededError is raised with proper attributes
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta


def _make_quota(
    *,
    plan_tier="free",
    monthly_document_limit=10,
    current_month_documents=0,
    monthly_bib_refs_limit=10,
    current_month_bib_refs=0,
    monthly_draft_limit=10,
    current_month_drafts=0,
):
    """Factory for quota dicts with sensible defaults."""
    future_reset = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    return {
        "user_id": "user-uuid",
        "plan_tier": plan_tier,
        "monthly_document_limit": monthly_document_limit,
        "current_month_documents": current_month_documents,
        "monthly_bib_refs_limit": monthly_bib_refs_limit,
        "current_month_bib_refs": current_month_bib_refs,
        "monthly_draft_limit": monthly_draft_limit,
        "current_month_drafts": current_month_drafts,
        "quota_reset_date": future_reset,
    }


# ── QuotaExceededError ────────────────────────────────────────────────────────

class TestQuotaExceededError:
    @pytest.mark.unit
    def test_error_attributes(self):
        from app.services.quota_management import QuotaExceededError

        err = QuotaExceededError("exceeded", quota_type="documents", limit=10, current=10)
        assert err.quota_type == "documents"
        assert err.limit == 10
        assert err.current == 10
        assert "exceeded" in str(err)


class TestPlanLimits:
    @pytest.mark.unit
    def test_get_plan_limits_aligns_task_08_values(self):
        from app.services.quota_management import get_plan_limits

        assert get_plan_limits("free") == {
            "monthly_document_limit": 30,
            "monthly_draft_limit": 2,
            "monthly_bib_refs_limit": 30,
        }
        assert get_plan_limits("pro") == {
            "monthly_document_limit": 100,
            "monthly_draft_limit": 20,
            "monthly_bib_refs_limit": 100,
        }
        assert get_plan_limits("team") == {
            "monthly_document_limit": 9999,
            "monthly_draft_limit": 9999,
            "monthly_bib_refs_limit": 9999,
        }


# ── check_quota — document ────────────────────────────────────────────────────

class TestCheckQuotaDocument:
    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_document_within_limit_returns_true(self, mock_supabase):
        from app.services.quota_management import check_quota

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [_make_quota(current_month_documents=4)]

        result = await check_quota("user-uuid", "document")
        assert result is True

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_document_at_limit_raises(self, mock_supabase):
        from app.services.quota_management import check_quota, QuotaExceededError

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [
                _make_quota(current_month_documents=10, monthly_document_limit=10)
            ]

        with pytest.raises(QuotaExceededError) as exc_info:
            await check_quota("user-uuid", "document")

        err = exc_info.value
        assert err.quota_type == "documents"
        assert err.limit == 10
        assert err.current == 10

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_document_quota_does_not_affect_bib_pool(self, mock_supabase):
        """Hitting PDF quota does not raise when checking bib_import."""
        from app.services.quota_management import check_quota

        # PDF quota maxed out, but bib refs still have capacity
        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [
                _make_quota(
                    current_month_documents=10,
                    monthly_document_limit=10,
                    current_month_bib_refs=0,
                    monthly_bib_refs_limit=10,
                )
            ]

        # Should NOT raise for bib_import
        result = await check_quota("user-uuid", "bib_import")
        assert result is True


# ── check_quota — bib_import ──────────────────────────────────────────────────

class TestCheckQuotaBibImport:
    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_bib_import_within_limit_returns_true(self, mock_supabase):
        from app.services.quota_management import check_quota

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [_make_quota(current_month_bib_refs=3)]

        result = await check_quota("user-uuid", "bib_import")
        assert result is True

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_bib_import_at_limit_raises(self, mock_supabase):
        from app.services.quota_management import check_quota, QuotaExceededError

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [
                _make_quota(current_month_bib_refs=10, monthly_bib_refs_limit=10)
            ]

        with pytest.raises(QuotaExceededError) as exc_info:
            await check_quota("user-uuid", "bib_import")

        err = exc_info.value
        assert err.quota_type == "bib_refs"
        assert err.limit == 10
        assert err.current == 10

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_bib_quota_does_not_affect_pdf_pool(self, mock_supabase):
        """Hitting BibTeX quota does not raise when checking document uploads."""
        from app.services.quota_management import check_quota

        # Bib refs maxed, PDFs still have capacity
        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [
                _make_quota(
                    current_month_bib_refs=10,
                    monthly_bib_refs_limit=10,
                    current_month_documents=0,
                    monthly_document_limit=10,
                )
            ]

        result = await check_quota("user-uuid", "document")
        assert result is True

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_eleventh_bib_import_rejected(self, mock_supabase):
        """The 11th BibTeX entry (10 already used) is rejected."""
        from app.services.quota_management import check_quota, QuotaExceededError

        mock_supabase.table.return_value.select.return_value.eq.return_value \
            .execute.return_value.data = [
                _make_quota(current_month_bib_refs=10, monthly_bib_refs_limit=10)
            ]

        with pytest.raises(QuotaExceededError):
            await check_quota("user-uuid", "bib_import")


# ── increment_quota_usage ─────────────────────────────────────────────────────

class TestIncrementQuotaUsage:
    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_document_increments_correct_field(self, mock_supabase):
        from app.services.quota_management import increment_quota_usage

        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock()
        mock_supabase.rpc.return_value = rpc_mock

        await increment_quota_usage("user-uuid", "document")

        mock_supabase.rpc.assert_called_once_with(
            "increment_quota_field",
            {"user_id_param": "user-uuid", "field_name": "current_month_documents"},
        )

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_bib_import_increments_correct_field(self, mock_supabase):
        from app.services.quota_management import increment_quota_usage

        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock()
        mock_supabase.rpc.return_value = rpc_mock

        await increment_quota_usage("user-uuid", "bib_import")

        mock_supabase.rpc.assert_called_once_with(
            "increment_quota_field",
            {"user_id_param": "user-uuid", "field_name": "current_month_bib_refs"},
        )

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_count_parameter_increments_multiple_times(self, mock_supabase):
        """count=5 should trigger 5 RPC calls."""
        from app.services.quota_management import increment_quota_usage

        rpc_mock = MagicMock()
        rpc_mock.execute.return_value = MagicMock()
        mock_supabase.rpc.return_value = rpc_mock

        await increment_quota_usage("user-uuid", "bib_import", count=5)

        assert mock_supabase.rpc.call_count == 5

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    async def test_unknown_operation_type_is_noop(self, mock_supabase):
        """Unknown operation types are silently ignored."""
        from app.services.quota_management import increment_quota_usage

        await increment_quota_usage("user-uuid", "invalid_op")

        mock_supabase.rpc.assert_not_called()


# ── create_default_quota ──────────────────────────────────────────────────────

class TestCreateDefaultQuota:
    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    @patch("app.services.quota_management._get_user_plan_tier", return_value="free")
    @patch("app.services.quota_management.sync_user_quota_plan")
    async def test_creates_with_correct_free_limits(self, mock_sync, mock_plan_tier, mock_supabase):
        from app.services.quota_management import create_default_quota

        await create_default_quota("user-uuid")

        mock_sync.assert_called_once_with("user-uuid", "free")

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    @patch("app.services.quota_management._get_user_plan_tier", return_value="pro")
    @patch("app.services.quota_management.sync_user_quota_plan")
    async def test_creates_with_correct_paid_limits(self, mock_sync, mock_plan_tier, mock_supabase):
        from app.services.quota_management import create_default_quota

        await create_default_quota("user-uuid")

        mock_sync.assert_called_once_with("user-uuid", "pro")


class TestSyncUserQuotaPlan:
    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    @patch("app.services.quota_management._get_user_quota_row")
    def test_updates_existing_quota_without_resetting_usage(self, mock_get_quota_row, mock_supabase):
        from app.services.quota_management import sync_user_quota_plan

        mock_get_quota_row.side_effect = [
            _make_quota(plan_tier="free", current_month_documents=12, current_month_bib_refs=5),
            _make_quota(plan_tier="pro", monthly_document_limit=100, monthly_bib_refs_limit=100, monthly_draft_limit=20),
        ]
        mock_supabase.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

        result = sync_user_quota_plan("user-uuid", "pro")

        update_payload = mock_supabase.table.return_value.update.call_args[0][0]
        assert update_payload["plan_tier"] == "pro"
        assert update_payload["monthly_document_limit"] == 100
        assert update_payload["monthly_draft_limit"] == 20
        assert update_payload["monthly_bib_refs_limit"] == 100
        assert result["plan_tier"] == "pro"

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    @patch("app.services.quota_management._get_user_quota_row")
    def test_inserts_missing_quota_using_plan_limits(self, mock_get_quota_row, mock_supabase):
        from app.services.quota_management import sync_user_quota_plan

        mock_get_quota_row.side_effect = [
            None,
            _make_quota(plan_tier="team", monthly_document_limit=9999, monthly_bib_refs_limit=9999, monthly_draft_limit=9999),
        ]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock()

        result = sync_user_quota_plan("user-uuid", "team")

        insert_payload = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_payload["user_id"] == "user-uuid"
        assert insert_payload["plan_tier"] == "team"
        assert insert_payload["monthly_document_limit"] == 9999
        assert insert_payload["monthly_draft_limit"] == 9999
        assert insert_payload["monthly_bib_refs_limit"] == 9999
        assert insert_payload["current_month_bib_refs"] == 0
        assert result["plan_tier"] == "team"


# ── get_quota_summary ─────────────────────────────────────────────────────────

class TestGetQuotaSummary:
    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    @patch("app.services.quota_management.ensure_user_quota")
    async def test_returns_both_pools(self, mock_ensure_quota, mock_supabase):
        from app.services.quota_management import get_quota_summary

        mock_ensure_quota.return_value = _make_quota(
            current_month_documents=3,
            monthly_document_limit=10,
            current_month_bib_refs=7,
            monthly_bib_refs_limit=10,
            plan_tier="free",
        )
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(count=2)

        result = await get_quota_summary("user-uuid")

        assert result["pdfs"]["used"] == 3
        assert result["pdfs"]["limit"] == 10
        assert result["bib_refs"]["used"] == 7
        assert result["bib_refs"]["limit"] == 10
        assert result["plan_tier"] == "free"

    @pytest.mark.unit
    @patch("app.services.quota_management.supabase")
    @patch("app.services.quota_management.ensure_user_quota")
    async def test_creates_quota_if_missing(self, mock_ensure_quota, mock_supabase):
        """If no quota row exists, ensure_user_quota creates one and returns summary."""
        from app.services.quota_management import get_quota_summary

        mock_ensure_quota.return_value = _make_quota()
        mock_supabase.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(count=0)

        result = await get_quota_summary("user-uuid")

        mock_ensure_quota.assert_called_once_with("user-uuid")
        assert "pdfs" in result
        assert "bib_refs" in result
        assert "projects" in result
