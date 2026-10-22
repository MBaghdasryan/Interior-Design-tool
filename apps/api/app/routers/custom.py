"""Custom furniture configurator API (P2-5): module library, configurations with versioned specs,
validation + manufacturer pricing, DXF/PDF production drawings, ordering gated by Production Ready."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..custom import drawings, engine
from ..custom.library import BODY, FAMILIES, FRONTS, HARDWARE, MODULES
from ..db import get_db
from ..errors import ApiError
from ..security import Principal, audit, current_principal, project_access, require

router = APIRouter(tags=["custom"])
PDF_LABELS = {
    "hy": {"spec": "Սպեցիֆիկացիա", "status_ready": "Production Ready", "status_not_ready": "ՆԱԽՆԱԿԱՆ — արտադրության համար չէ", "cut_list": "Կտրվածքի ցանկ", "price": "Գին", "quote": "հարցումով"},
    "ru": {"spec": "Спецификация", "status_ready": "Production Ready", "status_not_ready": "ПРЕДВАРИТЕЛЬНО — не для производства", "cut_list": "Раскрой", "price": "Цена", "quote": "по запросу"},
    "en": {"spec": "Specification", "status_ready": "Production Ready", "status_not_ready": "PRELIMINARY — not for production", "cut_list": "Cut list", "price": "Price", "quote": "on request"},
}


def _manufacturers(db: Session) -> list[m.Supplier]:
    return list(db.scalars(select(m.Supplier).where(m.Supplier.verification == "verified", m.Supplier.kind == "manufacturer")))


@router.get("/api/v1/custom/library")
def library(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    return {"families": FAMILIES, "modules": {k: {"family": v["family"], "w": v["w"], "h": v["h"], "d": v["d"], "doors": v.get("doors", 0), "drawers": v.get("drawers", 0)}
                                              for k, v in MODULES.items()},
            "body": BODY, "fronts": FRONTS, "hardware": HARDWARE,
            "manufacturers": [{"id": s.id, "name": s.name, "has_rates": bool(s.custom_rates), "lead_time_days": (s.custom_rates or {}).get("lead_time_days")} for s in _manufacturers(db)]}


def _evaluate(db: Session, c: m.CustomConfig) -> None:
    sup = db.get(m.Supplier, c.supplier_id) if c.supplier_id else None
    rates = (sup.custom_rates or None) if sup and sup.verification == "verified" else None
    c.issues = engine.validate(c.spec, (rates or {}).get("limits"))
    c.pricing = engine.price(c.spec, rates) if not c.issues else {"status": "invalid", "total_amd": None, "breakdown": []}
    if c.status != "ordered":
        c.status = "valid" if not c.issues else "draft"


def config_dict(c: m.CustomConfig, proj: m.Project) -> dict:
    return {"id": c.id, "name": c.name, "family": c.family, "supplier_id": c.supplier_id, "spec": c.spec, "spec_version": c.spec_version, "status": c.status,
            "issues": c.issues, "pricing": c.pricing, "order_id": c.order_id, "production_ready": proj.accuracy_level == "production"}


def _config(db: Session, pid: str, cid: str) -> m.CustomConfig:
    c = db.get(m.CustomConfig, cid)
    if not c or c.project_id != pid:
        raise ApiError(404, "not_found")
    return c


class ConfigIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    family: str = Field(pattern="^(kitchen|wardrobe|walkin|tv)$")
    supplier_id: str | None = None
    available_length_mm: int | None = Field(default=None, ge=300, le=20000)
    modules: list[dict] = Field(default_factory=list, max_length=60)


def _apply(db: Session, c: m.CustomConfig, body: ConfigIn) -> None:
    if body.supplier_id and body.supplier_id not in {s.id for s in _manufacturers(db)}:
        raise ApiError(422, "validation", fields=["supplier_id"])
    clean = []
    for md in body.modules:
        row = {k: md.get(k) for k in ("type", "w", "h", "d", "body", "front", "qty")}
        row["qty"] = max(1, min(int(row.get("qty") or 1), 20))
        if isinstance(md.get("hardware"), dict):
            row["hardware"] = {k: int(v) for k, v in md["hardware"].items() if k in HARDWARE and isinstance(v, int | float) and 0 <= v <= 50}
        clean.append(row)
    c.name, c.family, c.supplier_id = body.name, body.family, body.supplier_id
    c.spec = {"family": body.family, "available_length_mm": body.available_length_mm, "modules": clean}


@router.get("/api/v1/projects/{pid}/custom")
def list_configs(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:read", p, db)
    return [config_dict(c, proj) for c in db.scalars(select(m.CustomConfig).where(m.CustomConfig.project_id == pid).order_by(m.CustomConfig.created_at))]


@router.post("/api/v1/projects/{pid}/custom")
def create_config(pid: str, body: ConfigIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    c = m.CustomConfig(project_id=pid, name=body.name, family=body.family)
    _apply(db, c, body)
    _evaluate(db, c)
    db.add(c)
    db.flush()
    db.add(m.CustomConfigVersion(config_id=c.id, version=1, spec=c.spec, pricing=c.pricing, author=p.user.email))
    audit(db, p, "custom.create", "custom_config", c.id, project_id=pid)
    db.commit()
    return config_dict(c, proj)


@router.put("/api/v1/projects/{pid}/custom/{cid}")
def update_config(pid: str, cid: str, body: ConfigIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    c = _config(db, pid, cid)
    if c.status == "ordered":
        raise ApiError(409, "custom.ordered_locked")
    _apply(db, c, body)
    _evaluate(db, c)
    c.spec_version += 1
    db.add(m.CustomConfigVersion(config_id=c.id, version=c.spec_version, spec=c.spec, pricing=c.pricing, author=p.user.email))
    audit(db, p, "custom.update", "custom_config", cid, project_id=pid, data={"version": c.spec_version})
    db.commit()
    return config_dict(c, proj)


@router.delete("/api/v1/projects/{pid}/custom/{cid}")
def delete_config(pid: str, cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:write", p, db)
    c = _config(db, pid, cid)
    if c.status == "ordered":
        raise ApiError(409, "custom.ordered_locked")
    db.delete(c)
    audit(db, p, "custom.delete", "custom_config", cid, project_id=pid)
    db.commit()
    return {"ok": True}


@router.get("/api/v1/projects/{pid}/custom/{cid}/versions")
def config_versions(pid: str, cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    _config(db, pid, cid)
    return [{"version": v.version, "author": v.author, "created_at": v.created_at.isoformat(), "total_amd": (v.pricing or {}).get("total_amd"),
             "modules": len((v.spec or {}).get("modules", []))}
            for v in db.scalars(select(m.CustomConfigVersion).where(m.CustomConfigVersion.config_id == cid).order_by(m.CustomConfigVersion.version.desc()))]


@router.get("/api/v1/projects/{pid}/custom/{cid}/drawing.dxf")
def drawing_dxf(pid: str, cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    c = _config(db, pid, cid)
    if c.issues:
        raise ApiError(409, "custom.invalid")
    return Response(drawings.to_dxf(c.name, c.spec, c.spec_version), media_type="application/dxf",
                    headers={"Content-Disposition": f'attachment; filename="custom_{cid[:8]}_v{c.spec_version}.dxf"'})


@router.get("/api/v1/projects/{pid}/custom/{cid}/drawing.pdf")
def drawing_pdf(pid: str, cid: str, lang: str = "hy", p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:read", p, db)
    c = _config(db, pid, cid)
    if c.issues:
        raise ApiError(409, "custom.invalid")
    pdf = drawings.to_pdf(c.name, c.spec, c.spec_version, c.pricing or {}, proj.accuracy_level == "production", PDF_LABELS.get(lang, PDF_LABELS["hy"]))
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="custom_{cid[:8]}_v{c.spec_version}.pdf"'})


@router.post("/api/v1/projects/{pid}/custom/{cid}/order")
def order_config(pid: str, cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Creates a manufacturer order (cart → recheck → request, like any order). Production Ready only."""
    proj = project_access(pid, "project:write", p, db)
    c = _config(db, pid, cid)
    if proj.accuracy_level != "production":
        raise ApiError(409, "order.made_to_measure_requires_production")
    if c.issues or (c.pricing or {}).get("status") != "priced" or not c.supplier_id:
        raise ApiError(409, "custom.not_priced")
    if c.order_id:
        return {"order_id": c.order_id}
    sup = db.get(m.Supplier, c.supplier_id)
    cart = m.Cart(project_id=pid, variant_id=c.id)
    db.add(cart)
    db.flush()
    total = c.pricing["total_amd"]
    o = m.Order(project_id=pid, cart_id=cart.id, supplier_id=sup.id, supplier_name=sup.name, status="cart",
                totals={"goods": total, "delivery": 0, "installation": 0, "quote_required": 0, "commission_platform": round(total * sup.commission_pct / 100), "discount": 0})
    db.add(o)
    db.flush()
    db.add(m.OrderItem(order_id=o.id, ref=f"custom:{c.id}:{c.spec_version}", name=f"{c.name} (v{c.spec_version})", qty=1, unit="set", unit_price=total, total=total,
                       price_status="confirmed", lead_days=(c.pricing or {}).get("lead_time_days")))
    db.add(m.Delivery(order_id=o.id, address=proj.address or ""))
    db.add(m.Installation(order_id=o.id, status="pending"))
    c.order_id, c.status = o.id, "ordered"
    audit(db, p, "custom.order", "custom_config", cid, project_id=pid, data={"order_id": o.id, "total_amd": total, "version": c.spec_version})
    db.commit()
    return {"order_id": o.id}


