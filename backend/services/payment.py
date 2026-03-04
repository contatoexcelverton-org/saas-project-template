"""
Serviço de pagamento — Stripe (internacional) + Mercado Pago (Brasil/PIX)
Webhooks sempre validados por assinatura antes de processar.
Credenciais sempre via Key Vault em produção.
"""
import hashlib
import hmac
import os
import time
from typing import Literal, Optional


# -- Stripe --

def _stripe_client():
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    return stripe


def create_stripe_customer(email: str, name: str) -> str:
    """Cria cliente no Stripe e retorna o customer_id."""
    stripe = _stripe_client()
    customer = stripe.Customer.create(email=email, name=name)
    return customer.id


def create_stripe_subscription(
    customer_id: str,
    price_id: str,
    trial_days: int = 0,
) -> dict:
    stripe = _stripe_client()
    params = {
        "customer": customer_id,
        "items": [{"price": price_id}],
        "payment_behavior": "default_incomplete",
        "expand": ["latest_invoice.payment_intent"],
    }
    if trial_days > 0:
        params["trial_period_days"] = trial_days
    sub = stripe.Subscription.create(**params)
    return {
        "subscription_id": sub.id,
        "status": sub.status,
        "client_secret": sub.latest_invoice.payment_intent.client_secret
        if sub.latest_invoice and sub.latest_invoice.payment_intent
        else None,
    }


def validate_stripe_webhook(payload: bytes, sig_header: str) -> dict:
    """Valida assinatura do webhook Stripe e retorna o evento."""
    import stripe
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
        return event
    except stripe.error.SignatureVerificationError:
        raise ValueError("Assinatura do webhook Stripe inválida")


# -- Mercado Pago --

def _mp_sdk():
    import mercadopago
    token = os.environ.get("MP_ACCESS_TOKEN", "")
    return mercadopago.SDK(token)


def create_mp_pix(
    email: str,
    amount: float,
    description: str,
    external_reference: str,
) -> dict:
    """Cria cobrança PIX via Mercado Pago."""
    sdk = _mp_sdk()
    payment_data = {
        "transaction_amount": amount,
        "description": description,
        "payment_method_id": "pix",
        "external_reference": external_reference,
        "payer": {"email": email},
    }
    result = sdk.payment().create(payment_data)
    response = result["response"]
    if result["status"] not in (200, 201):
        raise RuntimeError(f"Erro MP: {response}")
    return {
        "payment_id": response["id"],
        "status": response["status"],
        "qr_code": response["point_of_interaction"]["transaction_data"]["qr_code"],
        "qr_code_base64": response["point_of_interaction"]["transaction_data"]["qr_code_base64"],
    }


def validate_mp_webhook(payload: bytes, x_signature: str, x_request_id: str) -> bool:
    """Valida assinatura do webhook do Mercado Pago."""
    secret = os.environ.get("MP_WEBHOOK_SECRET", "")
    # MP usa: manifest = "id:{data.id};request-id:{x-request-id};ts:{ts};"
    # Extrai ts e data_id do x_signature
    parts = {k: v for k, v in (p.split("=", 1) for p in x_signature.split(","))}
    ts = parts.get("ts", "")
    v1 = parts.get("v1", "")
    manifest = f"id:{x_request_id};request-id:{x_request_id};ts:{ts};"
    expected = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, v1)


# -- Status unificado --

def get_subscription_status(
    gateway: Literal["stripe", "mercadopago"],
    subscription_id: str,
) -> dict:
    if gateway == "stripe":
        stripe = _stripe_client()
        sub = stripe.Subscription.retrieve(subscription_id)
        return {"status": sub.status, "current_period_end": sub.current_period_end}
    raise NotImplementedError(f"Gateway {gateway} não implementado para status")
