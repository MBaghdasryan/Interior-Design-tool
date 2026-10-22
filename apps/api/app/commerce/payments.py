"""Payment providers behind one interface. No contract → `NotConfigured`: the UI shows
«Integration pending» and nothing is ever marked paid. Money moves in the ledger only after a
webhook whose signature verifies.

Implemented adapter: `stripe_compat` — a Stripe-compatible hosted checkout (create session over
HTTPS, webhook signed `t=<unix>,v1=<hex hmac-sha256(secret, "<t>.<body>")>`, 5-minute tolerance).
Armenian acquirers (Idram, ArCa, Ameriabank vPOS) need their contract and API documentation; they
are registered as names so configuration errors are explicit, and report `adapter_pending`."""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass

import httpx

from ..config import get_settings

PENDING_ADAPTERS = ("idram", "arca", "ameriabank")


class PaymentError(Exception):
    pass


@dataclass
class WebhookEvent:
    id: str
    type: str  # payment.succeeded | payment.failed | payment.refunded
    provider_ref: str
    amount_amd: int


class PaymentProvider:
    name = "none"
    status = "integration_pending"

    def configured(self) -> bool:
        return False

    def create_payment(self, *, order_id: str, amount_amd: int, idempotency_key: str, return_url: str) -> dict:
        raise PaymentError("payment.integration_pending")

    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent:
        raise PaymentError("payment.integration_pending")


class StripeCompatProvider(PaymentProvider):
    name = "stripe_compat"
    status = "configured"

    def __init__(self, api_base: str, api_key: str, webhook_secret: str, client: httpx.Client | None = None, now=time.time):
        self.api_base, self.api_key, self.secret = api_base.rstrip("/"), api_key, webhook_secret
        self.client = client or httpx.Client(timeout=20)
        self.now = now

    def configured(self) -> bool:
        return bool(self.api_base and self.api_key and self.secret)

    def create_payment(self, *, order_id: str, amount_amd: int, idempotency_key: str, return_url: str) -> dict:
        r = self.client.post(f"{self.api_base}/v1/checkout/sessions", headers={"Authorization": f"Bearer {self.api_key}", "Idempotency-Key": idempotency_key},
                             data={"mode": "payment", "client_reference_id": order_id, "success_url": return_url, "cancel_url": return_url,
                                   "line_items[0][price_data][currency]": "amd", "line_items[0][price_data][unit_amount]": str(amount_amd * 100),
                                   "line_items[0][price_data][product_data][name]": f"Order {order_id}", "line_items[0][quantity]": "1"})
        if r.status_code >= 400:
            raise PaymentError(f"provider {r.status_code}")
        j = r.json()
        return {"provider_ref": j["id"], "redirect_url": j.get("url", "")}

    def verify_webhook(self, headers: dict, body: bytes) -> WebhookEvent:
        sig = {k.lower(): v for k, v in headers.items()}.get("stripe-signature", "")
        parts = dict(p.split("=", 1) for p in sig.split(",") if "=" in p)
        try:
            ts = int(parts.get("t", "0"))
        except ValueError:
            raise PaymentError("payment.bad_signature") from None
        expected = hmac.new(self.secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        if not parts.get("v1") or not hmac.compare_digest(expected, parts["v1"]):
            raise PaymentError("payment.bad_signature")
        if abs(self.now() - ts) > 300:
            raise PaymentError("payment.stale_signature")
        ev = json.loads(body)
        obj = ev.get("data", {}).get("object", {})
        kind = {"checkout.session.completed": "payment.succeeded", "charge.refunded": "payment.refunded",
                "checkout.session.expired": "payment.failed", "payment_intent.payment_failed": "payment.failed"}.get(ev.get("type", ""), "ignored")
        amount = int(obj.get("amount_total") or obj.get("amount_refunded") or obj.get("amount") or 0) // 100
        return WebhookEvent(id=str(ev.get("id", "")), type=kind, provider_ref=str(obj.get("id") or obj.get("checkout_session") or ""), amount_amd=amount)


class PendingAdapter(PaymentProvider):
    status = "adapter_pending"

    def __init__(self, name: str):
        self.name = name


def get_provider() -> PaymentProvider:
    s = get_settings()
    name = (s.payment_provider or "").lower()
    if name == "stripe_compat":
        p = StripeCompatProvider(s.payment_api_base or "", s.payment_api_key or "", s.payment_webhook_secret or "")
        return p if p.configured() else PaymentProvider()
    if name in PENDING_ADAPTERS:
        return PendingAdapter(name)
    return PaymentProvider()
