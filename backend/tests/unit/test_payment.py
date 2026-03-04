"""
Testes unitários — Pagamento
Todos os testes mockam os SDKs do Stripe e Mercado Pago.
Sem chamadas reais a APIs externas.
"""
import hashlib
import hmac
import os
import time
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_fake")
os.environ.setdefault("MP_ACCESS_TOKEN", "APP_USR_fake")
os.environ.setdefault("MP_WEBHOOK_SECRET", "mp_webhook_secret_fake")


class TestStripeWebhookValidation:
    def test_valid_signature_accepted(self):
        from services.payment import validate_stripe_webhook
        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.return_value = {"type": "invoice.paid", "id": "evt_1"}
            event = validate_stripe_webhook(b'{"id":"evt_1"}', "t=123,v1=abc")
            assert event["type"] == "invoice.paid"

    def test_invalid_signature_raises(self):
        from services.payment import validate_stripe_webhook
        import stripe
        with patch("stripe.Webhook.construct_event") as mock_construct:
            mock_construct.side_effect = stripe.error.SignatureVerificationError(
                "Invalid", "sig"
            )
            with pytest.raises(ValueError, match="inválida"):
                validate_stripe_webhook(b"payload", "bad-sig")


class TestStripeCustomer:
    def test_create_customer_returns_id(self):
        from services.payment import create_stripe_customer
        with patch("stripe.Customer.create") as mock_create:
            mock_create.return_value = MagicMock(id="cus_test123")
            customer_id = create_stripe_customer("user@test.com", "User Test")
            assert customer_id == "cus_test123"
            mock_create.assert_called_once_with(email="user@test.com", name="User Test")


class TestStripeSubscription:
    def test_create_subscription_returns_dict(self):
        from services.payment import create_stripe_subscription
        mock_intent = MagicMock(client_secret="pi_secret_123")
        mock_invoice = MagicMock(payment_intent=mock_intent)
        mock_sub = MagicMock(id="sub_abc", status="incomplete", latest_invoice=mock_invoice)
        with patch("stripe.Subscription.create", return_value=mock_sub):
            result = create_stripe_subscription("cus_123", "price_xyz")
            assert result["subscription_id"] == "sub_abc"
            assert result["status"] == "incomplete"
            assert result["client_secret"] == "pi_secret_123"

    def test_create_subscription_with_trial(self):
        from services.payment import create_stripe_subscription
        mock_sub = MagicMock(id="sub_trial", status="trialing", latest_invoice=None)
        with patch("stripe.Subscription.create", return_value=mock_sub) as mock_create:
            create_stripe_subscription("cus_123", "price_xyz", trial_days=14)
            call_kwargs = mock_create.call_args[1]
            assert call_kwargs["trial_period_days"] == 14


class TestMpPixCreation:
    def test_create_pix_returns_qr_code(self):
        from services.payment import create_mp_pix
        mock_response = {
            "id": 123456,
            "status": "pending",
            "point_of_interaction": {
                "transaction_data": {
                    "qr_code": "00020101...",
                    "qr_code_base64": "iVBORw0KGgo=",
                }
            },
        }
        with patch("mercadopago.SDK") as mock_sdk:
            mock_sdk.return_value.payment.return_value.create.return_value = {
                "status": 201,
                "response": mock_response,
            }
            result = create_mp_pix("user@test.com", 97.90, "Assinatura mensal", "order-001")
            assert result["qr_code"] == "00020101..."
            assert result["payment_id"] == 123456

    def test_mp_error_raises(self):
        from services.payment import create_mp_pix
        with patch("mercadopago.SDK") as mock_sdk:
            mock_sdk.return_value.payment.return_value.create.return_value = {
                "status": 400,
                "response": {"message": "Bad request"},
            }
            with pytest.raises(RuntimeError, match="Erro MP"):
                create_mp_pix("bad@test.com", 0, "fail", "order-fail")
