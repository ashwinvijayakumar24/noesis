"""
tests/test_webhook_hardening.py

Issue #3 – Stripe webhook security hardening.

Covers:
  1. Valid signature accepted (constructs event from Stripe)
  2. Invalid signature raises HTTPException(400)
  3. Missing Stripe-Signature header with a secret raises HTTPException(400)
  4. Missing STRIPE_WEBHOOK_SECRET in non-dev environments raises HTTPException(500)
  5. Missing secret in development allows unsigned JSON parsing
  6. _record_event_or_skip returns True for new events
  7. _record_event_or_skip returns False for duplicates (ON CONFLICT DO NOTHING)
  8. Duplicate event_id returns {"status": "duplicate"} without running handlers
  9. Handler exception still returns {"status": "success"} (event already recorded)
"""

import json
import pytest
from unittest.mock import MagicMock, patch
import stripe as stripe_module


# ---------------------------------------------------------------------------
# _verify_stripe_signature – unit tests
# ---------------------------------------------------------------------------

class TestVerifyStripeSignature:

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.settings")
    @patch("app.api.routes.subscriptions.stripe")
    def test_valid_signature_accepted(self, mock_stripe, mock_settings):
        from app.api.routes.subscriptions import _verify_stripe_signature

        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        expected = {"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {}}}
        mock_stripe.Webhook.construct_event.return_value = expected

        result = _verify_stripe_signature(b'{"id": "evt_1"}', "t=123,v1=abc")

        assert result["id"] == "evt_1"
        mock_stripe.Webhook.construct_event.assert_called_once_with(
            b'{"id": "evt_1"}', "t=123,v1=abc", "whsec_test"
        )

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.settings")
    @patch("app.api.routes.subscriptions.stripe")
    def test_invalid_signature_returns_400(self, mock_stripe, mock_settings):
        from fastapi import HTTPException
        from app.api.routes.subscriptions import _verify_stripe_signature

        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        mock_stripe.Webhook.construct_event.side_effect = (
            stripe_module.error.SignatureVerificationError("bad sig", sig_header="t=1,v1=bad")
        )
        mock_stripe.error.SignatureVerificationError = stripe_module.error.SignatureVerificationError

        with pytest.raises(HTTPException) as exc:
            _verify_stripe_signature(b'{"id": "evt_1"}', "t=1,v1=bad")

        assert exc.value.status_code == 400

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.settings")
    @patch("app.api.routes.subscriptions.stripe")
    def test_missing_signature_header_returns_400(self, mock_stripe, mock_settings):
        from fastapi import HTTPException
        from app.api.routes.subscriptions import _verify_stripe_signature

        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"

        with pytest.raises(HTTPException) as exc:
            _verify_stripe_signature(b'{"id": "evt_1"}', None)

        assert exc.value.status_code == 400

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.settings")
    def test_missing_secret_in_production_returns_500(self, mock_settings):
        from fastapi import HTTPException
        from app.api.routes.subscriptions import _verify_stripe_signature

        mock_settings.STRIPE_WEBHOOK_SECRET = None
        mock_settings.ENVIRONMENT = "production"

        with pytest.raises(HTTPException) as exc:
            _verify_stripe_signature(b'{"id": "evt_1"}', "t=1,v1=abc")

        assert exc.value.status_code == 500

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.settings")
    def test_missing_secret_in_staging_returns_500(self, mock_settings):
        from fastapi import HTTPException
        from app.api.routes.subscriptions import _verify_stripe_signature

        mock_settings.STRIPE_WEBHOOK_SECRET = None
        mock_settings.ENVIRONMENT = "staging"

        with pytest.raises(HTTPException) as exc:
            _verify_stripe_signature(b'{"id": "evt_1"}', None)

        assert exc.value.status_code == 500

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.settings")
    def test_missing_secret_in_development_allows_unsigned(self, mock_settings):
        from app.api.routes.subscriptions import _verify_stripe_signature

        mock_settings.STRIPE_WEBHOOK_SECRET = None
        mock_settings.ENVIRONMENT = "development"

        payload = json.dumps({"id": "evt_dev", "type": "checkout.session.completed"}).encode()
        result = _verify_stripe_signature(payload, None)

        assert result["id"] == "evt_dev"


# ---------------------------------------------------------------------------
# _record_event_or_skip – unit tests
# ---------------------------------------------------------------------------

class TestRecordEventOrSkip:

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.get_supabase_client")
    def test_new_event_returns_true(self, mock_get_db):
        from app.api.routes.subscriptions import _record_event_or_skip

        db = MagicMock()
        mock_get_db.return_value = db
        db.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"event_id": "evt_new", "type": "checkout.session.completed"}]
        )

        result = _record_event_or_skip("evt_new", "checkout.session.completed")

        assert result is True

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.get_supabase_client")
    def test_duplicate_event_returns_false(self, mock_get_db):
        from app.api.routes.subscriptions import _record_event_or_skip

        db = MagicMock()
        mock_get_db.return_value = db
        # Supabase returns empty data list when ON CONFLICT DO NOTHING fires.
        db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

        result = _record_event_or_skip("evt_dup", "checkout.session.completed")

        assert result is False


