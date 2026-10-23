"""Pricing v1.0, AI credits, subscriptions and credit packs paid through Ameriabank vPOS (bank API mocked per the
vPOS 3.1 spec), refunds, plan limits, supplier applications."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app import models as m
from app.commerce import ameriabank, credits
from app.db import SessionLocal
from app.security import hash_password
from tests.conftest import login

pytestmark = pytest.mark.usefixtures("client")


class FakeBank:
    """vPOS 3.1 test server: InitPayment → PaymentID; GetPaymentDetails reports what the test sets."""

    def __init__(self):
        self.payments: dict[str, dict] = {}
        self.calls: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        op = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content or b"{}")
        self.calls.append((op, body))
        if body.get("Password") != "s3cret":
            return httpx.Response(200, json={"ResponseCode": "20", "ResponseMessage": "Incorrect Username and Password"})
        if op == "InitPayment":
            pid = f"PAY-{body['OrderID']}"
            self.payments[pid] = {"Amount": body["Amount"], "OrderID": body["OrderID"], "OrderStatus": "0", "ResponseCode": "", "Opaque": body.get("Opaque")}
            return httpx.Response(200, json={"PaymentID": pid, "ResponseCode": 1, "ResponseMessage": "OK"})
        pay = self.payments.get(body.get("PaymentID"), {})
        if op == "GetPaymentDetails":
            return httpx.Response(200, json={**pay, "CardNumber": "4083****1234", "ApprovalCode": "A1", "ClientEmail": "card@holder.am", "ExpDate": "1228"})
        if op == "RefundPayment":
            pay["OrderStatus"] = "4"
            return httpx.Response(200, json={"ResponseCode": "00", "ResponseMessage": "OK"})
        if op in ("CancelPayment", "ConfirmPayment"):
            pay["OrderStatus"] = "3" if op == "CancelPayment" else "2"
            return httpx.Response(200, json={"ResponseCode": "00"})
        return httpx.Response(404)

    def pay(self, pid: str, status: str = "2", amount=None):
        self.payments[pid].update(OrderStatus=status, ResponseCode="00" if status in ("1", "2") else "0116")
        if amount is not None:
            self.payments[pid]["Amount"] = amount


@pytest.fixture()
def bank(monkeypatch):
    fb = FakeBank()
    monkeypatch.setattr(ameriabank, "_http", lambda: httpx.Client(transport=httpx.MockTransport(fb.handler)))
    yield fb
    with SessionLocal() as db:
        db.query(m.PlatformSetting).filter_by(key="vpos").delete()
        db.commit()


@pytest.fixture()
def studio(client):
    """A fresh bureau with its head (known password) — billing state never leaks into other tests."""
    with SessionLocal() as db:
        org = m.Organization(name="Billing Studio", kind="bureau", settings={})
        u = m.User(email=f"head.{datetime.now().timestamp()}@studio.am", name="Head", password_hash=hash_password("demo1234"),
                   email_verified_at=datetime.now(timezone.utc), onboarded_at=datetime.now(timezone.utc))
        db.add_all([org, u])
        db.flush()
        db.add(m.Membership(user_id=u.id, org_id=org.id, role="bureau_admin"))
        db.commit()
        org_id, email = org.id, u.email
    return org_id, login(client, email)


def _vpos(client, admin):
    return client.put("/api/v1/admin/billing/vpos", headers=admin, json={"client_id": "CID-1", "username": "renovara", "password": "s3cret", "mode": "test",
                                                                         "order_id_offset": 2_000_000})


def test_public_pricing_is_the_owner_catalogue(client):
    pr = client.get("/api/v1/public/pricing").json()
    plans = {p["key"]: p for p in pr["bureau_plans"] + pr["supplier_plans"]}
    assert plans["designer_start"]["price_amd_month"] == 5000 and plans["designer_start"]["price_amd_year"] == 50000
    assert plans["bureau"]["price_amd_month"] == 49900 and plans["bureau"]["seats"] == 5 and plans["bureau"]["ai_credits_month"] == 700
    assert plans["enterprise"]["custom"] and plans["supplier_mini"]["commission_pct"] == 12 and plans["supplier_pro"]["sku_limit"] == 2000
    assert [c["credits"] for c in pr["credit_packs"]] == [100, 500, 2000, 10000] and pr["credit_costs"]["image_pro_4k"] == 45
    assert pr["online_payments"] is False


def test_vpos_settings_are_admin_only_and_never_return_the_password(client, admin, bank):
    ops = login(client, "ops@forma.local")
    assert client.get("/api/v1/admin/billing/vpos", headers=ops).status_code == 403
    cfg = _vpos(client, admin).json()
    assert cfg["configured"] and cfg["password_set"] and "password" not in cfg and cfg["effective_base"] == ameriabank.TEST_BASE
    cfg = client.put("/api/v1/admin/billing/vpos", headers=admin, json={"client_id": "CID-1", "username": "renovara", "mode": "test", "order_id_offset": 2_000_000}).json()
    assert cfg["password_set"]  # empty password keeps the stored one
    with SessionLocal() as db:
        assert "s3cret" not in json.dumps(db.get(m.PlatformSetting, "vpos").value)  # encrypted at rest


def test_subscription_paid_by_card_activates_plan_and_credits(client, admin, designer, bank, studio):
    org_id, head = studio
    assert client.post("/api/v1/billing/checkout", headers=head, json={"purpose": "plan", "key": "designer_pro"}).json()["code"] == "billing.not_configured"
    _vpos(client, admin)
    assert client.post("/api/v1/billing/checkout", headers=designer, json={"purpose": "plan", "key": "designer_pro"}).status_code == 403  # not the payer
    assert client.post("/api/v1/billing/checkout", headers=head, json={"purpose": "plan", "key": "enterprise"}).json()["code"] == "billing.not_purchasable"
    r = client.post("/api/v1/billing/checkout", headers=head, json={"purpose": "plan", "key": "designer_pro", "interval": "month", "lang": "ru"}).json()
    assert r["redirect_url"].startswith(f"{ameriabank.TEST_BASE}/Payments/Pay?id=PAY-") and r["redirect_url"].endswith("&lang=ru")
    init = next(b for op, b in bank.calls if op == "InitPayment")
    assert init["Amount"] == 12000 and init["Currency"] == "051" and init["OrderID"] > 2_000_000 and init["BackURL"].endswith("/api/v1/billing/vpos/return")
    pid = f"PAY-{init['OrderID']}"
    # the browser returns before the money is deposited: nothing is activated
    back = client.get("/api/v1/billing/vpos/return", params={"orderID": init["OrderID"], "paymentID": pid, "resposneCode": "00", "opaque": r["payment_id"]},
                      follow_redirects=False)
    assert back.status_code == 303 and "status=redirected" in back.headers["location"]
    bank.pay(pid)
    back = client.get("/api/v1/billing/vpos/return", params={"orderID": init["OrderID"], "paymentID": pid, "resposneCode": "00", "opaque": r["payment_id"]},
                      follow_redirects=False)
    assert "status=paid" in back.headers["location"]
    b = client.get("/api/v1/billing", headers=head).json()
    assert b["plan"]["key"] == "designer_pro" and b["usage"]["credits"] == 150 and b["payments"][0]["card"] == "4083****1234"
    until = datetime.fromisoformat(b["paid_until"])
    assert timedelta(days=27) < until - datetime.now(timezone.utc) < timedelta(days=32)
    # a repeated return or sync changes nothing
    client.get("/api/v1/billing/vpos/return", params={"paymentID": pid, "opaque": r["payment_id"]}, follow_redirects=False)
    assert client.post(f"/api/v1/billing/payments/{r['payment_id']}/sync", headers=head).json()["status"] == "paid"
    with SessionLocal() as db:
        pay = db.get(m.BillingPayment, r["payment_id"])
        assert "card@holder.am" not in json.dumps(pay.details) and "ExpDate" not in pay.details  # no card holder data kept
        assert db.query(m.LedgerEntry).filter_by(idempotency_key=f"billing:{pay.id}").count() == 2
        assert credits.balance(db, org_id) == 150
    assert client.get("/api/v1/admin/ledger", headers=admin).json()["reconcile"]["billing_matches_acquirer"]


def test_credit_pack_refund_spend_and_enforcement(client, admin, bank, studio):
    org_id, head = studio
    _vpos(client, admin)
    r = client.post("/api/v1/billing/checkout", headers=head, json={"purpose": "credits", "key": "c500"}).json()
    pid = next(b for op, b in bank.calls if op == "InitPayment")["OrderID"]
    bank.pay(f"PAY-{pid}")
    assert client.post(f"/api/v1/billing/payments/{r['payment_id']}/sync", headers=head).json()["status"] == "paid"
    with SessionLocal() as db:
        assert credits.balance(db, org_id) == 500
        assert credits.charge(db, org_id, "image_pro_4k") == 45 and credits.charge(db, org_id, "unknown_op") == 0
        db.commit()
        assert credits.balance(db, org_id) == 455
    led = client.get("/api/v1/billing", headers=head).json()["credit_ledger"]
    assert led[0]["delta"] == -45 and led[0]["operation"] == "image_pro_4k"
    assert client.post(f"/api/v1/admin/billing/payments/{r['payment_id']}/refund", headers=head, json={"reason": "test"}).status_code == 403
    assert client.post(f"/api/v1/admin/billing/payments/{r['payment_id']}/refund", headers=admin, json={"amount_amd": 999999, "reason": "too much"}).json()["code"] == "billing.refund_amount"
    rf = client.post(f"/api/v1/admin/billing/payments/{r['payment_id']}/refund", headers=admin, json={"reason": "customer request"}).json()
    assert rf["status"] == "refunded" and rf["refunded_amd"] == 5900
    with SessionLocal() as db:
        assert credits.balance(db, org_id) == 0  # the remaining pack credits are revoked
        org = db.get(m.Organization, org_id)
        org.settings = {"plan": "free"}
        db.commit()
    # enforcement is a platform switch; at zero balance a paid operation is refused
    t = client.get("/api/v1/admin/tariffs", headers=admin).json()
    client.put("/api/v1/admin/tariffs", headers=admin, json={**t, "credits_enforced": True})
    with SessionLocal() as db:
        with pytest.raises(credits.NoCredits):
            credits.check(db, org_id, "grounded_render")
        credits.check(db, org_id, "unknown_op")
    with SessionLocal() as db:
        db.query(m.PlatformSetting).filter_by(key="tariffs").delete()
        db.commit()


def test_declined_and_mismatched_payments_activate_nothing(client, admin, bank, studio):
    org_id, head = studio
    _vpos(client, admin)
    a = client.post("/api/v1/billing/checkout", headers=head, json={"purpose": "credits", "key": "c100"}).json()
    b = client.post("/api/v1/billing/checkout", headers=head, json={"purpose": "credits", "key": "c100"}).json()
    ids = [x["OrderID"] for op, x in bank.calls if op == "InitPayment"]
    bank.pay(f"PAY-{ids[0]}", status="6")
    bank.pay(f"PAY-{ids[1]}", amount=1)  # the bank reports another amount than we charged
    assert client.post(f"/api/v1/billing/payments/{a['payment_id']}/sync", headers=head).json()["status"] == "declined"
    assert client.post(f"/api/v1/billing/payments/{b['payment_id']}/sync", headers=head).json()["status"] == "error"
    with SessionLocal() as db:
        assert credits.balance(db, org_id) == 0


def test_balance_spends_soonest_expiring_grants_first():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        org = m.Organization(name="Credits Lab", kind="bureau", settings={})
        db.add(org)
        db.flush()
        credits.grant(db, org.id, 50, "grant_plan", expires_at=now + timedelta(days=5))
        credits.grant(db, org.id, 100, "grant_pack", expires_at=now + timedelta(days=300))
        db.flush()
        db.add(m.CreditEntry(org_id=org.id, delta=-60, reason="spend", operation="x", created_at=now + timedelta(seconds=1)))
        db.flush()
        assert credits.balance(db, org.id, now + timedelta(seconds=2)) == 90
        assert credits.balance(db, org.id, now + timedelta(days=6)) == 90  # the expired plan grant was used up first
        assert not credits.grant(db, org.id, 10, "grant_trial", idempotency_key="t1") or not credits.grant(db, org.id, 10, "grant_trial", idempotency_key="t1")
        db.rollback()


def test_trial_plan_limits_and_expiry(client, admin, studio):
    org_id, head = studio
    b = client.post("/api/v1/billing/trial", headers=head).json()
    assert b["plan"]["key"] == "free" and b["plan"]["max_projects"] == 3 and b["usage"]["credits"] == 50
    assert client.post("/api/v1/billing/trial", headers=head).json()["code"] == "billing.trial_used"
    for i in range(3):
        assert client.post("/api/v1/projects", headers=head, json={"title": f"T{i}"}).status_code == 200
    assert client.post("/api/v1/projects", headers=head, json={"title": "T4"}).json()["code"] == "plan.project_limit"
    # seats: Designer Start has one seat
    client.put(f"/api/v1/admin/orgs/{org_id}/plan", headers=admin, json={"plan": "designer_start"})
    r = client.post("/api/v1/team/invite", headers=head, json={"email": "second@studio.am", "name": "Second", "role": "designer"})
    assert r.status_code == 402 and r.json()["code"] == "plan.seat_limit"
    # a paid period that ended falls back to Free
    with SessionLocal() as db:
        org = db.get(m.Organization, org_id)
        org.settings = {**org.settings, "plan": "designer_pro", "paid_until": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), "trial_until": None}
        db.commit()
    assert client.get("/api/v1/billing", headers=head).json()["plan"]["key"] == "free"


def test_supplier_plan_limits_skus_and_sets_commission(client, admin):
    sh = login(client, "supplier@forma.local")
    ov = client.get("/api/v1/supplier/overview", headers=sh).json()
    org_id = ov["supplier"]["org_id"]
    assert client.put(f"/api/v1/admin/orgs/{org_id}/plan", headers=admin, json={"plan": "designer_pro"}).status_code == 422  # not a supplier plan
    client.put(f"/api/v1/admin/orgs/{org_id}/plan", headers=admin, json={"plan": "supplier_mini"})
    assert client.get("/api/v1/supplier/overview", headers=sh).json()["supplier"]["commission_pct"] == 12
    body = {"supplier_id": ov["supplier"]["id"], "category": "sofa", "name_ru": "Сверх лимита", "variants": [{"sku": "OVER-1"}]}
    if ov["products"] >= 20:
        r = client.post("/api/v1/catalog/products", headers=sh, json=body)
        assert r.status_code == 402 and r.json()["code"] == "plan.sku_limit"
    b = client.get("/api/v1/billing", headers=sh).json()
    assert {p["audience"] for p in b["plans"]} <= {"supplier", "manufacturer"} and b["credit_packs"] == [] and "skus" in b["usage"]
    client.put(f"/api/v1/admin/orgs/{org_id}/plan", headers=admin, json={"plan": None})


def test_supplier_application_flow(client, admin):
    body = {"company": "Lusastgh Lighting", "contact_name": "Ani", "email": "Ani@Lusastgh.am", "phone": "+374 10 11 11 11", "kind": "store",
            "sku_count": 120, "categories": ["lighting"], "message": "Хотим подключиться", "locale": "ru", "consent": True}
    assert client.post("/api/v1/public/supplier-applications", json={**body, "consent": False}).status_code == 422
    assert client.post("/api/v1/public/supplier-applications", json={**body, "hp": "bot"}).json()["ok"]
    assert client.post("/api/v1/public/supplier-applications", json=body).json()["ok"]
    apps = [a for a in client.get("/api/v1/admin/supplier-applications", headers=admin).json() if a["company"] == "Lusastgh Lighting"]
    assert len(apps) == 1 and apps[0]["email"] == "ani@lusastgh.am"  # the bot submission was not stored
    assert client.get("/api/v1/admin/supplier-applications", headers=login(client, "ops@forma.local")).status_code == 403
    a = client.post(f"/api/v1/admin/supplier-applications/{apps[0]['id']}/decision", headers=admin, json={"decision": "approved"}).json()
    assert a["status"] == "approved" and a["org_id"]
    with SessionLocal() as db:
        sup = db.query(m.Supplier).filter_by(org_id=a["org_id"]).one()
        assert sup.verification == "pending" and not sup.is_demo
        u = db.query(m.User).filter_by(email="ani@lusastgh.am").one()
        assert db.query(m.Membership).filter_by(user_id=u.id, org_id=a["org_id"], role="supplier_admin").count() == 1
    assert client.post(f"/api/v1/admin/supplier-applications/{apps[0]['id']}/decision", headers=admin, json={"decision": "rejected"}).json()["code"] == "application.decided"
