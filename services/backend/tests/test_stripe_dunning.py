"""
tests/test_stripe_dunning.py

Issue #4 – Stripe dunning and seat-change tests.

Covers:
  1. invoice.payment_failed sets status=past_due and records last_payment_failed_at
  2. invoice.payment_failed does NOT downgrade quota (past_due retains paid tier)
  3. invoice.payment_failed with no subscription_id returns early without DB writes
  4. invoice.payment_succeeded clears past_due, sets last_payment_failed_at=None
  5. invoice.payment_succeeded re-syncs quota to current plan tier
  6. handle_subscription_updated persists seat count for team plans
  7. handle_subscription_updated omits seats for pro plans (None per spec)
  8. past_due status retains paid tier in handle_subscription_updated
"""

import pytest
from unittest.mock import MagicMock, patch


def _mock_supabase_with_subscription(mock_get_db, user_id: str, plan_tier: str):
    """
    Configure a MagicMock supabase client so that:
      - select().eq().limit().execute() returns the given subscription row
      - update().eq().execute() is a no-op mock
    """
    db = MagicMock()
    mock_get_db.return_value = db
    tbl = db.table.return_value
    tbl.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"user_id": user_id, "plan_tier": plan_tier}]
    )
    tbl.update.return_value.eq.return_value.execute.return_value = MagicMock()
    return db


# ---------------------------------------------------------------------------
# invoice.payment_failed
# ---------------------------------------------------------------------------

class TestInvoicePaymentFailed:

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_sets_past_due_and_records_last_payment_failed_at(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_invoice_payment_failed

        db = _mock_supabase_with_subscription(mock_get_db, "user-1", "pro")

        handle_invoice_payment_failed({"id": "in_123", "subscription": "sub_123"})

        update_payload = db.table.return_value.update.call_args[0][0]
        assert update_payload["status"] == "past_due"
        assert update_payload["last_payment_failed_at"] is not None

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_does_not_downgrade_quota_on_payment_failed(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_invoice_payment_failed

        _mock_supabase_with_subscription(mock_get_db, "user-1", "pro")

        handle_invoice_payment_failed({"id": "in_123", "subscription": "sub_123"})

        # Quota must stay at "pro" – past_due retains paid access per dunning policy.
        mock_sync_quota.assert_called_once_with("user-1", "pro")

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_no_subscription_id_returns_early(self, mock_get_db, mock_sync_quota):
        from app.services.stripe_service import handle_invoice_payment_failed

        db = MagicMock()
        mock_get_db.return_value = db

        handle_invoice_payment_failed({"id": "in_123"})  # no "subscription" key

        db.table.return_value.update.assert_not_called()
        mock_sync_quota.assert_not_called()

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_team_plan_retains_team_quota_on_failure(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_invoice_payment_failed

        _mock_supabase_with_subscription(mock_get_db, "user-1", "team")

        handle_invoice_payment_failed({"id": "in_456", "subscription": "sub_456"})

        mock_sync_quota.assert_called_once_with("user-1", "team")


# ---------------------------------------------------------------------------
# invoice.payment_succeeded
# ---------------------------------------------------------------------------

class TestInvoicePaymentSucceeded:

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_clears_past_due_and_nulls_last_payment_failed_at(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_invoice_payment_succeeded

        db = _mock_supabase_with_subscription(mock_get_db, "user-1", "pro")

        handle_invoice_payment_succeeded({"id": "in_123", "subscription": "sub_123"})

        update_payload = db.table.return_value.update.call_args[0][0]
        assert update_payload["status"] == "active"
        assert update_payload["last_payment_failed_at"] is None

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_resyncs_quota_to_current_plan_tier(self, mock_get_db, mock_sync_quota):
        from app.services.stripe_service import handle_invoice_payment_succeeded

        _mock_supabase_with_subscription(mock_get_db, "user-1", "team")

        handle_invoice_payment_succeeded({"id": "in_123", "subscription": "sub_123"})

        mock_sync_quota.assert_called_once_with("user-1", "team")

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_no_subscription_id_returns_early(self, mock_get_db, mock_sync_quota):
        from app.services.stripe_service import handle_invoice_payment_succeeded

        db = MagicMock()
        mock_get_db.return_value = db

        handle_invoice_payment_succeeded({"id": "in_123"})  # no "subscription" key

        db.table.return_value.update.assert_not_called()
        mock_sync_quota.assert_not_called()


# ---------------------------------------------------------------------------
# Seat count persistence in handle_subscription_updated
# ---------------------------------------------------------------------------

class TestSeatCount:

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_subscription_updated_persists_seat_count_for_team(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_subscription_updated

        db = _mock_supabase_with_subscription(mock_get_db, "user-1", "team")

        handle_subscription_updated({
            "id": "sub_123",
            "status": "active",
            "metadata": {"plan_tier": "team"},
            "current_period_start": 1713744000,
            "current_period_end": 1716336000,
            "cancel_at_period_end": False,
            "items": {"data": [{"quantity": 3, "price": {"id": "price_team"}}]},
        })

        update_payload = db.table.return_value.update.call_args[0][0]
        assert update_payload.get("seats") == 3

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_subscription_updated_does_not_set_seats_for_pro(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_subscription_updated

        db = _mock_supabase_with_subscription(mock_get_db, "user-1", "pro")

        handle_subscription_updated({
            "id": "sub_123",
            "status": "active",
            "metadata": {"plan_tier": "pro"},
            "current_period_start": 1713744000,
            "current_period_end": 1716336000,
            "cancel_at_period_end": False,
            "items": {"data": [{"quantity": 1, "price": {"id": "price_pro"}}]},
        })

        update_payload = db.table.return_value.update.call_args[0][0]
        assert "seats" not in update_payload

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_past_due_subscription_retains_paid_tier(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_subscription_updated

        _mock_supabase_with_subscription(mock_get_db, "user-1", "pro")

        handle_subscription_updated({
            "id": "sub_123",
            "status": "past_due",
            "metadata": {"plan_tier": "pro"},
            "current_period_start": 1713744000,
            "current_period_end": 1716336000,
            "cancel_at_period_end": False,
        })

        # past_due must keep "pro", not downgrade to "free".
        mock_sync_quota.assert_called_once_with("user-1", "pro")

    @pytest.mark.unit
    @patch("app.services.stripe_service.sync_user_quota_plan")
    @patch("app.services.stripe_service.get_supabase_client")
    def test_inactive_status_downgrades_to_free(
        self, mock_get_db, mock_sync_quota
    ):
        from app.services.stripe_service import handle_subscription_updated

        _mock_supabase_with_subscription(mock_get_db, "user-1", "pro")

        handle_subscription_updated({
            "id": "sub_123",
            "status": "incomplete",
            "metadata": {"plan_tier": "pro"},
            "current_period_start": 1713744000,
            "current_period_end": 1716336000,
            "cancel_at_period_end": False,
        })

        mock_sync_quota.assert_called_once_with("user-1", "free")
