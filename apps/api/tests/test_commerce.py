"""P2-1: cart → price re-check → order request (idempotent) → supplier confirmation (quote,
commissions) → lifecycle → payment only via a verified provider webhook → double-entry ledger
(capture, refund reversal, payout), reconciliation, export; «Integration pending» without a provider."""
import hashlib
import hmac
import json
import time

import httpx
import pytest
from sqlalchemy import select

from app import models as m
from app.commerce import ledger
from app.commerce import payments as pay_mod
from app.db import SessionLocal
from app.security import hash_password

pytestmark = pytest.mark.usefixtures("client")
PW = "Shop-Pass-12345"


@pytest.fixture(scope="module")
def world(client):
    """A real (non-demo) supplier with its own cabinet user, and an approved variant buying from it."""
    with SessionLocal() as db:
        org = m.Organization(name="Shop T LLC", kind="supplier")
        db.add(org)
        db.flush()
        u = m.User(email="shop.t@example.com", name="Shop T", password_hash=hash_password(PW), email_verified_at=m.utcnow(), onboarded_at=m.utcnow())
        db.add(u)
        db.flush()
        db.add(m.Membership(user_id=u.id, org_id=org.id, role="supplier_admin"))
        sup = m.Supplier(name="Shop T", slug="shop-t", org_id=org.id, is_demo=False, commission_pct=10.0)
        db.add(sup)
        db.flush()
        prod = m.Product(supplier_id=sup.id, category="sofa", name_ru="Диван Т", tier="comfort")
        db.add(prod)
        db.flush()
        pv = m.ProductVariant(product_id=prod.id, sku="T-1", price=400_000, currency="AMD", price_status="confirmed")
        db.add(pv)
        proj = db.query(m.Project).filter(m.Project.title.like("Демо%")).first()
        v = m.DesignVariant(project_id=proj.id, key="shop", title="Shop", style="modern", tier="comfort", status="approved")
        db.add(v)
        db.flush()
        est = {"lines": [
            {"id": "l1", "ref": f"pv:{pv.id}", "group": "furniture", "category": "sofa", "name": "Диван Т", "sku": "T-1", "qty": 1, "unit": "pcs",
             "unit_price": 400_000, "total": 400_000, "price_status": "confirmed", "supplier": "Shop T", "supplier_key": "shop-t"},
            {"id": "l2", "group": "delivery", "category": "delivery", "name": "Доставка", "qty": 1, "unit": "pcs", "unit_price": 10_000, "total": 10_000,
             "supplier": "Shop T", "supplier_key": "shop-t"}]}
        ver = m.DesignVersion(variant_id=v.id, number=1, scene={}, estimate=est)
        db.add(ver)
        db.flush()
        v.current_version_id = ver.id
        db.commit()
        ids = {"pid": proj.id, "vid": v.id, "pv": pv.id, "sup": sup.id, "org": proj.org_id}
    r = client.post("/api/v1/auth/login", json={"email": "shop.t@example.com", "password": PW})
    client.cookies.clear()
    ids["shop"] = {"Authorization": f"Bearer {r.json()['token']}"}
    yield ids
    with SessionLocal() as db:
        db.query(m.Order).filter(m.Order.project_id == ids["pid"]).delete()
        db.query(m.Cart).filter(m.Cart.project_id == ids["pid"]).delete()
        db.delete(db.get(m.DesignVariant, ids["vid"]))
        db.commit()


