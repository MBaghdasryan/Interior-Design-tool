"""Payment provider webhooks (public, signature-verified, idempotent) and the platform ledger."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m
from ..commerce import ledger, tariffs
from ..commerce import orders as orders_svc
from ..commerce.payments import PaymentError, get_provider
from ..db import get_db
from ..errors import ApiError
from ..security import Principal, audit, require

router = APIRouter(tags=["payments"])


@router.post("/api/v1/payments/webhook/{provider}")
async def webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    prov = get_provider()
    if prov.name != provider or not prov.configured():
        raise ApiError(404, "not_found")
    body = await request.body()
    try:
        ev = prov.verify_webhook(dict(request.headers), body)
    except PaymentError as e:
        raise ApiError(400, str(e)) from None
    try:  # each provider event is processed once
        db.add(m.ProcessedWebhook(id=f"{provider}:{ev.id}"))
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"ok": True, "duplicate": True}
    pay = db.scalar(select(m.Payment).where(m.Payment.provider == provider, m.Payment.provider_ref == ev.provider_ref))
    if not pay:
        db.commit()
        return {"ok": True, "ignored": "unknown payment"}
    o = db.get(m.Order, pay.order_id)
    if ev.type == "payment.succeeded" and pay.status == "pending":
        if ev.amount_amd != pay.amount_amd:
            db.add(m.AuditEvent(project_id=o.project_id, action="payment.amount_mismatch", entity="payment", entity_id=pay.id,
                                data={"expected": pay.amount_amd, "received": ev.amount_amd}))
            db.commit()
            raise ApiError(409, "payment.amount_mismatch")
        orders_svc.record_capture(db, o, pay)
    elif ev.type == "payment.refunded" and pay.status == "captured":
        orders_svc.record_refund(db, o, pay)
    elif ev.type == "payment.failed" and pay.status == "pending":
        pay.status = "failed"
        o.payment_status = "none"
    db.add(m.AuditEvent(project_id=o.project_id, action=f"payment.{ev.type.split('.')[-1]}", entity="payment", entity_id=pay.id, data={"event": ev.id}))
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ platform ledger
@router.get("/api/v1/admin/ledger")
def ledger_overview(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return {"balances": ledger.balances(db), "reconcile": ledger.reconcile(db), "revenue": ledger.revenue_by_stream(db),
            "payments": {"provider": get_provider().name, "configured": get_provider().configured()}}


@router.get("/api/v1/admin/ledger/export.csv")
def ledger_export_csv(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return Response(ledger.export_csv(db), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="ledger.csv"'})


@router.get("/api/v1/admin/ledger/export.xlsx")
def ledger_export_xlsx(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return Response(ledger.export_xlsx(db), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="ledger.xlsx"'})


class PayoutIn(BaseModel):
    supplier_id: str
    amount_amd: int = Field(gt=0)
    reference: str = Field(min_length=3, max_length=200)  # bank transfer reference — the transfer itself happens outside the platform


@router.post("/api/v1/admin/payouts")
def create_payout(body: PayoutIn, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    po = orders_svc.record_payout(db, body.supplier_id, body.amount_amd, reference=body.reference, idempotency_key=f"payout:{body.supplier_id}:{body.reference}")
    audit(db, p, "payout.record", "supplier", body.supplier_id, data={"amount_amd": body.amount_amd, "reference": body.reference})
    db.commit()
    return {"id": po.id, "supplier_id": po.supplier_id, "amount_amd": po.amount_amd, "status": po.status, "txn_id": po.txn_id}


class CommerceSettingsIn(BaseModel):
    tax_rate_pct: float = Field(default=0.0, ge=0, le=50)
    designer_commission_pct: float = Field(default=0.0, ge=0, le=30)


@router.get("/api/v1/admin/commerce-settings")
def get_commerce_settings(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return orders_svc.commerce_settings(db)


@router.put("/api/v1/admin/commerce-settings")
def put_commerce_settings(body: CommerceSettingsIn, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    row = db.get(m.PlatformSetting, "commerce") or m.PlatformSetting(key="commerce", value={})
    row.value = {**(row.value or {}), **body.model_dump()}
    db.merge(row)
    audit(db, p, "commerce.settings", "platform_setting", "commerce", data=body.model_dump())
    db.commit()
    return orders_svc.commerce_settings(db)


# ------------------------------------------------------------------ business model (P2-2)
@router.get("/api/v1/admin/tariffs")
def get_tariffs(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return tariffs.get_tariffs(db).model_dump()


@router.put("/api/v1/admin/tariffs")
def put_tariffs(body: tariffs.Tariffs, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    try:
        t = tariffs.set_tariffs(db, body)
    except ValueError as e:
        raise ApiError(422, "validation", fields=["bureau_plans"], info=str(e)) from None
    audit(db, p, "tariffs.update", "platform_setting", "tariffs", data={"plans": len(t.bureau_plans), "packs": len(t.credit_packs)})
    db.commit()
    return t.model_dump()


@router.get("/api/v1/admin/revenue")
def revenue(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return tariffs.revenue_report(db)


class ManualRevenueIn(BaseModel):
    stream: str = Field(pattern="^(subscription|credits|procurement|manufacturer|leads|white_label|exports)$")
    amount_amd: int = Field(gt=0)
    reference: str = Field(min_length=3, max_length=200)  # invoice / bank transfer id of money actually received
    org_id: str | None = None


@router.post("/api/v1/admin/revenue/manual")
def record_manual_revenue(body: ManualRevenueIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    """Records money received outside a payment provider (bank transfer against an invoice). Idempotent by reference."""
    txn = ledger.post(db, body.stream, [("cash", body.amount_amd, 0), (f"revenue:{body.stream}", 0, body.amount_amd)],
                      idempotency_key=f"manual:{body.stream}:{body.reference}", memo=f"{body.reference} {body.org_id or ''}".strip())
    audit(db, p, "revenue.manual", "ledger", txn, data=body.model_dump())
    db.commit()
    return {"txn_id": txn}


class OrgPlanIn(BaseModel):
    plan: str | None = None


@router.put("/api/v1/admin/orgs/{org_id}/plan")
def set_org_plan(org_id: str, body: OrgPlanIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    """Platform assignment (invoice, pilot agreement) — no card payment, no paid period."""
    from ..commerce.billing import assign_plan

    org = db.get(m.Organization, org_id)
    if not org:
        raise ApiError(404, "not_found")
    if body.plan and body.plan not in {x.key for x in tariffs.plans_for(tariffs.get_tariffs(db), org.kind)}:
        raise ApiError(422, "validation", fields=["plan"])
    assign_plan(db, org, body.plan)
    audit(db, p, "org.plan", "organization", org_id, data={"plan": body.plan})
    db.commit()
    return tariffs.plan_usage(db, org)


@router.get("/api/v1/admin/orgs")
def list_orgs(p: Principal = Depends(require("audit:read")), db: Session = Depends(get_db)):
    return [{"id": o.id, "name": o.name, "kind": o.kind, "plan": (o.settings or {}).get("plan")} for o in db.scalars(select(m.Organization).order_by(m.Organization.name))]


@router.get("/api/v1/bureau/plan")
def my_plan(p: Principal = Depends(require("project:read")), db: Session = Depends(get_db)):
    org_id = next(iter(p.org_ids), None)
    org = db.get(m.Organization, org_id) if org_id else None
    if not org:
        raise ApiError(404, "not_found")
    return tariffs.plan_usage(db, org)
