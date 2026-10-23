"""Cross-project workspace sections: the order registry (all orders of the organisation, mockup 32)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import false, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..security import Principal, current_principal
from .commerce import order_dict

router = APIRouter(prefix="/api/v1", tags=["workspace"])

ACTIVE = ("requested", "confirmed", "in_production", "delivering", "installing", "disputed")
# stage chain shown per order: the status that completes the stage, in order
STAGES = [("confirmed", "confirmed"), ("production", "in_production"), ("delivery", "delivering"), ("installation", "installing"), ("closed", "closed")]
RANK = {"requested": 0, "confirmed": 1, "in_production": 2, "delivering": 3, "installing": 4, "closed": 5}


def _order_scope(p: Principal, db: Session):
    """Platform admin: all orders; bureau staff: orders of their organisations' projects; supplier staff: orders to their supplier."""
    stmt = select(m.Order).where(m.Order.status != "cart")
    if p.is_platform_admin:
        return stmt
    sup_ids = list(db.scalars(select(m.Supplier.id).where(m.Supplier.org_id.in_(p.org_ids)))) if p.org_ids else []
    proj_ids = select(m.Project.id).where(m.Project.org_id.in_(p.org_ids))
    return stmt.where(or_(m.Order.project_id.in_(proj_ids), m.Order.supplier_id.in_(sup_ids) if sup_ids else false()))


def _amount(d: dict) -> int:
    if d.get("quote"):
        return int(d["quote"]["total_amd"] or 0)
    t = d.get("totals") or {}
    return int((t.get("goods") or 0) + (t.get("delivery") or 0) + (t.get("installation") or 0))


def _stages(o: m.Order) -> list[dict]:
    reached = {h.get("to"): h.get("at") for h in (o.history or [])}
    r = RANK.get(o.status, -1)
    out = []
    for key, status in STAGES:
        done = RANK.get(status, 99) <= r or status in reached
        cur = RANK.get(status) == r + 1 and o.status not in ("cancelled", "refunded", "disputed")
        out.append({"key": key, "state": "done" if done else ("current" if cur else "planned"), "at": reached.get(status)})
    return out


@router.get("/orders")
def order_registry(status: str = "", supplier_id: str = "", project_id: str = "", q: str = "", days: int = Query(0, ge=0, le=3650),
                   p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    stmt = _order_scope(p, db)
    if status == "active":
        stmt = stmt.where(m.Order.status.in_(ACTIVE))
    elif status:
        stmt = stmt.where(m.Order.status == status)
    if supplier_id:
        stmt = stmt.where(m.Order.supplier_id == supplier_id)
    if project_id:
        stmt = stmt.where(m.Order.project_id == project_id)
    if days:
        stmt = stmt.where(m.Order.created_at >= datetime.now(timezone.utc) - timedelta(days=days))
    orders = db.scalars(stmt.order_by(m.Order.created_at.desc()).limit(500)).all()
    projects = {x.id: x for x in db.scalars(select(m.Project).where(m.Project.id.in_({o.project_id for o in orders})))} if orders else {}
    items = []
    for o in orders:
        pr = projects.get(o.project_id)
        if q and q.lower() not in f"{o.supplier_name} {pr.title if pr else ''} {o.id[:6]}".lower():
            continue
        d = order_dict(db, o)
        d.update(number=o.id[:6].upper(), project_id=o.project_id, project_title=pr.title if pr else "", city=pr.city if pr else "", amount_amd=_amount(d),
                 stages=_stages(o), positions=len(d["items"]))
        items.append(d)
    by_supplier: dict[str, dict] = defaultdict(lambda: {"name": "", "count": 0, "amount_amd": 0})
    for d in items:
        g = by_supplier[d["supplier_id"] or d["supplier_name"]]
        g["name"], g["count"], g["amount_amd"] = d["supplier_name"], g["count"] + 1, g["amount_amd"] + d["amount_amd"]
    now = datetime.now(timezone.utc)

    def monthly(pred) -> list[int]:
        out = [0] * 6
        for d in items:
            if not pred(d):
                continue
            c = datetime.fromisoformat(d["created_at"])
            c = c if c.tzinfo else c.replace(tzinfo=timezone.utc)
            k = (now.year - c.year) * 12 + now.month - c.month
            if 0 <= k < 6:
                out[5 - k] += 1
        return out
    kpi = {"active": sum(1 for d in items if d["status"] in ACTIVE), "in_production": sum(1 for d in items if d["status"] == "in_production"),
           "delivering": sum(1 for d in items if d["status"] == "delivering"), "installing": sum(1 for d in items if d["status"] == "installing"),
           "closed": sum(1 for d in items if d["status"] == "closed"), "amount_amd": sum(d["amount_amd"] for d in items if d["status"] not in ("cancelled", "refunded")),
           "series": {"active": monthly(lambda d: d["status"] in ACTIVE), "all": monthly(lambda d: True)}}
    return {"items": items, "kpi": kpi, "suppliers": [{"key": k, **v} for k, v in sorted(by_supplier.items(), key=lambda x: -x[1]["amount_amd"])]}
