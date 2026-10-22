"""Estimate re-checks, supplier RFQ, cart and orders."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.connectors.others import build_connector
from ..catalog.discovery import source_dict, upsert_record
from ..commerce import orders as orders_svc
from ..commerce.payments import PaymentError, get_provider
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..ratelimit import check as rate_check
from ..scene.model import Scene
from ..security import Principal, audit, current_principal, project_access
from ..services import new_version

router = APIRouter(prefix="/api/v1/projects/{pid}", tags=["commerce"])


def _current(db, pid, vid):
    v = db.get(m.DesignVariant, vid)
    if not v or v.project_id != pid:
        raise ApiError(404, "variant.not_found")
    return v, db.get(m.DesignVersion, v.current_version_id)


@router.post("/variants/{vid}/recheck-prices")
def recheck_prices(pid: str, vid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """«Перепроверить цены и наличие»: refreshes external records (live when enabled), marks stale data,
    recomputes the estimate as a new version. Mandatory before RFQ/approval."""
    rate_check(f"recheck:{p.user.id}", 20, 3600)
    proj = project_access(pid, "project:write", p, db)
    v, ver = _current(db, pid, vid)
    s = get_settings()
    refreshed, stale, checked = 0, 0, 0
    now = datetime.now(timezone.utc)
    for ln in (ver.estimate or {}).get("lines", []):
        ref = ln.get("ref") or ""
        if not ref.startswith("ext:"):
            continue
        rec = db.get(m.ExternalProductRecord, ref[4:])
        if not rec:
            continue
        checked += 1
        src = db.get(m.ExternalSource, rec.source_id)
        conn = build_connector(source_dict(src), live=s.external_fetch_live, cache_lookup=None)
        fresh = None
        try:
            fresh = conn.refresh_product(rec.canonical_url)
        except Exception:  # noqa: BLE001
            fresh = None
        if fresh:
            upsert_record(db, fresh)
            refreshed += 1
        else:
            age_h = (now - (rec.retrieved_at if rec.retrieved_at.tzinfo else rec.retrieved_at.replace(tzinfo=timezone.utc))).total_seconds() / 3600
            if age_h > (src.ttl_h or {}).get("price", 24):
                data = dict(rec.data)
                data.setdefault("validation_warnings", []).append("Цена устарела (TTL истёк) — требуется подтверждение поставщика")
                rec.data = data
                stale += 1
    cs = ver.change_summary or {}
    new = new_version(db, proj, v, Scene.model_validate(ver.scene), selection=cs.get("selection", {}), extras=cs.get("extras"), source="manual",
                      note=f"Перепроверка цен: обновлено {refreshed}, устарело {stale}", user_id=p.user.id)
    db.commit()
    return {"checked_external": checked, "refreshed": refreshed, "stale": stale, "live_fetch": s.external_fetch_live, "version_id": new.id,
            "total": new.estimate["totals"]["known"], "message": None if s.external_fetch_live else
            "Live-проверка выключена (EXTERNAL_FETCH_LIVE=false): пересчитано по кэшу, устаревшие позиции помечены"}


@router.post("/variants/{vid}/estimate-snapshot")
def estimate_snapshot(pid: str, vid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:write", p, db)
    v, ver = _current(db, pid, vid)
    snap = m.EstimateSnapshot(project_id=pid, variant_id=vid, version_id=ver.id, reason="manual", data=ver.estimate)
    db.add(snap)
    db.commit()
    return {"id": snap.id, "created_at": snap.created_at.isoformat()}


# ------------------------------------------------------------------ RFQ
class RfqIn(BaseModel):
    variant_id: str
    supplier_keys: list[str] | None = None
    message: str = ""


def rfq_dict(r: m.RFQ) -> dict:
    return {"id": r.id, "supplier_name": r.supplier_name, "supplier_id": r.supplier_id, "status": r.status, "items": r.items, "message": r.message, "quote": r.quote,
            "created_at": r.created_at.isoformat(), "updated_at": r.updated_at.isoformat() if r.updated_at else None}


@router.get("/rfqs")
def list_rfqs(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    return [rfq_dict(r) for r in db.scalars(select(m.RFQ).where(m.RFQ.project_id == pid).order_by(m.RFQ.created_at.desc()))]


@router.post("/rfqs")
def create_rfqs(pid: str, body: RfqIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """One RFQ per supplier from the current version, after a fresh estimate snapshot."""
    proj = project_access(pid, "project:write", p, db)
    v, ver = _current(db, pid, body.variant_id)
    snap = m.EstimateSnapshot(project_id=pid, variant_id=v.id, version_id=ver.id, reason="rfq", data=ver.estimate)
    db.add(snap)
    db.flush()
    groups: dict[str, list[dict]] = defaultdict(list)
    names: dict[str, str] = {}
    for ln in (ver.estimate or {}).get("lines", []):
        key = ln.get("supplier_key")
        if not key or ln["group"] in ("delivery", "installation", "works", "contingency"):
            continue
        if body.supplier_keys and key not in body.supplier_keys:
            continue
        groups[key].append({k: ln.get(k) for k in ("id", "name", "sku", "qty", "unit", "unit_price", "price_status", "url", "note")})
        names[key] = ln.get("supplier") or key
    created = []
    for key, items in groups.items():
        sup = db.scalar(select(m.Supplier).where(m.Supplier.slug == key))
        demo = bool(sup and sup.is_demo)
        r = m.RFQ(project_id=pid, supplier_id=sup.id if sup else None, supplier_name=names[key], items=items, estimate_snapshot_id=snap.id,
                  message=body.message or f"Запрос актуального предложения по проекту «{proj.title}» ({len(items)} поз.)",
                  status="draft" if demo else "draft")
        db.add(r)
        created.append(r)
    audit(db, p, "rfq.create", "rfq", None, project_id=pid, data={"count": len(created)})
    db.commit()
    return [rfq_dict(r) for r in created]


@router.post("/rfqs/{rid}/send")
def send_rfq(pid: str, rid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "rfq:send", p, db)
    r = db.get(m.RFQ, rid)
    if not r or r.project_id != pid:
        raise ApiError(404, "not_found")
    sup = db.get(m.Supplier, r.supplier_id) if r.supplier_id else None
    if sup and sup.is_demo:
        raise ApiError(409, "rfq.demo_supplier")
    # Delivery channel (email/supplier portal/API) is pluggable; supplier cabinet sees it immediately.
    r.status = "sent"
    audit(db, p, "rfq.send", "rfq", rid, project_id=pid)
    db.commit()
    return rfq_dict(r)


# ------------------------------------------------------------------ cart / orders (P2-1)
def order_dict(db: Session, o: m.Order) -> dict:
    items = db.scalars(select(m.OrderItem).where(m.OrderItem.order_id == o.id)).all()
    quote = db.scalar(select(m.SupplierQuote).where(m.SupplierQuote.order_id == o.id).order_by(m.SupplierQuote.created_at.desc()).limit(1))
    d = db.scalar(select(m.Delivery).where(m.Delivery.order_id == o.id))
    inst = db.scalar(select(m.Installation).where(m.Installation.order_id == o.id))
    com = db.scalars(select(m.Commission).where(m.Commission.order_id == o.id)).all()
    return {"id": o.id, "supplier_name": o.supplier_name, "supplier_id": o.supplier_id, "status": o.status, "payment_status": o.payment_status,
            "items": [{"id": it.id, "ref": it.ref, "name": it.name, "sku": it.sku, "qty": it.qty, "unit": it.unit, "unit_price": it.unit_price, "total": it.total,
                       "price_status": it.price_status, "rechecked_price": it.rechecked_price, "url": it.url, "lead_days": it.lead_days} for it in items] or o.items,
            "totals": o.totals, "delivery": {**(o.delivery or {}), **({"status": d.status, "cost_amd": d.cost_amd} if d else {})},
            "installation": {**(o.installation or {}), **({"status": inst.status, "cost_amd": inst.cost_amd} if inst else {})},
            "quote": {"total_amd": quote.total_amd, "valid_until": quote.valid_until.isoformat(), "note": quote.note} if quote else None,
            "commissions": [{"party": c.party, "pct": c.pct, "amount_amd": c.amount_amd} for c in com],
            "history": o.history or [], "cart_id": o.cart_id, "created_at": o.created_at.isoformat(),
            "next": sorted(orders_svc.TRANSITIONS.get(o.status, {}))}


@router.get("/orders")
def list_orders(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    return [order_dict(db, o) for o in db.scalars(select(m.Order).where(m.Order.project_id == pid).order_by(m.Order.created_at))]


def cart_dict(c: m.Cart | None) -> dict | None:
    if not c:
        return None
    return {"id": c.id, "variant_id": c.variant_id, "status": c.status, "rechecked_at": c.rechecked_at.isoformat() if c.rechecked_at else None, "recheck": c.recheck or {},
            "recheck_max_age_h": get_settings().order_recheck_max_age_h}


@router.get("/cart")
def get_cart(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    c = db.scalar(select(m.Cart).where(m.Cart.project_id == pid).order_by(m.Cart.created_at.desc()).limit(1))
    return {"cart": cart_dict(c), "payments": payment_status()}


def payment_status() -> dict:
    prov = get_provider()
    return {"provider": prov.name, "status": "configured" if prov.configured() else prov.status}


class CartIn(BaseModel):
    variant_id: str


@router.post("/cart")
def build_cart(pid: str, body: CartIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Splits the approved estimate into per-supplier orders of one cart."""
    proj = project_access(pid, "project:write", p, db)
    v, ver = _current(db, pid, body.variant_id)
    if v.status != "approved":
        raise ApiError(409, "cart.requires_approval")
    snap = db.scalar(select(m.EstimateSnapshot).where(m.EstimateSnapshot.variant_id == v.id, m.EstimateSnapshot.reason == "approval").order_by(m.EstimateSnapshot.created_at.desc()).limit(1))
    cart, out = orders_svc.build_cart(db, proj, v, snap.data if snap else ver.estimate)
    audit(db, p, "cart.build", "cart", cart.id, project_id=pid, data={"orders": len(out)})
    db.commit()
    return [order_dict(db, o) for o in out]


