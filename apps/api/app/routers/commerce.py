"""Estimate re-checks, supplier RFQ, cart and orders."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.connectors.others import build_connector
from ..catalog.discovery import source_dict, upsert_record
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
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


# ------------------------------------------------------------------ cart / orders
@router.get("/orders")
def list_orders(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    return [order_dict(o) for o in db.scalars(select(m.Order).where(m.Order.project_id == pid).order_by(m.Order.created_at))]


def order_dict(o: m.Order) -> dict:
    return {"id": o.id, "supplier_name": o.supplier_name, "status": o.status, "items": o.items, "totals": o.totals, "delivery": o.delivery,
            "installation": o.installation, "created_at": o.created_at.isoformat()}


class CartIn(BaseModel):
    variant_id: str


@router.post("/cart")
def build_cart(pid: str, body: CartIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Splits the approved estimate into per-supplier carts (MVP: request-for-quote checkout)."""
    proj = project_access(pid, "project:write", p, db)
    v, ver = _current(db, pid, body.variant_id)
    if v.status != "approved":
        raise ApiError(409, "cart.requires_approval")
    snap = db.scalar(select(m.EstimateSnapshot).where(m.EstimateSnapshot.variant_id == v.id, m.EstimateSnapshot.reason == "approval").order_by(m.EstimateSnapshot.created_at.desc()).limit(1))
    est = snap.data if snap else ver.estimate
    db.query(m.Order).filter(m.Order.project_id == pid, m.Order.status == "cart").delete()
    groups: dict[str, list[dict]] = defaultdict(list)
    for ln in est.get("lines", []):
        if ln.get("supplier_key") and ln["group"] not in ("works", "contingency"):
            groups[ln["supplier_key"]].append(ln)
    out = []
    for key, lines in groups.items():
        goods = [x for x in lines if x["group"] not in ("delivery", "installation")]
        sup = db.scalar(select(m.Supplier).where(m.Supplier.slug == key))
        totals = {"goods": sum(x["total"] or 0 for x in goods), "delivery": sum(x["total"] or 0 for x in lines if x["group"] == "delivery"),
                  "installation": sum(x["total"] or 0 for x in lines if x["group"] == "installation"), "quote_required": sum(1 for x in goods if x["total"] is None)}
        totals["commission_platform"] = round(totals["goods"] * ((sup.commission_pct if sup else 0) / 100))
        o = m.Order(project_id=pid, supplier_id=sup.id if sup else None, supplier_name=lines[0].get("supplier") or key, status="cart",
                    items=[{k: x.get(k) for k in ("id", "name", "sku", "qty", "unit", "unit_price", "total", "price_status", "url", "lead_days")} for x in goods],
                    totals=totals, delivery=(sup.delivery if sup else {}), installation=(sup.installation if sup else {}))
        db.add(o)
        out.append(o)
    db.commit()
    _ = proj
    return [order_dict(o) for o in out]


@router.post("/orders/{oid}/request")
def request_order(pid: str, oid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    o = db.get(m.Order, oid)
    if not o or o.project_id != pid:
        raise ApiError(404, "not_found")
    sup = db.get(m.Supplier, o.supplier_id) if o.supplier_id else None
    if sup and sup.is_demo:
        raise ApiError(409, "order.demo_supplier")
    made = [i for i in o.items if "изготов" in (i.get("name") or "").lower()]
    if proj.accuracy_level != "production" and made:
        raise ApiError(409, "order.made_to_measure_requires_production")
    o.status = "requested"
    audit(db, p, "order.request", "order", oid, project_id=pid)
    db.commit()
    return order_dict(o)
