"""Supplier cabinet (Store Partner), bureau cabinet and the public Client Viewer."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..errors import ApiError
from ..scene.model import Scene
from ..scene.svg import render_svg
from ..security import Principal, audit, current_principal, require
from ..services import project_dict, variant_dict, version_dict

router = APIRouter(tags=["partners"])


# ------------------------------------------------------------------ supplier cabinet
def _supplier_for(p: Principal, db: Session, supplier_id: str | None = None) -> m.Supplier:
    """The caller's supplier; platform staff open any supplier's cabinet by supplier_id."""
    if supplier_id and p.is_platform:
        sup = db.get(m.Supplier, supplier_id)
        if not sup:
            raise ApiError(404, "supplier.not_linked")
        return sup
    sup = db.scalar(select(m.Supplier).where(m.Supplier.org_id.in_(p.org_ids)).limit(1)) if p.org_ids else None
    if not sup:
        raise ApiError(404, "supplier.not_linked")
    return sup


@router.get("/api/v1/supplier/overview")
def supplier_overview(supplier_id: str | None = None, p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    sup = _supplier_for(p, db, supplier_id)
    variants = db.scalars(select(m.ProductVariant).join(m.Product).where(m.Product.supplier_id == sup.id, m.Product.status == "active")).all()
    refs = {f"pv:{v.id}": v for v in variants}
    used = Counter()
    projects = set()
    for ver in db.scalars(select(m.DesignVersion)):
        for o in (ver.scene or {}).get("objects", []):
            if o.get("product_variant_id") in refs:
                used[o["product_variant_id"]] += 1
                projects.add(ver.variant_id)
    top = [{"sku": refs[r].sku, "name": refs[r].product.name_ru, "placements": n, "image_url": refs[r].image_url, "category": refs[r].product.category,
            "price": refs[r].price, "color_hex": refs[r].color_hex} for r, n in used.most_common(10)]
    rfqs = db.scalars(select(m.RFQ).where(m.RFQ.supplier_id == sup.id).order_by(m.RFQ.created_at.desc()).limit(50)).all()
    from datetime import datetime, timedelta, timezone

    stale_before = datetime.now(timezone.utc) - timedelta(days=14)
    orders = db.scalars(select(m.Order).where(m.Order.supplier_id == sup.id, m.Order.status != "cart")).all()

    def _old(d):
        return d is None or (d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d) < stale_before
    attention = {"rfq_new": sum(1 for r in rfqs if r.status == "sent"), "orders_to_confirm": sum(1 for o in orders if o.status == "requested"),
                 "stale_prices": sum(1 for v in variants if v.price is not None and _old(v.price_checked_at)), "no_dims": sum(1 for v in variants if not v.width_mm)}
    active_orders = sum(1 for o in orders if o.status not in ("closed", "cancelled", "refunded"))
    return {"supplier": {"id": sup.id, "org_id": sup.org_id, "name": sup.name, "is_demo": sup.is_demo, "commission_pct": sup.commission_pct, "delivery": sup.delivery,
                         "verification": sup.verification},
            "products": len(variants), "with_price": sum(1 for v in variants if v.price is not None), "with_dims": sum(1 for v in variants if v.width_mm),
            "with_3d": sum(1 for v in variants if v.model3d_url), "in_stock": sum(1 for v in variants if v.stock_status == "in_stock"),
            "placements": sum(used.values()), "variants_using": len(projects), "top": top, "attention": attention, "active_orders": active_orders,
            "rfqs": [{"id": r.id, "status": r.status, "items": len(r.items), "created_at": r.created_at.isoformat(), "message": r.message} for r in rfqs]}


@router.get("/api/v1/supplier/demand")
def supplier_demand(supplier_id: str | None = None, p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    """Where the supplier's products are used and who asked for them. Client data (name, address, project title) is not
    disclosed: the supplier sees the bureau, city, area and items; contact comes through a request or an order."""
    sup = _supplier_for(p, db, supplier_id)
    refs = {f"pv:{v.id}": v for v in db.scalars(select(m.ProductVariant).join(m.Product).where(m.Product.supplier_id == sup.id))}
    by_project: dict[str, Counter] = {}
    rows = db.execute(select(m.DesignVersion, m.DesignVariant.project_id).join(m.DesignVariant, m.DesignVariant.current_version_id == m.DesignVersion.id)
                      .where(m.DesignVariant.status != "archived"))
    for ver, pid in rows:
        for o in (ver.scene or {}).get("objects", []):
            if o.get("product_variant_id") in refs:
                by_project.setdefault(pid, Counter())[o["product_variant_id"]] += 1
    rfqs = db.scalars(select(m.RFQ).where(m.RFQ.supplier_id == sup.id, m.RFQ.status != "draft").order_by(m.RFQ.created_at.desc()).limit(200)).all()
    orders = db.scalars(select(m.Order).where(m.Order.supplier_id == sup.id, m.Order.status != "cart")).all()
    pids = set(by_project) | {r.project_id for r in rfqs} | {o.project_id for o in orders}
    projects = {pr.id: pr for pr in db.scalars(select(m.Project).where(m.Project.id.in_(pids)))} if pids else {}
    orgs = {o.id: o.name for o in db.scalars(select(m.Organization).where(m.Organization.id.in_({pr.org_id for pr in projects.values()})))} if projects else {}

    def ref(pid: str) -> dict:
        pr = projects.get(pid)
        return {"ref": f"P-{pid[:6].upper()}", "bureau": orgs.get(pr.org_id, "") if pr else "", "city": pr.city if pr else "", "area_m2": pr.area_m2 if pr else None}

    stage = {}
    for r in rfqs:
        stage[r.project_id] = "request"
    for o in orders:
        stage[o.project_id] = "order"
    usage = []
    for pid, cnt in by_project.items():
        pr = projects.get(pid)
        if not pr:
            continue
        usage.append({**ref(pid), "stage": stage.get(pid, "design"), "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                      "items": [{"sku": refs[k].sku, "name": refs[k].product.name_ru, "qty": n} for k, n in cnt.most_common()]})
    usage.sort(key=lambda x: x["updated_at"] or "", reverse=True)
    return {"usage": usage,
            "requests": [{"id": r.id, **ref(r.project_id), "status": r.status, "created_at": r.created_at.isoformat(), "message": r.message,
                          "items": [{"sku": it.get("sku"), "name": it.get("name"), "qty": it.get("qty"), "unit": it.get("unit")} for it in r.items]} for r in rfqs],
            "counts": {"projects": len(usage), "requests": sum(1 for r in rfqs if r.status == "sent"), "orders": len(orders)}}


# ------------------------------------------------------------------ supplier orders (P2-1)
@router.get("/api/v1/supplier/orders")
def supplier_orders(supplier_id: str | None = None, p: Principal = Depends(require("rfq:respond")), db: Session = Depends(get_db)):
    from .commerce import order_dict

    sup = _supplier_for(p, db, supplier_id)
    rows = db.scalars(select(m.Order).where(m.Order.supplier_id == sup.id, m.Order.status != "cart").order_by(m.Order.created_at.desc()).limit(100)).all()
    return [order_dict(db, o) | {"project_id": o.project_id} for o in rows]


def _supplier_order(p: Principal, db: Session, oid: str, supplier_id: str | None = None) -> m.Order:
    sup = _supplier_for(p, db, supplier_id)
    o = db.get(m.Order, oid)
    if not o or o.supplier_id != sup.id or o.status == "cart":
        raise ApiError(404, "not_found")
    return o


class ConfirmIn(BaseModel):
    total_amd: int = Field(gt=0)
    valid_days: int = Field(default=7, ge=1, le=60)
    note: str = Field(default="", max_length=500)


@router.post("/api/v1/supplier/orders/{oid}/confirm")
def supplier_confirm(oid: str, body: ConfirmIn, supplier_id: str | None = None, p: Principal = Depends(require("rfq:respond")), db: Session = Depends(get_db)):
    from ..commerce import orders as orders_svc
    from ..notify import notify, project_people
    from .commerce import order_dict

    o = _supplier_order(p, db, oid, supplier_id)
    orders_svc.confirm(db, o, total_amd=body.total_amd, valid_days=body.valid_days, actor=p.user.email, note=body.note)
    audit(db, p, "order.confirmed", "order", oid, project_id=o.project_id, data={"total_amd": body.total_amd})
    proj = db.get(m.Project, o.project_id)
    notify(db, project_people(db, proj), "order_update", params={"supplier": o.supplier_name, "status": o.status}, link=f"/app/p/{proj.id}/procurement", project_id=proj.id)
    db.commit()
    return order_dict(db, o)


class SupplierStatusIn(BaseModel):
    to: str = Field(pattern="^(in_production|delivering|installing|cancelled)$")
    note: str = Field(default="", max_length=300)


@router.post("/api/v1/supplier/orders/{oid}/status")
def supplier_status(oid: str, body: SupplierStatusIn, supplier_id: str | None = None, p: Principal = Depends(require("rfq:respond")), db: Session = Depends(get_db)):
    from ..commerce import orders as orders_svc
    from ..notify import notify, project_people
    from .commerce import order_dict

    o = _supplier_order(p, db, oid, supplier_id)
    orders_svc.transition(db, o, body.to, side="supplier", actor=p.user.email, note=body.note)
    audit(db, p, f"order.{body.to}", "order", oid, project_id=o.project_id)
    proj = db.get(m.Project, o.project_id)
    notify(db, project_people(db, proj), "order_update", params={"supplier": o.supplier_name, "status": o.status}, link=f"/app/p/{proj.id}/procurement", project_id=proj.id)
    db.commit()
    return order_dict(db, o)


class FeedIn(BaseModel):
    enabled: bool = False
    url: str = Field(default="", max_length=500)
    interval_h: int = Field(default=24, ge=6, le=168)
    max_price_change_pct: float = Field(default=60.0, ge=5, le=500)


def _feed_out(sup: m.Supplier) -> dict:
    from ..catalog.maintenance import feed_cfg

    f = feed_cfg(sup)
    return {k: f.get(k) for k in ("enabled", "url", "interval_h", "max_price_change_pct", "last_sync_at", "last_status")} | {"history": (f.get("history") or [])[:10]}


@router.get("/api/v1/supplier/feed")
def get_feed(supplier_id: str | None = None, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    return _feed_out(_supplier_for(p, db, supplier_id))


@router.put("/api/v1/supplier/feed")
def put_feed(body: FeedIn, supplier_id: str | None = None, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    from urllib.parse import urlparse

    sup = _supplier_for(p, db, supplier_id)
    u = urlparse(body.url)
    if body.url and (u.scheme != "https" or not u.hostname):
        raise ApiError(422, "validation", fields=["url"])
    if body.enabled and not body.url:
        raise ApiError(422, "validation", fields=["url"])
    sup.feed = {**(sup.feed or {}), **body.model_dump()}
    audit(db, p, "supplier.feed_update", "supplier", sup.id, data={"enabled": body.enabled, "host": u.hostname, "interval_h": body.interval_h})
    db.commit()
    return _feed_out(sup)


@router.post("/api/v1/supplier/feed/sync")
def sync_feed_now(supplier_id: str | None = None, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    from ..jobs.runner import enqueue, job_dict

    sup = _supplier_for(p, db, supplier_id)
    if not (sup.feed or {}).get("url"):
        raise ApiError(422, "validation", fields=["url"])
    job = enqueue(db, "supplier_feed", project_id=None, params={"supplier_id": sup.id})
    audit(db, p, "supplier.feed_sync", "supplier", sup.id)
    db.commit()
    return job_dict(job)


class QuoteIn(BaseModel):
    status: str = Field(pattern="^(quoted|declined)$")
    total_amd: float | None = None
    valid_days: int = 7
    comment: str = ""


@router.post("/api/v1/supplier/rfqs/{rid}/respond")
def respond_rfq(rid: str, body: QuoteIn, supplier_id: str | None = None, p: Principal = Depends(require("rfq:respond")), db: Session = Depends(get_db)):
    sup = _supplier_for(p, db, supplier_id)
    r = db.get(m.RFQ, rid)
    if not r or r.supplier_id != sup.id:
        raise ApiError(404, "not_found")
    r.status = body.status
    r.quote = body.model_dump()
    from ..notify import notify, project_people

    proj = db.get(m.Project, r.project_id)
    if proj:
        notify(db, project_people(db, proj), "rfq_reply", params={"supplier": r.supplier_name, "project": proj.title}, link=f"/app/p/{proj.id}/procurement", project_id=proj.id)
    db.commit()
    return {"ok": True}


@router.get("/api/v1/supplier/products")
def supplier_products(supplier_id: str | None = None, p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    sup = _supplier_for(p, db, supplier_id)
    out = []
    for v in db.scalars(select(m.ProductVariant).join(m.Product).where(m.Product.supplier_id == sup.id, m.Product.status == "active").limit(2000)):
        out.append({"id": v.id, "product_id": v.product_id, "sku": v.sku, "name": v.product.name_ru, "category": v.product.category, "price": v.price, "price_status": v.price_status,
                    "stock": v.stock_status, "dims": [v.width_mm, v.depth_mm, v.height_mm], "has_3d": bool(v.model3d_url), "color_hex": v.color_hex})
    return out


# ------------------------------------------------------------------ bureau cabinet
@router.get("/api/v1/bureau/overview")
def bureau_overview(org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _bureau_org(p, db, org_id)
    members = db.scalars(select(m.Membership).where(m.Membership.org_id == org.id)).all()
    projects = db.scalars(select(m.Project).where(m.Project.org_id == org.id).order_by(m.Project.updated_at.desc())).all()
    from .projects import _cover

    totals = {v.project_id: (v.metrics or {}).get("total") for v in db.scalars(select(m.DesignVariant).where(
        m.DesignVariant.project_id.in_([x.id for x in projects]), m.DesignVariant.status.in_(["selected", "approved"])))}
    return {"org": {"id": org.id, "name": org.name, "settings": org.settings},
            "members": [{"name": ms.user.name, "email": ms.user.email, "role": ms.role} for ms in members],
            "projects": [{**project_dict(x), "cover": _cover(db, x.id), "total": totals.get(x.id)} for x in projects],
            "status_counts": dict(Counter(x.status for x in projects)),
            "pipeline_value": sum((v.metrics or {}).get("total", 0) for v in db.scalars(select(m.DesignVariant).where(
                m.DesignVariant.project_id.in_([x.id for x in projects]), m.DesignVariant.status.in_(["selected", "approved"]))))}


def _bureau_org(p: Principal, db: Session, org_id: str | None = None) -> m.Organization:
    """The caller's bureau; platform staff open any bureau's cabinet by org_id."""
    if org_id and p.is_platform_admin:
        org = db.get(m.Organization, org_id)
        if not org or org.kind != "bureau":
            raise ApiError(404, "bureau.not_found")
        return org
    org = next((o for o in (db.get(m.Organization, oid) for oid in p.org_ids) if o and o.kind == "bureau"), None)
    if not org:
        raise ApiError(404, "bureau.not_found")
    return org


@router.get("/api/v1/bureau/ai-usage")
def bureau_ai_usage(org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """AI spend of the organisation (today / month, by task and provider) against its budget."""
    from ..ai.budget import summary

    return summary(db, _bureau_org(p, db, org_id).id)


class AiBudgetIn(BaseModel):
    daily_usd: float = Field(ge=0, le=10_000)
    monthly_usd: float = Field(ge=0, le=100_000)


@router.put("/api/v1/bureau/ai-budget")
def bureau_ai_budget(body: AiBudgetIn, org_id: str | None = None, p: Principal = Depends(require("team:manage")), db: Session = Depends(get_db)):
    from ..ai.budget import summary

    org = _bureau_org(p, db, org_id)
    org.settings = {**(org.settings or {}), "ai_budget": body.model_dump()}
    audit(db, p, "bureau.ai_budget", "organization", org.id, org_id=org.id, data=body.model_dump())
    db.commit()
    return summary(db, org.id)


class OrgSettingsIn(BaseModel):
    title_block: dict


@router.put("/api/v1/bureau/settings")
def bureau_settings(body: OrgSettingsIn, org_id: str | None = None, p: Principal = Depends(require("team:manage")), db: Session = Depends(get_db)):
    org = _bureau_org(p, db, org_id)
    org.settings = {**(org.settings or {}), "title_block": body.title_block}
    audit(db, p, "bureau.settings", "organization", org.id, org_id=org.id)
    db.commit()
    return org.settings


# ------------------------------------------------------------------ public client viewer (share token)
def _by_token(token: str, db: Session) -> m.Project:
    proj = db.scalar(select(m.Project).where(m.Project.share_token == token))
    if not proj:
        raise ApiError(404, "share.invalid")
    return proj


@router.get("/api/v1/client/{token}")
def client_view(token: str, db: Session = Depends(get_db)):
    proj = _by_token(token, db)
    variants = db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == proj.id, m.DesignVariant.status != "archived")).all()
    out = []
    for v in variants:
        ver = db.get(m.DesignVersion, v.current_version_id)
        d = variant_dict(v, ver)
        # the client sees prices, but not internal supplier commission data
        if ver:
            from ..render.service import latest_renders
            from ..storage import get_storage

            d["renders"] = [{"room_id": room, "url": get_storage().signed_url(docs[0].storage_key), "width": docs[0].meta.get("width"),
                             "height": docs[0].meta.get("height"), "score": (docs[0].meta.get("grounding") or {}).get("score"),
                             "visual_analogs": (docs[0].meta.get("grounding") or {}).get("visual_analogs", [])}
                            for room, docs in latest_renders(db, ver.id).items() if docs]
        out.append(d)
    comments = db.scalars(select(m.Comment).where(m.Comment.project_id == proj.id, m.Comment.visibility == "client").order_by(m.Comment.created_at)).all()
    return {"project": {"title": proj.title, "address": proj.address, "area_m2": proj.area_m2, "accuracy_level": proj.accuracy_level, "status": proj.status},
            "variants": out, "comments": [{"id": c.id, "body": c.body, "author_name": c.author_name, "anchor": c.anchor, "variant_id": c.variant_id,
                                            "created_at": c.created_at.isoformat(), "resolved": c.resolved} for c in comments]}


@router.get("/api/v1/client/{token}/plan.svg")
def client_plan(token: str, variant_id: str, db: Session = Depends(get_db)):
    from fastapi.responses import Response

    proj = _by_token(token, db)
    v = db.get(m.DesignVariant, variant_id)
    if not v or v.project_id != proj.id:
        raise ApiError(404, "not_found")
    ver = db.get(m.DesignVersion, v.current_version_id)
    return Response(render_svg(Scene.model_validate(ver.scene)), media_type="image/svg+xml")


class ClientComment(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=2000)
    variant_id: str | None = None
    anchor: dict = Field(default_factory=dict)


@router.post("/api/v1/client/{token}/comments")
def client_comment(token: str, body: ClientComment, db: Session = Depends(get_db)):
    proj = _by_token(token, db)
    c = m.Comment(project_id=proj.id, variant_id=body.variant_id, author_name=f"{body.name} (клиент)", body=body.body, anchor=body.anchor)
    db.add(c)
    db.add(m.AuditEvent(project_id=proj.id, action="client.comment", entity="comment", data={"name": body.name}))
    from ..notify import notify, project_people

    notify(db, project_people(db, proj, with_admins=True), "client_comment", params={"name": body.name[:60], "project": proj.title}, link=f"/app/p/{proj.id}", project_id=proj.id)
    db.commit()
    return {"id": c.id}


class ClientDecision(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    variant_id: str
    decision: str = Field(pattern="^(approved|changes_requested)$")
    note: str = ""


@router.post("/api/v1/client/{token}/decision")
def client_decision(token: str, body: ClientDecision, db: Session = Depends(get_db)):
    """Client's approval is recorded in the approval journal; the designer finalises it
    (the AI and the share link never publish the construction package on their own)."""
    proj = _by_token(token, db)
    v = db.get(m.DesignVariant, body.variant_id)
    if not v or v.project_id != proj.id or not v.current_version_id:  # nothing generated yet → nothing to approve
        raise ApiError(404, "not_found")
    db.add(m.Approval(project_id=proj.id, variant_id=v.id, version_id=v.current_version_id, actor_name=body.name, actor_role="client", decision=body.decision, note=body.note))
    db.add(m.AuditEvent(project_id=proj.id, action=f"client.{body.decision}", entity="variant", entity_id=v.id))
    from ..notify import notify, project_people

    notify(db, project_people(db, proj, with_admins=True), "client_approved" if body.decision == "approved" else "client_changes",
           params={"name": body.name[:60], "project": proj.title}, link=f"/app/p/{proj.id}", project_id=proj.id)
    db.commit()
    return {"ok": True}


@router.get("/api/v1/client/{token}/variants/{vid}/version")
def client_version(token: str, vid: str, db: Session = Depends(get_db)):
    proj = _by_token(token, db)
    v = db.get(m.DesignVariant, vid)
    if not v or v.project_id != proj.id:
        raise ApiError(404, "not_found")
    _ = func
    return version_dict(db.get(m.DesignVersion, v.current_version_id))


# ------------------------------------------------------------------ public showcase (landing page)
@router.get("/api/v1/public/showcase")
def showcase(db: Session = Depends(get_db)):
    """Furnished demo scene for the landing page (synthetic demo project only)."""
    from ..scene.demo import demo_base_scene

    proj = db.scalar(select(m.Project).where(m.Project.title == "Демо-квартира · 3 комнаты"))
    if proj:
        v = db.scalar(select(m.DesignVariant).where(m.DesignVariant.project_id == proj.id, m.DesignVariant.status.in_(["selected", "approved", "draft"]))
                      .order_by(m.DesignVariant.created_at.desc()).limit(1))
        if v:
            ver = db.get(m.DesignVersion, v.current_version_id)
            return {"scene": ver.scene, "title": v.title, "total": (ver.estimate or {}).get("totals", {}).get("known"), "items": len(ver.scene.get("objects", [])),
                    "rooms": len(ver.scene.get("rooms", [])), "suppliers": len({ln.get("supplier_key") for ln in (ver.estimate or {}).get("lines", []) if ln.get("supplier_key")})}
    return {"scene": demo_base_scene().model_dump(mode="json"), "title": None, "total": None, "items": 0, "rooms": 7, "suppliers": 0}
