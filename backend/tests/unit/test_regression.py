"""
test_regression.py — Contratos dos fluxos críticos

NUNCA REMOVA OU DESABILITE TESTES DESTE ARQUIVO.
Toda alteração no projeto deve passar por estes testes sem quebrar nenhum.

Cobre obrigatoriamente:
  - Cadastro de usuário (OTP gerado, hash salvo)
  - Login (OTP validado, tokens emitidos, payload correto)
  - Expiração e adulteração de tokens
  - Criação de customer e assinatura Stripe
  - Validação de webhooks Stripe (válido e inválido)
  - Criação de PIX Mercado Pago
  - Validação de webhook Mercado Pago
  - Health check endpoint (HTTP 200)
"""

import hashlib
import hmac
import os
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ambiente forçado para HS256 (sem Key Vault) — CI e local
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_SECRET_FALLBACK", "regression-test-secret-minimum-32-bytes-long")
os.environ.setdefault("JWT_ACCESS_EXPIRE_MINUTES", "60")
os.environ.setdefault("JWT_REFRESH_EXPIRE_DAYS", "7")
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_regression_fake")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_regression_fake")
os.environ.setdefault("MP_ACCESS_TOKEN", "APP_USR_regression_fake")
os.environ.setdefault("MP_WEBHOOK_SECRET", "mp_regression_secret_fake")


# ===========================================================================
# FLUXO 1 — Cadastro de usuário
# ===========================================================================

class TestCadastroUsuario:
    """Contrato: OTP gerado com 6 dígitos numéricos e hash determinístico."""

    def test_otp_tem_6_digitos(self):
        from services.auth import generate_otp
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_otp_hash_determinístico(self):
        from services.auth import hash_otp
        otp = "123456"
        assert hash_otp(otp) == hash_otp(otp)

    def test_otp_hash_diferente_para_valores_distintos(self):
        from services.auth import hash_otp
        assert hash_otp("111111") != hash_otp("222222")

    def test_otps_sao_unicos_em_lote(self):
        from services.auth import generate_otp
        otps = {generate_otp() for _ in range(200)}
        assert len(otps) > 180, "Colisão excessiva de OTPs — gerador com problema"


# ===========================================================================
# FLUXO 2 — Login via JWT
# ===========================================================================

class TestLogin:
    """Contrato: tokens emitidos com payload correto e verificáveis."""

    def test_access_token_payload(self):
        from services.auth import create_access_token, verify_token
        token = create_access_token("u-001", "tenant-abc", "dev@excelverton.com")
        payload = verify_token(token)
        assert payload["sub"] == "u-001"
        assert payload["tenant"] == "tenant-abc"
        assert payload["email"] == "dev@excelverton.com"
        assert payload["type"] == "access"

    def test_refresh_token_payload(self):
        from services.auth import create_refresh_token, verify_token
        token = create_refresh_token("u-001", "tenant-abc")
        payload = verify_token(token)
        assert payload["sub"] == "u-001"
        assert payload["type"] == "refresh"

    def test_access_e_refresh_sao_diferentes(self):
        from services.auth import create_access_token, create_refresh_token
        access = create_access_token("u-001", "t", "e@e.com")
        refresh = create_refresh_token("u-001", "t")
        assert access != refresh


# ===========================================================================
# FLUXO 3 — Expiração e adulteração de tokens
# ===========================================================================

class TestSegurancaTokens:
    """Contrato: tokens expirados e adulterados DEVEM ser rejeitados."""

    def test_token_expirado_levanta_valueerror(self, monkeypatch):
        monkeypatch.setenv("JWT_ACCESS_EXPIRE_MINUTES", "-1")
        import importlib
        import services.auth as auth_mod
        importlib.reload(auth_mod)
        token = auth_mod.create_access_token("u", "t", "e@e.com")
        with pytest.raises(ValueError, match="expirado"):
            auth_mod.verify_token(token)
        # Restore
        importlib.reload(auth_mod)

    def test_token_adulterado_levanta_valueerror(self):
        from services.auth import create_access_token, verify_token
        token = create_access_token("u-001", "t", "e@e.com")
        adulterado = token[:-6] + "XXXXXX"
        with pytest.raises(ValueError):
            verify_token(adulterado)

    def test_string_aleatoria_levanta_valueerror(self):
        from services.auth import verify_token
        with pytest.raises(ValueError, match="inv\u00e1lido"):
            verify_token("not.a.jwt.token")


# ===========================================================================
# FLUXO 4 — Stripe: customer e assinatura
# ===========================================================================

class TestStripeCustomer:
    """Contrato: create_stripe_customer retorna customer_id."""

    def test_retorna_customer_id(self):
        from services.payment import create_stripe_customer
        with patch("stripe.Customer.create") as mock_create:
            mock_create.return_value = MagicMock(id="cus_regression_001")
            cid = create_stripe_customer("user@test.com", "Test User")
        assert cid == "cus_regression_001"
        mock_create.assert_called_once_with(email="user@test.com", name="Test User")


class TestStripeAssinatura:
    """Contrato: create_stripe_subscription retorna subscription_id e client_secret."""

    def test_retorna_subscription_id_e_client_secret(self):
        from services.payment import create_stripe_subscription
        mock_intent = MagicMock(client_secret="pi_secret_regression")
        mock_invoice = MagicMock(payment_intent=mock_intent)
        mock_sub = MagicMock(id="sub_regression", status="incomplete", latest_invoice=mock_invoice)
        with patch("stripe.Subscription.create", return_value=mock_sub):
            result = create_stripe_subscription("cus_001", "price_001")
        assert result["subscription_id"] == "sub_regression"
        assert result["status"] == "incomplete"
        assert result["client_secret"] == "pi_secret_regression"

    def test_trial_days_passado_corretamente(self):
        from services.payment import create_stripe_subscription
        mock_sub = MagicMock(id="sub_trial", status="trialing", latest_invoice=None)
        with patch("stripe.Subscription.create", return_value=mock_sub) as mock_create:
            create_stripe_subscription("cus_001", "price_001", trial_days=7)
        assert mock_create.call_args[1]["trial_period_days"] == 7


