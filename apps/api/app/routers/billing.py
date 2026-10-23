"""Pricing, subscriptions and AI-credit packs (pricing v1.0), card payments through Ameriabank vPOS,
the public price list and «become a supplier» applications."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..commerce import ameriabank, billing, credits, tariffs
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..ratelimit import check as rate_check
from ..security import Principal, audit, current_principal, require

router = APIRouter(tags=["billing"])
PAYER_ROLES = {"bureau_admin", "supplier_admin", "platform_admin"}


def _raise(e: billing.BillingError):
    status = {"billing.not_configured": 409, "billing.trial_used": 409, "billing.bank_error": 502, "billing.not_refundable": 409}.get(e.code, 422)
    raise ApiError(status, e.code, **e.params) from None


def payment_dict(p: m.BillingPayment) -> dict:
    d = p.details or {}
    return {"id": p.id, "org_id": p.org_id, "purpose": p.purpose, "item_key": p.item_key, "interval": p.interval, "amount_amd": p.amount_amd, "status": p.status,
            "order_id": p.order_id, "card": d.get("CardNumber"), "approval_code": d.get("ApprovalCode"), "refunded_amd": p.refunded_amd,
            "created_at": p.created_at.isoformat() if p.created_at else None, "paid_at": p.paid_at.isoformat() if p.paid_at else None}


# ------------------------------------------------------------------ public price list
@router.get("/api/v1/public/pricing")
def public_pricing(db: Session = Depends(get_db)):
    t = tariffs.get_tariffs(db)
    return {"version": t.version, "bureau_plans": [p.model_dump() for p in t.bureau_plans], "supplier_plans": [p.model_dump() for p in t.supplier_plans],
            "credit_packs": [c.model_dump() for c in t.credit_packs], "storage_addons": [s.model_dump() for s in t.storage_addons],
            "credit_costs": t.credit_costs, "trial": t.trial.model_dump(), "online_payments": ameriabank.load_config(db).configured}


# ------------------------------------------------------------------ the organisation's billing
def _billing_org(p: Principal, db: Session, org_id: str | None) -> tuple[m.Organization, bool]:
    if org_id and p.is_platform_admin:
        org = db.get(m.Organization, org_id)
        if not org:
            raise ApiError(404, "not_found")
        return org, True
    org = next((o for o in (db.get(m.Organization, i) for i in p.org_ids) if o and o.kind in ("bureau", "supplier")), None)
    if not org:
        raise ApiError(404, "billing.no_org")
    return org, bool(p.roles.get(org.id, set()) & PAYER_ROLES)


@router.get("/api/v1/billing")
def my_billing(org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org, can_pay = _billing_org(p, db, org_id)
    t = tariffs.get_tariffs(db)
    pays = db.scalars(select(m.BillingPayment).where(m.BillingPayment.org_id == org.id).order_by(m.BillingPayment.created_at.desc()).limit(50))
    return {"org": {"id": org.id, "name": org.name, "kind": org.kind}, "can_pay": can_pay, **tariffs.plan_usage(db, org),
            "plans": [x.model_dump() for x in tariffs.plans_for(t, org.kind)], "credit_packs": [c.model_dump() for c in t.credit_packs] if org.kind != "supplier" else [],
            "credit_costs": t.credit_costs, "trial": t.trial.model_dump(), "credits_enforced": t.credits_enforced,
            "credit_ledger": credits.ledger(db, org.id, 30), "payments": [payment_dict(x) for x in pays],
            "online_payments": ameriabank.load_config(db).configured}


class CheckoutIn(BaseModel):
    purpose: str = Field(pattern="^(plan|credits)$")
    key: str = Field(min_length=2, max_length=40)
    interval: str = Field(default="month", pattern="^(month|year)$")
    lang: str = Field(default="hy", pattern="^(hy|ru|en)$")


@router.post("/api/v1/billing/checkout")
def start_checkout(body: CheckoutIn, org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Free plans switch at once; paid ones start a card payment on the bank's page (the browser is redirected)."""
    org, can_pay = _billing_org(p, db, org_id)
    if not can_pay:
        raise ApiError(403, "billing.not_payer")
    rate_check(f"checkout:{org.id}", 10, 600)
    if body.purpose == "plan":
        plan = next((x for x in tariffs.plans_for(tariffs.get_tariffs(db), org.kind) if x.key == body.key), None)
        if plan and plan.price_amd_month == 0 and not plan.custom:
            billing.assign_plan(db, org, plan.key)
            audit(db, p, "billing.plan_free", "organization", org.id, org_id=org.id, data={"plan": plan.key})
            db.commit()
            return {"status": "applied", "redirect_url": None}
    back = f"{get_settings().public_base_url.rstrip('/')}/api/v1/billing/vpos/return"
    try:
        pay = billing.checkout(db, org, p.user, purpose=body.purpose, key=body.key, interval=body.interval, back_url=back, lang=body.lang)
    except billing.BillingError as e:
        _raise(e)
    audit(db, p, "billing.checkout", "billing_payment", pay.id, org_id=org.id, data={"purpose": body.purpose, "key": body.key, "amount_amd": pay.amount_amd})
    db.commit()
    return {"status": pay.status, "payment_id": pay.id, "redirect_url": pay.details.get("pay_url")}