# ---------------------------------------------------------------------------
# Webhook endpoint – integration tests via TestClient
# ---------------------------------------------------------------------------

class TestWebhookEndpoint:
    """Full-stack tests that exercise the POST /webhooks/stripe route."""

    @staticmethod
    def _build_client():
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.routes.subscriptions import router

        app = FastAPI()
        app.include_router(router, prefix="/api")
        return TestClient(app)

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.handle_checkout_completed")
    @patch("app.api.routes.subscriptions._record_event_or_skip")
    @patch("app.api.routes.subscriptions._verify_stripe_signature")
    def test_duplicate_event_returns_duplicate_without_calling_handler(
        self, mock_verify, mock_record, mock_handler
    ):
        client = self._build_client()

        event = {
            "id": "evt_dup",
            "type": "checkout.session.completed",
            "data": {"object": {}},
        }
        mock_verify.return_value = event
        mock_record.return_value = False  # already processed

        response = client.post(
            "/api/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=abc"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "duplicate"
        assert body["event_id"] == "evt_dup"
        mock_handler.assert_not_called()

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions.handle_checkout_completed")
    @patch("app.api.routes.subscriptions._record_event_or_skip")
    @patch("app.api.routes.subscriptions._verify_stripe_signature")
    def test_handler_exception_still_returns_200(
        self, mock_verify, mock_record, mock_handler
    ):
        client = self._build_client()

        event = {
            "id": "evt_exc",
            "type": "checkout.session.completed",
            "data": {"object": {}},
        }
        mock_verify.return_value = event
        mock_record.return_value = True  # new event – process it
        mock_handler.side_effect = RuntimeError("handler exploded")

        response = client.post(
            "/api/webhooks/stripe",
            content=b'{}',
            headers={"Stripe-Signature": "t=1,v1=abc"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions._record_event_or_skip")
    @patch("app.api.routes.subscriptions.stripe")
    @patch("app.api.routes.subscriptions.settings")
    def test_invalid_signature_returns_400_via_endpoint(
        self, mock_settings, mock_stripe, mock_record
    ):
        client = self._build_client()

        mock_settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
        mock_stripe.Webhook.construct_event.side_effect = (
            stripe_module.error.SignatureVerificationError("bad sig", sig_header="t=1,v1=bad")
        )
        mock_stripe.error.SignatureVerificationError = (
            stripe_module.error.SignatureVerificationError
        )

        response = client.post(
            "/api/webhooks/stripe",
            content=b'{"id": "evt_1"}',
            headers={"Stripe-Signature": "t=1,v1=bad"},
        )

        assert response.status_code == 400
        mock_record.assert_not_called()

    @pytest.mark.unit
    @patch("app.api.routes.subscriptions._record_event_or_skip")
    @patch("app.api.routes.subscriptions.settings")
    def test_missing_secret_in_production_returns_500_via_endpoint(
        self, mock_settings, mock_record
    ):
        client = self._build_client()

        mock_settings.STRIPE_WEBHOOK_SECRET = None
        mock_settings.ENVIRONMENT = "production"

        response = client.post(
            "/api/webhooks/stripe",
            content=b'{"id": "evt_1"}',
            headers={"Stripe-Signature": "t=1,v1=abc"},
        )

        assert response.status_code == 500
        mock_record.assert_not_called()