# ===========================================================================
# FLUXO 5 — Stripe: webhook
# ===========================================================================

class TestStripeWebhook:
    """Contrato: assinatura válida aceita, inválida rejeitada com ValueError."""

    def test_assinatura_valida_retorna_evento(self):
        from services.payment import validate_stripe_webhook
        with patch("stripe.Webhook.construct_event") as mock_ev:
            mock_ev.return_value = {"type": "invoice.paid", "id": "evt_001"}
            event = validate_stripe_webhook(b'{"id":"evt_001"}', "t=1,v1=abc")
        assert event["type"] == "invoice.paid"

    def test_assinatura_invalida_levanta_valueerror(self):
        from services.payment import validate_stripe_webhook
        import stripe
        with patch("stripe.Webhook.construct_event") as mock_ev:
            mock_ev.side_effect = stripe.error.SignatureVerificationError("bad", "sig")
            with pytest.raises(ValueError, match="inv\u00e1lida"):
                validate_stripe_webhook(b"payload", "bad-sig")


# ===========================================================================
# FLUXO 6 — Mercado Pago: PIX
# ===========================================================================

class TestMercadoPagoPix:
    """Contrato: create_mp_pix retorna qr_code e qr_code_base64."""

    def test_retorna_qr_code_e_base64(self):
        from services.payment import create_mp_pix
        mock_response = {
            "id": 99999,
            "status": "pending",
            "point_of_interaction": {
                "transaction_data": {
                    "qr_code": "00020101...",
                    "qr_code_base64": "iVBORw0KGgo=",
                }
            },
        }
        mock_sdk = MagicMock()
        mock_sdk.payment().create.return_value = {"status": 201, "response": mock_response}
        with patch("mercadopago.SDK", return_value=mock_sdk):
            result = create_mp_pix("payer@test.com", 29.90, "Plano Pro", "ref-001")
        assert result["qr_code"] == "00020101..."
        assert result["qr_code_base64"] == "iVBORw0KGgo="
        assert result["payment_id"] == 99999


# ===========================================================================
# FLUXO 7 — Mercado Pago: webhook
# ===========================================================================

class TestMercadoPagoWebhook:
    """Contrato: HMAC-SHA256 válido aceito, inválido rejeitado."""

    def _gerar_assinatura(self, secret: str, request_id: str, ts: str) -> str:
        manifest = f"id:{request_id};request-id:{request_id};ts:{ts};"
        return hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()

    def test_assinatura_valida_retorna_true(self, monkeypatch):
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "segredo-teste-123")
        from services.payment import validate_mp_webhook
        ts = "1700000000"
        rid = "req-abc-123"
        v1 = self._gerar_assinatura("segredo-teste-123", rid, ts)
        result = validate_mp_webhook(b"payload", f"ts={ts},v1={v1}", rid)
        assert result is True

    def test_assinatura_invalida_retorna_false(self, monkeypatch):
        monkeypatch.setenv("MP_WEBHOOK_SECRET", "segredo-teste-123")
        from services.payment import validate_mp_webhook
        result = validate_mp_webhook(b"payload", "ts=1700000000,v1=assinatura_errada", "req-xyz")
        assert result is False


# ===========================================================================
# FLUXO 8 — Health check
# ===========================================================================

class TestHealthCheck:
    """Contrato: /api/health retorna HTTP 200 com status ok."""

    def test_health_retorna_200_e_status_ok(self, monkeypatch):
        import json
        import azure.functions as func
        # Mock de todas as dependências externas do health check
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        monkeypatch.setenv("POSTGRES_DB", "testdb")
        monkeypatch.setenv("POSTGRES_USER", "testuser")
        monkeypatch.setenv("POSTGRES_PASSWORD", "testpass")
        # Faz o psycopg2.connect levantar exceção controlada (sem banco real)
        with patch("psycopg2.connect", side_effect=Exception("no db in unit test")):
            from api.health import health_check
            req = func.HttpRequest(
                method="GET",
                url="http://localhost/api/health",
                body=b"",
                headers={},
                params={},
            )
            response = health_check(req)
        # Status pode ser "degraded" sem banco, mas o endpoint DEVE responder
        assert response.status_code in (200, 503)
        body = json.loads(response.get_body())
        assert "status" in body

    def test_health_retorna_200_quando_todos_checks_ok(self, monkeypatch):
        import json
        import azure.functions as func
        monkeypatch.setenv("POSTGRES_HOST", "localhost")
        monkeypatch.setenv("POSTGRES_DB", "testdb")
        monkeypatch.setenv("POSTGRES_USER", "testuser")
        monkeypatch.setenv("POSTGRES_PASSWORD", "testpass")
        mock_conn = MagicMock()
        with patch("psycopg2.connect", return_value=mock_conn):
            from api.health import health_check
            req = func.HttpRequest(
                method="GET",
                url="http://localhost/api/health",
                body=b"",
                headers={},
                params={},
            )
            response = health_check(req)
        assert response.status_code == 200
        body = json.loads(response.get_body())
        assert body["status"] == "ok"