@router.get("/api/v1/billing/vpos/return", include_in_schema=False)
def vpos_return(request: Request, db: Session = Depends(get_db)):
    """The bank returns the browser here (orderID, paymentID, resposneCode, opaque). The query is only a hint:
    the status is always read from GetPaymentDetails."""
    q = request.query_params
    pid = q.get("paymentID") or q.get("paymentid") or ""
    pay = db.scalar(select(m.BillingPayment).where(m.BillingPayment.provider_payment_id == pid)) if pid else None
    if pay and q.get("opaque") and q.get("opaque") != pay.id:
        pay = None
    base = get_settings().public_base_url.rstrip("/")
    if not pay:
        return RedirectResponse(f"{base}/app/billing?status=unknown", status_code=303)
    billing.sync(db, pay)
    db.commit()
    return RedirectResponse(f"{base}/app/billing?payment={pay.id}&status={pay.status}", status_code=303)


@router.post("/api/v1/billing/payments/{bid}/sync")
def sync_payment(bid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    pay = db.get(m.BillingPayment, bid)
    if not pay or not (p.is_platform_admin or pay.org_id in p.org_ids):
        raise ApiError(404, "not_found")
    billing.sync(db, pay)
    db.commit()
    return payment_dict(pay)


@router.post("/api/v1/billing/trial")
def start_trial(org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org, can_pay = _billing_org(p, db, org_id)
    if not can_pay or org.kind != "bureau":
        raise ApiError(403, "billing.not_payer")
    try:
        billing.start_trial(db, org)
    except billing.BillingError as e:
        _raise(e)
    audit(db, p, "billing.trial", "organization", org.id, org_id=org.id)
    db.commit()
    return tariffs.plan_usage(db, org)


# ------------------------------------------------------------------ platform admin
class VposIn(BaseModel):
    client_id: str = Field(default="", max_length=100)
    username: str = Field(default="", max_length=100)
    password: str | None = Field(default=None, max_length=200)  # empty / omitted = keep the stored one
    mode: str = Field(default="test", pattern="^(test|live)$")
    base_url: str = Field(default="", max_length=200, pattern=r"^(https://[^\s]+)?$")
    order_id_offset: int = Field(default=0, ge=0, le=2_000_000_000)


@router.get("/api/v1/admin/billing/vpos")
def get_vpos(p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    return ameriabank.public_config(db)


@router.put("/api/v1/admin/billing/vpos")
def put_vpos(body: VposIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    ameriabank.save_config(db, client_id=body.client_id, username=body.username, password=body.password, mode=body.mode, base_url=body.base_url,
                           order_id_offset=body.order_id_offset)
    audit(db, p, "billing.vpos_settings", "platform_setting", "vpos", data={"mode": body.mode, "client_id": body.client_id, "password_changed": bool(body.password)})
    db.commit()
    return ameriabank.public_config(db)


@router.get("/api/v1/admin/billing/payments")
def admin_payments(status: str = "", limit: int = Query(200, le=500), p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    stmt = select(m.BillingPayment)
    if status:
        stmt = stmt.where(m.BillingPayment.status == status)
    rows = db.scalars(stmt.order_by(m.BillingPayment.created_at.desc()).limit(limit)).all()
    names = {o.id: o.name for o in db.scalars(select(m.Organization).where(m.Organization.id.in_({r.org_id for r in rows})))} if rows else {}
    return [{**payment_dict(r), "org_name": names.get(r.org_id, "")} for r in rows]


class RefundIn(BaseModel):
    amount_amd: int | None = Field(default=None, gt=0)
    reason: str = Field(min_length=3, max_length=300)


@router.post("/api/v1/admin/billing/payments/{bid}/refund")
def admin_refund(bid: str, body: RefundIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    pay = db.get(m.BillingPayment, bid)
    if not pay:
        raise ApiError(404, "not_found")
    try:
        billing.refund(db, pay, body.amount_amd)
    except billing.BillingError as e:
        _raise(e)
    audit(db, p, "billing.refund", "billing_payment", bid, org_id=pay.org_id, data={"amount_amd": body.amount_amd or pay.amount_amd, "reason": body.reason})
    db.commit()
    return payment_dict(pay)


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/api/v1/admin/billing/payments/{bid}/cancel")
def admin_cancel(bid: str, body: CancelIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    pay = db.get(m.BillingPayment, bid)
    if not pay or not pay.provider_payment_id:
        raise ApiError(404, "not_found")
    try:
        billing.cancel(db, pay)
    except billing.BillingError as e:
        _raise(e)
    audit(db, p, "billing.cancel", "billing_payment", bid, org_id=pay.org_id, data={"reason": body.reason})
    db.commit()
    return payment_dict(pay)


class GrantIn(BaseModel):
    credits: int = Field(gt=0, le=1_000_000)
    reason: str = Field(min_length=3, max_length=300)
    months: int = Field(default=12, ge=1, le=36)


@router.post("/api/v1/admin/orgs/{org_id}/credits")
def admin_grant(org_id: str, body: GrantIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    org = db.get(m.Organization, org_id)
    if not org:
        raise ApiError(404, "not_found")
    from datetime import datetime, timezone

    credits.grant(db, org.id, body.credits, "grant_admin", ref=body.reason[:120], expires_at=billing.add_months(datetime.now(timezone.utc), body.months), user_id=p.user.id)
    audit(db, p, "billing.credits_grant", "organization", org.id, org_id=org.id, data=body.model_dump())
    db.commit()
    return {"balance": credits.balance(db, org.id)}


# ------------------------------------------------------------------ «become a supplier» applications
class ApplicationIn(BaseModel):
    company: str = Field(min_length=2, max_length=200)
    contact_name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str = Field(default="", max_length=40)
    website: str = Field(default="", max_length=300)
    city: str = Field(default="", max_length=100)
    kind: str = Field(default="store", pattern="^(store|manufacturer|installer)$")
    sku_count: int | None = Field(default=None, ge=0, le=10_000_000)
    categories: list[str] = Field(default_factory=list, max_length=30)
    message: str = Field(default="", max_length=2000)
    locale: str = Field(default="hy", pattern="^(hy|ru|en)$")
    consent: bool
    hp: str = Field(default="", max_length=200)  # honeypot: humans leave it empty


def application_dict(a: m.SupplierApplication) -> dict:
    return {k: getattr(a, k) for k in ("id", "company", "contact_name", "email", "phone", "website", "city", "kind", "sku_count", "categories", "message",
                                        "locale", "status", "note", "org_id")} | {"created_at": a.created_at.isoformat() if a.created_at else None}


@router.post("/api/v1/public/supplier-applications")
def apply_as_supplier(body: ApplicationIn, request: Request, db: Session = Depends(get_db)):
    rate_check(f"supplier-apply:{request.client.host if request.client else '-'}", 5, 3600)
    if not body.consent:
        raise ApiError(422, "validation", fields=["consent"])
    if body.hp:  # bot: pretend success, store nothing
        return {"ok": True}
    a = m.SupplierApplication(**body.model_dump(exclude={"consent", "hp"}))
    a.email = a.email.strip().lower()
    db.add(a)
    db.flush()
    from ..notify import notify, platform_staff

    notify(db, platform_staff(db), "catalog_alert", params={"source": a.company, "reason": "supplier_application"}, link="/app/admin?tab=applications")
    db.commit()
    return {"ok": True}


@router.get("/api/v1/admin/supplier-applications")
def list_applications(status: str = "", p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    stmt = select(m.SupplierApplication)
    if status:
        stmt = stmt.where(m.SupplierApplication.status == status)
    return [application_dict(a) for a in db.scalars(stmt.order_by(m.SupplierApplication.created_at.desc()).limit(300))]


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    note: str = Field(default="", max_length=1000)


@router.post("/api/v1/admin/supplier-applications/{aid}/decision")
def decide_application(aid: str, body: DecisionIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    """Approval creates the supplier organisation and its catalogue owner, and invites the contact as supplier admin."""
    a = db.get(m.SupplierApplication, aid)
    if not a:
        raise ApiError(404, "not_found")
    if a.status != "new":
        raise ApiError(409, "application.decided")
    a.status, a.note = body.decision, body.note
    if body.decision == "approved":
        from .manage import InviteIn, team_invite

        org = m.Organization(name=a.company, kind="supplier", settings={})
        db.add(org)
        db.flush()
        base = "".join(ch if ch.isalnum() else "-" for ch in a.company.lower()).strip("-")[:50] or "supplier"
        slug, n = base, 1
        while db.scalar(select(m.Supplier.id).where(m.Supplier.slug == slug)):
            n += 1
            slug = f"{base}-{n}"
        db.add(m.Supplier(name=a.company, slug=slug, kind=a.kind, city=a.city or "Ереван", website=a.website, org_id=org.id, is_demo=False, verification="pending",
                          contacts={"phone": a.phone, "email": a.email}))
        a.org_id = org.id
        default_plan = tariffs.get_tariffs(db).default_plan
        if default_plan and any(x.key == default_plan for x in tariffs.get_tariffs(db).supplier_plans):
            billing.assign_plan(db, org, default_plan)
        db.flush()
        team_invite(InviteIn(email=a.email, name=a.contact_name, role="supplier_admin", locale=a.locale), org_id=org.id, p=p, db=db)
    audit(db, p, f"supplier_application.{body.decision}", "supplier_application", aid, data={"company": a.company})
    db.commit()
    return application_dict(a)