@router.post("/cart/recheck")
def recheck_cart(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Mandatory before ordering: re-reads current prices and availability of every cart item."""
    project_access(pid, "project:write", p, db)
    c = db.scalar(select(m.Cart).where(m.Cart.project_id == pid, m.Cart.status == "open").order_by(m.Cart.created_at.desc()).limit(1))
    if not c:
        raise ApiError(404, "cart.not_found")
    r = orders_svc.recheck_cart(db, c)
    audit(db, p, "cart.recheck", "cart", c.id, project_id=pid, data={"changed": len(r["changed"]), "unavailable": len(r["unavailable"]), "delta_amd": r["delta_amd"]})
    db.commit()
    return cart_dict(c)


def _order(db: Session, pid: str, oid: str) -> m.Order:
    o = db.get(m.Order, oid)
    if not o or o.project_id != pid:
        raise ApiError(404, "not_found")
    return o


@router.post("/orders/{oid}/request")
def request_order(pid: str, oid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
                  idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    proj = project_access(pid, "project:write", p, db)
    o = _order(db, pid, oid)
    made = [i for i in db.scalars(select(m.OrderItem).where(m.OrderItem.order_id == o.id)) if "изготов" in (i.name or "").lower()]
    if proj.accuracy_level != "production" and made:
        raise ApiError(409, "order.made_to_measure_requires_production")
    orders_svc.request(db, o, actor=p.user.email, idempotency_key=idempotency_key)
    audit(db, p, "order.request", "order", oid, project_id=pid)
    _notify_supplier(db, o)
    db.commit()
    return order_dict(db, o)


class TransitionIn(BaseModel):
    to: str
    note: str = ""


@router.post("/orders/{oid}/transition")
def bureau_transition(pid: str, oid: str, body: TransitionIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Bureau-side moves: cancel, dispute, close after delivery / installation."""
    project_access(pid, "project:write", p, db)
    o = _order(db, pid, oid)
    if body.to == "requested":
        raise ApiError(409, "order.bad_transition", frm=o.status, to=body.to)
    orders_svc.transition(db, o, body.to, side="bureau", actor=p.user.email, note=body.note)
    audit(db, p, f"order.{body.to}", "order", oid, project_id=pid, data={"note": body.note[:200]})
    _notify_supplier(db, o)
    db.commit()
    return order_dict(db, o)


@router.post("/orders/{oid}/pay")
def pay_order(pid: str, oid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db),
              idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    """Starts a hosted payment with the contracted provider. Without one → 409 payment.integration_pending
    (the UI shows «Integration pending»; nothing is marked paid)."""
    project_access(pid, "project:write", p, db)
    o = _order(db, pid, oid)
    prov = get_provider()
    if not prov.configured():
        raise ApiError(409, "payment.integration_pending", provider=prov.name)
    if o.payment_status == "paid":
        raise ApiError(409, "payment.already_paid")
    amount = orders_svc.payable_amd(db, o)
    key = idempotency_key or f"pay:{o.id}:{amount}"
    existing = db.scalar(select(m.Payment).where(m.Payment.idempotency_key == key))
    if existing:
        return {"payment_id": existing.id, "status": existing.status, "redirect_url": None}
    s = get_settings()
    try:
        r = prov.create_payment(order_id=o.id, amount_amd=amount, idempotency_key=key, return_url=f"{s.public_base_url.rstrip('/')}/app/p/{pid}/procurement")
    except PaymentError as e:
        raise ApiError(502, "payment.provider_error", info=str(e)[:200]) from e
    pay = m.Payment(order_id=o.id, provider=prov.name, provider_ref=r["provider_ref"], amount_amd=amount, idempotency_key=key)
    db.add(pay)
    o.payment_status = "pending"
    audit(db, p, "order.pay", "order", oid, project_id=pid, data={"amount_amd": amount, "provider": prov.name})
    db.commit()
    return {"payment_id": pay.id, "status": pay.status, "redirect_url": r.get("redirect_url")}


def _notify_supplier(db: Session, o: m.Order) -> None:
    from ..notify import notify

    if not o.supplier_id:
        return
    sup = db.get(m.Supplier, o.supplier_id)
    staff = [ms.user for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == sup.org_id))] if sup and sup.org_id else []
    notify(db, staff, "order_update", params={"supplier": o.supplier_name, "status": o.status}, link="/app/supplier")
