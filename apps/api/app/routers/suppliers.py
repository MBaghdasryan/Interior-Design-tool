"""Supplier partner onboarding (P2-3): organisation profile, partner agreement, platform
verification, category mapping, asset uploads (3D, PBR textures, BIM/CAD, certificates),
warehouses, delivery options and installation services. A self-registered supplier stays
`pending` — hidden from the catalogue and from design generation — until a platform admin verifies it."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.assets import AssetInvalid, validate
from ..catalog.taxonomy import CATEGORIES
from ..db import get_db
from ..errors import ApiError
from ..security import Principal, audit, require
from ..storage import ScanUnavailable, get_storage, scan_upload

router = APIRouter(tags=["suppliers"])
AGREEMENT_VERSION = "2026-10"  # bump when the owner publishes new partner terms


def _supplier_org(p: Principal) -> str:
    org = next((ms.org for ms in p.user.memberships if ms.org.kind == "supplier"), None)
    if not org:
        raise ApiError(403, "auth.forbidden")
    return org.id


def _supplier(p: Principal, db: Session, *, required: bool = True) -> m.Supplier | None:
    sup = db.scalar(select(m.Supplier).where(m.Supplier.org_id == _supplier_org(p)).order_by(m.Supplier.created_at).limit(1))
    if required and not sup:
        raise ApiError(404, "supplier.not_linked")
    return sup


def onboarding_state(db: Session, sup: m.Supplier | None) -> dict:
    ob = (sup.onboarding or {}) if sup else {}
    products = db.scalar(select(func.count(m.Product.id)).where(m.Product.supplier_id == sup.id)) if sup else 0
    assets = db.scalar(select(func.count(m.SupplierAsset.id)).where(m.SupplierAsset.supplier_id == sup.id)) if sup else 0
    steps = {"profile": bool(sup), "agreement": (ob.get("agreement") or {}).get("version") == AGREEMENT_VERSION,
             "catalogue": bool(products) or bool((sup.feed or {}).get("url")) if sup else False,
             "category_map": bool(sup and sup.category_map), "assets": bool(assets), "submitted": bool(ob.get("submitted_at"))}
    return {"supplier": {"id": sup.id, "name": sup.name, "website": sup.website, "city": sup.city, "kind": sup.kind, "tax_id": ob.get("tax_id", ""),
                         "contacts": sup.contacts} if sup else None,
            "verification": sup.verification if sup else "not_started", "note": ob.get("review_note", ""), "agreement_version": AGREEMENT_VERSION,
            "steps": steps, "products": products or 0, "assets": assets or 0}


@router.get("/api/v1/supplier/onboarding")
def get_onboarding(p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    _supplier_org(p)
    return onboarding_state(db, _supplier(p, db, required=False))


class ProfileIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    website: str = Field(default="", max_length=300)
    city: str = Field(default="Ереван", max_length=100)
    kind: str = Field(default="store", pattern="^(store|manufacturer|installer)$")
    tax_id: str = Field(default="", max_length=30)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=200)


@router.put("/api/v1/supplier/onboarding/profile")
def put_profile(body: ProfileIn, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    org_id = _supplier_org(p)
    sup = _supplier(p, db, required=False)
    if not sup:
        base = "".join(ch if ch.isalnum() else "-" for ch in body.name.lower()).strip("-")[:50] or "supplier"
        slug, n = base, 1
        while db.scalar(select(m.Supplier.id).where(m.Supplier.slug == slug)):
            n += 1
            slug = f"{base}-{n}"
        sup = m.Supplier(org_id=org_id, name=body.name, slug=slug, is_demo=False, verification="pending")
        db.add(sup)
    sup.name, sup.website, sup.city, sup.kind = body.name, body.website, body.city or "Ереван", body.kind
    sup.contacts = {**(sup.contacts or {}), "phone": body.phone, "email": body.email}
    sup.onboarding = {**(sup.onboarding or {}), "tax_id": body.tax_id}
    audit(db, p, "supplier.profile", "supplier", sup.id)
    db.commit()
    return onboarding_state(db, sup)


class AgreementIn(BaseModel):
    version: str
    accept: bool


@router.post("/api/v1/supplier/onboarding/agreement")
def accept_agreement(body: AgreementIn, request: Request, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    sup = _supplier(p, db)
    if not body.accept or body.version != AGREEMENT_VERSION:
        raise ApiError(422, "validation", fields=["accept"])
    sup.onboarding = {**(sup.onboarding or {}), "agreement": {"version": body.version, "at": datetime.now(timezone.utc).isoformat(), "by": p.user.email,
                                                               "ip": request.client.host if request.client else ""}}
    audit(db, p, "supplier.agreement", "supplier", sup.id, data={"version": body.version})
    db.commit()
    return onboarding_state(db, sup)


@router.post("/api/v1/supplier/onboarding/submit")
def submit_onboarding(p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    from ..notify import notify, platform_staff

    sup = _supplier(p, db)
    st = onboarding_state(db, sup)["steps"]
    missing = [k for k in ("profile", "agreement", "catalogue") if not st[k]]
    if missing:
        raise ApiError(409, "supplier.onboarding_incomplete", steps=", ".join(missing))
    sup.onboarding = {**(sup.onboarding or {}), "submitted_at": datetime.now(timezone.utc).isoformat()}
    if sup.verification == "rejected":
        sup.verification = "pending"
    notify(db, platform_staff(db), "catalog_alert", params={"source": sup.name, "reason": "supplier_review"}, link="/app/admin")
    audit(db, p, "supplier.submit", "supplier", sup.id)
    db.commit()
    return onboarding_state(db, sup)


class CategoryMapIn(BaseModel):
    mapping: dict[str, str]


@router.get("/api/v1/supplier/category-map")
def get_category_map(p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    sup = _supplier(p, db)
    return {"mapping": sup.category_map or {}, "taxonomy": sorted(CATEGORIES)}


@router.put("/api/v1/supplier/category-map")
def put_category_map(body: CategoryMapIn, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    sup = _supplier(p, db)
    bad = [v for v in body.mapping.values() if v not in CATEGORIES]
    if bad:
        raise ApiError(422, "validation", fields=["mapping"], info=", ".join(bad[:5]))
    sup.category_map = {k.strip().lower(): v for k, v in body.mapping.items() if k.strip()}
    audit(db, p, "supplier.category_map", "supplier", sup.id, data={"n": len(sup.category_map)})
    db.commit()
    return {"mapping": sup.category_map, "taxonomy": sorted(CATEGORIES)}


# ------------------------------------------------------------------ assets
def asset_dict(a: m.SupplierAsset) -> dict:
    return {"id": a.id, "kind": a.kind, "filename": a.filename, "mime": a.mime, "size": a.size, "variant_id": a.variant_id, "meta": a.meta,
            "scan_status": a.scan_status, "created_at": a.created_at.isoformat(), "url": get_storage().signed_url(a.storage_key)}


@router.get("/api/v1/supplier/assets")
def list_assets(p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    sup = _supplier(p, db)
    return [asset_dict(a) for a in db.scalars(select(m.SupplierAsset).where(m.SupplierAsset.supplier_id == sup.id).order_by(m.SupplierAsset.created_at.desc()))]


@router.post("/api/v1/supplier/assets")
async def upload_asset(file: UploadFile = File(...), kind: str = Form(...), variant_id: str | None = Form(None),
                       p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    sup = _supplier(p, db)
    data = await file.read()
    name = (file.filename or "file").replace("/", "_")[-200:]
    try:
        mime, meta = validate(kind, name, data)
    except AssetInvalid as e:
        raise ApiError(422, f"asset.{e.code}") from None
    try:
        status, sig = scan_upload(data)
    except ScanUnavailable:
        raise ApiError(503, "file.scan_unavailable") from None
    if status == "infected":
        db.add(m.AuditEvent(action="file.quarantined", entity="supplier_asset", data={"filename": name, "signature": sig, "supplier_id": sup.id}))
        db.commit()
        raise ApiError(422, "file.malware")
    v = None
    if variant_id:
        v = db.get(m.ProductVariant, variant_id)
        if not v or v.product.supplier_id != sup.id:
            raise ApiError(404, "product.not_found")
    sha = hashlib.sha256(data).hexdigest()
    key = f"suppliers/{sup.id}/{kind}/{sha[:16]}_{name}"
    get_storage().put(key, data, mime)
    a = m.SupplierAsset(supplier_id=sup.id, variant_id=v.id if v else None, kind=kind, filename=name, mime=mime, size=len(data), sha256=sha,
                        storage_key=key, meta=meta, scan_status=status)
    db.add(a)
    if v and kind == "model3d":
        v.model3d_url = key  # the product now has a real 3D model (supplier-provided)
    audit(db, p, "supplier.asset_upload", "supplier_asset", None, data={"kind": kind, "filename": name, "size": len(data)})
    db.commit()
    return asset_dict(a)


@router.delete("/api/v1/supplier/assets/{aid}")
def delete_asset(aid: str, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    sup = _supplier(p, db)
    a = db.get(m.SupplierAsset, aid)
    if not a or a.supplier_id != sup.id:
        raise ApiError(404, "not_found")
    if a.variant_id and a.kind == "model3d":
        v = db.get(m.ProductVariant, a.variant_id)
        if v and v.model3d_url == a.storage_key:
            v.model3d_url = ""
    get_storage().delete(a.storage_key)
    db.delete(a)
    audit(db, p, "supplier.asset_delete", "supplier_asset", aid)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ locations, delivery, services
class LocationIn(BaseModel):
    kind: str = Field(default="warehouse", pattern="^(warehouse|showroom|pickup)$")
    name: str = Field(min_length=1, max_length=120)
    city: str = Field(default="Ереван", max_length=100)
    address: str = Field(default="", max_length=300)


class DeliveryIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    regions: list[str] = []
    fee_amd: int = Field(default=0, ge=0)
    days_min: int = Field(default=1, ge=0, le=365)
    days_max: int = Field(default=3, ge=0, le=365)


class ServiceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="", max_length=50)
    price_amd: int | None = Field(default=None, ge=0)
    unit: str = Field(default="pcs", max_length=20)


PARTNER = {"locations": (m.SupplierLocation, LocationIn), "delivery-options": (m.SupplierDeliveryOption, DeliveryIn), "services": (m.SupplierService, ServiceIn)}


def _row(r) -> dict:
    return {c.key: getattr(r, c.key) for c in r.__table__.columns if c.key not in ("supplier_id", "created_at")}


@router.get("/api/v1/supplier/partner-data")
def partner_data(p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    sup = _supplier(p, db)
    return {k: [_row(r) for r in db.scalars(select(model).where(model.supplier_id == sup.id).order_by(model.created_at))] for k, (model, _) in PARTNER.items()}


def _add(kind: str, payload: BaseModel, p: Principal, db: Session) -> dict:
    sup = _supplier(p, db)
    model, _ = PARTNER[kind]
    if isinstance(payload, DeliveryIn) and payload.days_max < payload.days_min:
        raise ApiError(422, "validation", fields=["days_max"])
    if isinstance(payload, ServiceIn) and payload.category and payload.category not in CATEGORIES:
        raise ApiError(422, "validation", fields=["category"])
    r = model(supplier_id=sup.id, **payload.model_dump())
    db.add(r)
    audit(db, p, f"supplier.{kind}.add", "supplier", sup.id)
    db.commit()
    return _row(r)


@router.post("/api/v1/supplier/locations")
def add_location(body: LocationIn, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    return _add("locations", body, p, db)


@router.post("/api/v1/supplier/delivery-options")
def add_delivery(body: DeliveryIn, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    return _add("delivery-options", body, p, db)


@router.post("/api/v1/supplier/services")
def add_service(body: ServiceIn, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    return _add("services", body, p, db)


@router.delete("/api/v1/supplier/{kind}/{rid}")
def delete_partner_row(kind: str, rid: str, p: Principal = Depends(require("supplier:manage")), db: Session = Depends(get_db)):
    if kind not in PARTNER:
        raise ApiError(404, "not_found")
    sup = _supplier(p, db)
    r = db.get(PARTNER[kind][0], rid)
    if not r or r.supplier_id != sup.id:
        raise ApiError(404, "not_found")
    db.delete(r)
    audit(db, p, f"supplier.{kind}.delete", "supplier", sup.id)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ platform verification
@router.get("/api/v1/admin/suppliers")
def admin_suppliers(verification: str | None = None, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    q = select(m.Supplier).where(m.Supplier.is_demo.is_(False))
    if verification:
        q = q.where(m.Supplier.verification == verification)
    return [onboarding_state(db, s) for s in db.scalars(q.order_by(m.Supplier.created_at.desc()).limit(200))]


class VerifyIn(BaseModel):
    decision: str = Field(pattern="^(verified|rejected)$")
    note: str = Field(default="", max_length=500)


@router.post("/api/v1/admin/suppliers/{sid}/verification")
def verify_supplier(sid: str, body: VerifyIn, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
    from ..notify import notify

    sup = db.get(m.Supplier, sid)
    if not sup or sup.is_demo:
        raise ApiError(404, "not_found")
    if body.decision == "verified" and (sup.onboarding or {}).get("agreement", {}).get("version") != AGREEMENT_VERSION:
        raise ApiError(409, "supplier.onboarding_incomplete", steps="agreement")
    sup.verification = body.decision
    sup.onboarding = {**(sup.onboarding or {}), "review_note": body.note, "reviewed_by": p.user.email, "reviewed_at": datetime.now(timezone.utc).isoformat()}
    staff = [ms.user for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == sup.org_id))] if sup.org_id else []
    notify(db, staff, "catalog_alert", params={"source": sup.name, "reason": f"supplier_{body.decision}"}, link="/app/supplier")
    audit(db, p, f"supplier.{body.decision}", "supplier", sid, data={"note": body.note})
    db.commit()
    return onboarding_state(db, sup)
