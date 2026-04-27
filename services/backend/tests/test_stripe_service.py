import pytest
from unittest.mock import MagicMock, patch


class TestStripeQuotaSync:
    @pytest.mark.unit
    def test_team_plan_config_uses_current_team_copy(self):
        from app.services.stripe_service import PLAN_CONFIGS

        features = PLAN_CONFIGS["team"]["features"]

        assert "Effectively unlimited usage" in features
        assert "Shared literature libraries" in features
        assert "Lab member invite link" not in features

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_checkout_completed_upserts_subscription_and_syncs_quota(
        self,
        mock_get_supabase_client,
        mock_sync_user_quota_plan,
    ):
        from app.services.stripe_service import handle_checkout_completed

        supabase = MagicMock()
        mock_get_supabase_client.return_value = supabase
        supabase.table.return_value.upsert.return_value.execute.return_value = MagicMock()

        handle_checkout_completed({
            "metadata": {"user_id": "user-1", "plan_tier": "pro"},
            "subscription": "sub_123",
            "customer": "cus_123",
        })

        upsert_payload = supabase.table.return_value.upsert.call_args[0][0]
        assert upsert_payload["user_id"] == "user-1"
        assert upsert_payload["plan_tier"] == "pro"
        assert upsert_payload["stripe_subscription_id"] == "sub_123"
        mock_sync_user_quota_plan.assert_called_once_with("user-1", "pro")

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_subscription_updated_keeps_paid_quota_for_active_status(
        self,
        mock_get_supabase_client,
        mock_sync_user_quota_plan,
    ):
        from app.services.stripe_service import handle_subscription_updated

        supabase = MagicMock()
        mock_get_supabase_client.return_value = supabase
        subscriptions_table = supabase.table.return_value
        subscriptions_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "user-1", "plan_tier": "free"}]
        )
        subscriptions_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

        handle_subscription_updated({
            "id": "sub_123",
            "status": "active",
            "current_period_start": 1713744000,
            "current_period_end": 1716336000,
            "metadata": {"plan_tier": "team"},
            "cancel_at_period_end": False,
        })

        update_payload = subscriptions_table.update.call_args[0][0]
        assert update_payload["plan_tier"] == "team"
        assert update_payload["status"] == "active"
        mock_sync_user_quota_plan.assert_called_once_with("user-1", "team")

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_subscription_updated_downgrades_quota_for_inactive_status(
        self,
        mock_get_supabase_client,
        mock_sync_user_quota_plan,
    ):
        from app.services.stripe_service import handle_subscription_updated

        supabase = MagicMock()
        mock_get_supabase_client.return_value = supabase
        subscriptions_table = supabase.table.return_value
        subscriptions_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "user-1", "plan_tier": "pro"}]
        )
        subscriptions_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

        handle_subscription_updated({
            "id": "sub_123",
            "status": "incomplete",
            "current_period_start": 1713744000,
            "current_period_end": 1716336000,
            "metadata": {"plan_tier": "pro"},
            "cancel_at_period_end": False,
        })

        mock_sync_user_quota_plan.assert_called_once_with("user-1", "free")

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_subscription_deleted_downgrades_quota_to_free(
        self,
        mock_get_supabase_client,
        mock_sync_user_quota_plan,
    ):
        from app.services.stripe_service import handle_subscription_deleted

        supabase = MagicMock()
        mock_get_supabase_client.return_value = supabase
        subscriptions_table = supabase.table.return_value
        subscriptions_table.select.return_value.eq.return_value.execute.return_value = MagicMock(
            data=[{"user_id": "user-1"}]
        )
        subscriptions_table.update.return_value.eq.return_value.execute.return_value = MagicMock()

        handle_subscription_deleted({"id": "sub_123"})

        update_payload = subscriptions_table.update.call_args[0][0]
        assert update_payload["plan_tier"] == "free"
        assert update_payload["status"] == "canceled"
        mock_sync_user_quota_plan.assert_called_once_with("user-1", "free")

    @pytest.mark.unit
    @patch("app.services.stripe_service.ensure_user_quota")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_get_usage_limits_reads_user_quotas(
        self,
        mock_get_supabase_client,
        mock_ensure_user_quota,
    ):
        from app.services.stripe_service import get_usage_limits

        mock_get_supabase_client.return_value = MagicMock()
        mock_ensure_user_quota.return_value = {
            "plan_tier": "pro",
            "current_month_documents": 12,
            "monthly_document_limit": 100,
            "current_month_bib_refs": 25,
            "monthly_bib_refs_limit": 100,
            "current_month_drafts": 7,
            "monthly_draft_limit": 20,
            "quota_reset_date": "2026-05-01T00:00:00+00:00",
        }

        usage = get_usage_limits("user-1")

        assert usage["plan_tier"] == "pro"
        assert usage["documents_uploaded"] == 12
        assert usage["documents_limit"] == 100
        assert usage["bib_refs_imported"] == 25
        assert usage["bib_refs_limit"] == 100
        assert usage["drafts_analyzed"] == 7
        assert usage["drafts_limit"] == 20
        assert usage["can_upload_document"] is True
        assert usage["can_import_bib"] is True