def _sign(secret: str, body: bytes, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    return f"t={ts},v1={hmac.new(secret.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()}"


def test_full_order_lifecycle_with_ledger(client, designer, world, monkeypatch):
    base = f"/api/v1/projects/{world['pid']}"
    orders = client.post(f"{base}/cart", headers=designer, json={"variant_id": world["vid"]}).json()
    assert len(orders) == 1 and orders[0]["totals"]["goods"] == 400_000 and orders[0]["totals"]["commission_platform"] == 40_000
    oid = orders[0]["id"]
    # ordering needs a fresh re-check; the price moved meanwhile
    assert client.post(f"{base}/orders/{oid}/request", headers=designer).json()["code"] == "order.recheck_required"
    with SessionLocal() as db:
        db.get(m.ProductVariant, world["pv"]).price = 420_000
        db.commit()
    rc = client.post(f"{base}/cart/recheck", headers=designer).json()
    assert rc["recheck"]["changed"] == [{"name": "Диван Т", "was": 400_000, "now": 420_000}] and rc["recheck"]["delta_amd"] == 20_000
    key = {"Idempotency-Key": "req-1"}
    o = client.post(f"{base}/orders/{oid}/request", headers={**designer, **key}).json()
    assert o["status"] == "requested" and o["totals"]["goods"] == 420_000
    assert client.post(f"{base}/orders/{oid}/request", headers={**designer, **key}).json()["status"] == "requested"  # retried → same order
    assert client.post(f"{base}/cart", headers=designer, json={"variant_id": world["vid"]}).json()["code"] == "cart.orders_in_progress"

    # supplier cabinet: sees the order, confirms a binding total → commissions fixed
    shop = world["shop"]
    assert [x["id"] for x in client.get("/api/v1/supplier/orders", headers=shop).json()] == [oid]
    assert client.post(f"/api/v1/supplier/orders/{oid}/status", headers=shop, json={"to": "delivering"}).json()["code"] == "order.bad_transition"
    o = client.post(f"/api/v1/supplier/orders/{oid}/confirm", headers=shop, json={"total_amd": 430_000, "valid_days": 5}).json()
    assert o["status"] == "confirmed" and o["quote"]["total_amd"] == 430_000
    assert {c["party"]: c["amount_amd"] for c in o["commissions"]} == {"platform": 43_000, "designer": 0}
    assert client.post(f"/api/v1/supplier/orders/{oid}/confirm", headers=world["shop"], json={"total_amd": 1}).status_code == 409

    # no payment provider → honest «integration pending», nothing marked paid
    assert client.get(f"{base}/cart", headers=designer).json()["payments"]["status"] == "integration_pending"
    r = client.post(f"{base}/orders/{oid}/pay", headers=designer)
    assert r.status_code == 409 and r.json()["code"] == "payment.integration_pending"

    # a Stripe-compatible provider is configured (test transport) → hosted checkout, webhook-only capture
    sessions = []
    secret = "whsec_test"
    prov = pay_mod.StripeCompatProvider("https://pay.example", "sk_test", secret,
                                        client=httpx.Client(transport=httpx.MockTransport(lambda req: sessions.append(req) or httpx.Response(200, json={"id": "cs_1", "url": "https://pay.example/c/cs_1"}))))
    monkeypatch.setattr(pay_mod, "get_provider", lambda: prov)
    import app.routers.commerce as rc_mod
    import app.routers.payments as rp_mod

    monkeypatch.setattr(rc_mod, "get_provider", lambda: prov)
    monkeypatch.setattr(rp_mod, "get_provider", lambda: prov)
    with SessionLocal() as db:
        db.merge(m.PlatformSetting(key="commerce", value={"tax_rate_pct": 20.0, "designer_commission_pct": 0.0}))
        db.commit()
    started = client.post(f"{base}/orders/{oid}/pay", headers={**designer, "Idempotency-Key": "pay-1"}).json()
    assert started["redirect_url"] == "https://pay.example/c/cs_1" and sessions[0].headers["Idempotency-Key"] == "pay-1"
    assert client.get(f"{base}/orders", headers=designer).json()[0]["payment_status"] == "pending"

    ev = json.dumps({"id": "evt_1", "type": "checkout.session.completed", "data": {"object": {"id": "cs_1", "amount_total": 430_000 * 100}}}).encode()
    bad = client.post("/api/v1/payments/webhook/stripe_compat", content=ev, headers={"Stripe-Signature": _sign("wrong", ev)})
    assert bad.status_code == 400 and bad.json()["code"] == "payment.bad_signature"
    stale = client.post("/api/v1/payments/webhook/stripe_compat", content=ev, headers={"Stripe-Signature": _sign(secret, ev, int(time.time()) - 3600)})
    assert stale.json()["code"] == "payment.stale_signature"
    assert client.post("/api/v1/payments/webhook/stripe_compat", content=ev, headers={"Stripe-Signature": _sign(secret, ev)}).json() == {"ok": True}
    assert client.post("/api/v1/payments/webhook/stripe_compat", content=ev, headers={"Stripe-Signature": _sign(secret, ev)}).json()["duplicate"] is True

    with SessionLocal() as db:
        b = ledger.balances(db)
        assert b["cash"] == 430_000
        assert b[f"supplier_payable:{world['sup']}"] == -(430_000 - 43_000)
        assert b["revenue:commission"] == -(43_000 - 8_600) and b["tax_payable"] == -8_600  # 20% tax on the platform commission
        rec = ledger.reconcile(db)
        assert rec["balanced"] and rec["payments_match_cash"]
        assert ledger.revenue_by_stream(db)["commission"] == 34_400
        entry = db.scalars(select(m.LedgerEntry)).first()
        entry.memo = "tampered"
        with pytest.raises(ValueError, match="immutable"):
            db.flush()
        db.rollback()

    # lifecycle after payment: cancel is refused (refund first); supplier ships; bureau closes
    assert client.post(f"{base}/orders/{oid}/transition", headers=designer, json={"to": "cancelled"}).json()["code"] == "order.paid_needs_refund"
    for to in ("in_production", "delivering"):
        assert client.post(f"/api/v1/supplier/orders/{oid}/status", headers=shop, json={"to": to}).json()["status"] == to
    o = client.post(f"{base}/orders/{oid}/transition", headers=designer, json={"to": "disputed", "note": "damaged leg"}).json()
    assert o["status"] == "disputed" and [h["to"] for h in o["history"]] == ["requested", "confirmed", "in_production", "delivering", "disputed"]

    # provider refund → reversing transaction, order refunded, cash back to zero
    rf = json.dumps({"id": "evt_2", "type": "charge.refunded", "data": {"object": {"id": "cs_1", "amount_refunded": 430_000 * 100}}}).encode()
    assert client.post("/api/v1/payments/webhook/stripe_compat", content=rf, headers={"Stripe-Signature": _sign(secret, rf)}).json() == {"ok": True}
    with SessionLocal() as db:
        assert db.get(m.Order, oid).status == "refunded"
        b = ledger.balances(db)
        assert b["cash"] == 0 and b[f"supplier_payable:{world['sup']}"] == 0
        assert ledger.reconcile(db)["balanced"]
        db.query(m.PlatformSetting).filter_by(key="commerce").delete()
        db.commit()


def test_payouts_and_ledger_rules(client, admin):
    with SessionLocal() as db:
        with pytest.raises(ledger.LedgerError):
            ledger.post(db, "adjustment", [("cash", 10, 0), ("revenue:x", 0, 9)], idempotency_key="bad-1")
        t1 = ledger.post(db, "adjustment", [("cash", 100, 0), ("supplier_payable:s-pay", 0, 100)], idempotency_key="adj-1")
        assert ledger.post(db, "adjustment", [("cash", 100, 0), ("supplier_payable:s-pay", 0, 100)], idempotency_key="adj-1") == t1  # idempotent
        db.commit()
    r = client.post("/api/v1/admin/payouts", headers=admin, json={"supplier_id": "s-pay", "amount_amd": 150, "reference": "bank-1"})
    assert r.status_code == 409 and r.json()["code"] == "payout.exceeds_balance"
    r = client.post("/api/v1/admin/payouts", headers=admin, json={"supplier_id": "s-pay", "amount_amd": 100, "reference": "bank-1"}).json()
    assert r["status"] == "recorded"
    assert client.post("/api/v1/admin/payouts", headers=admin, json={"supplier_id": "s-pay", "amount_amd": 100, "reference": "bank-1"}).json()["id"] == r["id"]
    ov = client.get("/api/v1/admin/ledger", headers=admin).json()
    assert ov["balances"]["supplier_payable:s-pay"] == 0 and ov["reconcile"]["balanced"]
    csv_r = client.get("/api/v1/admin/ledger/export.csv", headers=admin)
    assert csv_r.status_code == 200 and "supplier_payable:s-pay" in csv_r.content.decode("utf-8-sig")
    assert client.get("/api/v1/admin/ledger/export.xlsx", headers=admin).content[:2] == b"PK"
    from tests.conftest import login

    assert client.get("/api/v1/admin/ledger", headers=login(client)).status_code == 403


def test_tariffs_plan_limit_and_revenue_report(client, admin, designer):
    t = {"bureau_plans": [{"key": "start", "name": "Start", "price_amd_month": 25_000, "max_projects": 1}], "credit_packs": [{"key": "c100", "credits": 100, "price_amd": 10_000}],
         "procurement_fee": {"mode": "pct", "value": 3}, "export_prices_amd": {"dwg": 5_000}}
    assert client.put("/api/v1/admin/tariffs", headers=admin, json=t).json()["bureau_plans"][0]["max_projects"] == 1
    assert client.put("/api/v1/admin/tariffs", headers=designer, json=t).status_code == 403
    dup = {**t, "bureau_plans": t["bureau_plans"] * 2}
    assert client.put("/api/v1/admin/tariffs", headers=admin, json=dup).status_code == 422
    with SessionLocal() as db:
        org_id = db.query(m.Project).filter(m.Project.title.like("Демо%")).first().org_id
    assert client.put(f"/api/v1/admin/orgs/{org_id}/plan", headers=admin, json={"plan": "nope"}).status_code == 422
    u = client.put(f"/api/v1/admin/orgs/{org_id}/plan", headers=admin, json={"plan": "start"}).json()
    assert u["plan"]["key"] == "start" and u["usage"]["projects"] >= 1
    r = client.post("/api/v1/projects", headers=designer, json={"title": "Over the limit"})
    assert r.status_code == 402 and r.json()["code"] == "plan.project_limit"
    assert client.get("/api/v1/bureau/plan", headers=designer).json()["plan"]["name"] == "Start"
    client.put(f"/api/v1/admin/orgs/{org_id}/plan", headers=admin, json={"plan": None})
    assert client.post("/api/v1/projects", headers=designer, json={"title": "Unlimited again"}).status_code == 200
    # revenue only from the ledger: an offline invoice paid by bank transfer
    body = {"stream": "subscription", "amount_amd": 25_000, "reference": "INV-2026-001", "org_id": org_id}
    t1 = client.post("/api/v1/admin/revenue/manual", headers=admin, json=body).json()["txn_id"]
    assert client.post("/api/v1/admin/revenue/manual", headers=admin, json=body).json()["txn_id"] == t1  # idempotent
    rep = client.get("/api/v1/admin/revenue", headers=admin).json()
    assert rep["totals"]["subscription"] == 25_000 and "credits" in rep["totals"]
    with SessionLocal() as db:
        db.query(m.Project).filter(m.Project.title == "Unlimited again").delete()
        db.query(m.PlatformSetting).filter_by(key="tariffs").delete()
        db.commit()