class RatesIn(BaseModel):
    body: dict[str, int] = {}
    front: dict[str, int] = {}
    back: int | None = Field(default=None, ge=0)
    edge_per_m: int | None = Field(default=None, ge=0)
    hardware: dict[str, int] = {}
    assembly_pct: float = Field(default=0, ge=0, le=100)
    lead_time_days: int | None = Field(default=None, ge=1, le=365)
    limits: dict = {}


@router.get("/api/v1/supplier/custom-rates")
def get_rates(p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    from .suppliers import _supplier

    sup = _supplier(p, db)
    return {"rates": sup.custom_rates or {}, "body": BODY, "fronts": FRONTS, "hardware": HARDWARE, "kind": sup.kind}


@router.put("/api/v1/supplier/custom-rates")
def put_rates(body: RatesIn, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    from .suppliers import _supplier

    sup = _supplier(p, db)
    if any(k not in BODY for k in body.body) or any(k not in FRONTS for k in body.front) or any(k not in HARDWARE for k in body.hardware):
        raise ApiError(422, "validation", fields=["rates"])
    if any(v < 0 for d in (body.body, body.front, body.hardware) for v in d.values()):
        raise ApiError(422, "validation", fields=["rates"])
    sup.custom_rates = body.model_dump()
    audit(db, p, "supplier.custom_rates", "supplier", sup.id)
    db.commit()
    return {"rates": sup.custom_rates, "body": BODY, "fronts": FRONTS, "hardware": HARDWARE, "kind": sup.kind}
