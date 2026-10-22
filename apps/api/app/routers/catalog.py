"""Catalogue / PIM: search, product detail, supplier CSV/XLSX import with mapping
preview and validation, external-records review queue."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.candidates import candidate_from_record, candidate_from_variant
from ..catalog.pricelist import PriceGuard, _read_table, apply_price_list, guess_mapping, validate_row
from ..catalog.taxonomy import CATEGORIES, GROUPS, STYLES
from ..db import get_db
from ..errors import ApiError
from ..security import Principal, audit, current_principal, require

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])


@router.get("/taxonomy")
def taxonomy():
    return {"categories": [{"key": k, "group": v[0], "ru": v[1], "hy": v[2], "en": v[3]} for k, v in CATEGORIES.items()],
            "groups": [{"key": k, "ru": v[0], "hy": v[1], "en": v[2]} for k, v in GROUPS.items()],
            "styles": [{"key": k, **{kk: vv for kk, vv in v.items()}} for k, v in STYLES.items()]}


@router.get("/products")
def search(q: str = "", category: str | None = None, group: str | None = None, style: str | None = None, tier: str | None = None,
           max_price: float | None = None, in_stock: bool = False, include_external: bool = True, limit: int = Query(60, le=200), offset: int = 0,
           p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    stmt = select(m.ProductVariant).join(m.Product)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(m.Product.name_ru).like(like), func.lower(m.ProductVariant.sku).like(like), func.lower(m.Product.brand).like(like)))
    if category:
        stmt = stmt.where(m.Product.category == category)
    if group:
        stmt = stmt.where(m.Product.category.in_([k for k, v in CATEGORIES.items() if v[0] == group]))
    if tier:
        stmt = stmt.where(m.Product.tier == tier)
    if max_price:
        stmt = stmt.where(m.ProductVariant.price <= max_price)
    if in_stock:
        stmt = stmt.where(m.ProductVariant.stock_status == "in_stock")
    rows = []
    for v in db.scalars(stmt.order_by(m.Product.category, m.ProductVariant.price).offset(offset).limit(limit)):
        c = candidate_from_variant(v)
        if style and not v.sku.endswith(style[:3].upper()):
            continue
        rows.append({**c.dict(), "source": "internal"})
    if include_external:
        es = select(m.ExternalProductRecord).where(m.ExternalProductRecord.review_status != "rejected")
        if category:
            es = es.where(m.ExternalProductRecord.normalized_category == category)
        for r in db.scalars(es.limit(limit)):
            c = candidate_from_record(r, db.get(m.ExternalSource, r.source_id))
            if q and q.lower() not in c.name.lower():
                continue
            rows.append({**c.dict(), "source": "external", "review_status": r.review_status})
    return {"items": rows, "count": len(rows)}


@router.get("/suppliers")
def suppliers(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    out = []
    for s in db.scalars(select(m.Supplier).order_by(m.Supplier.name)):
        n = db.scalar(select(func.count(m.Product.id)).where(m.Product.supplier_id == s.id))
        out.append({"id": s.id, "name": s.name, "slug": s.slug, "kind": s.kind, "is_demo": s.is_demo, "website": s.website, "city": s.city,
                    "delivery": s.delivery, "installation": s.installation, "commission_pct": s.commission_pct, "products": n})
    return out


# ------------------------------------------------------------------ import
@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), p: Principal = Depends(require("catalog:write"))):
    data = await file.read()
    rows = _read_table(data, file.filename or "")
    if not rows:
        raise ApiError(422, "file.empty")
    mapping = guess_mapping(list(rows[0].keys()))
    preview = []
    ok = 0
    for r in rows[:200]:
        g, errs = validate_row(r, mapping)
        ok += not errs
        preview.append({"row": g, "errors": errs})
    return {"headers": list(rows[0].keys()), "mapping": mapping, "rows_total": len(rows), "valid_in_preview": ok, "preview": preview[:50]}


@router.post("/import/commit")
async def import_commit(file: UploadFile = File(...), supplier_name: str = Form(...), mapping: str = Form(...), max_price_change_pct: float = Form(60.0),
                        p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    """Commits a supplier price list. Guard: a mass update that changes prices by more
    than max_price_change_pct for >20% of rows is rejected (protection from broken feeds)."""
    import json

    data = await file.read()
    rows = _read_table(data, file.filename or "")
    slug = "".join(ch if ch.isalnum() else "-" for ch in supplier_name.lower()).strip("-")[:60] or "supplier"
    sup = db.scalar(select(m.Supplier).where(m.Supplier.slug == slug))
    if not sup:
        org_id = next(iter(p.org_ids), None)
        sup = m.Supplier(name=supplier_name, slug=slug, org_id=org_id, is_demo=False)
        db.add(sup)
        db.flush()
    try:
        r = apply_price_list(db, sup, rows, json.loads(mapping), max_price_change_pct)
    except PriceGuard as e:
        raise ApiError(409, "catalog.import_price_guard", count=e.count, pct=e.pct) from None
    audit(db, p, "catalog.import", "supplier", sup.id, data={k: r[k] for k in ("created", "updated", "rejected")})
    db.commit()
    return {"supplier_id": sup.id, **r, "errors": r["errors"][:100]}


# ------------------------------------------------------------------ external review queue
@router.get("/external/review")
def review_queue(p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    out = []
    for r in db.scalars(select(m.ExternalProductRecord).where(m.ExternalProductRecord.review_status == "pending_review").limit(200)):
        src = db.get(m.ExternalSource, r.source_id)
        out.append({"id": r.id, "source": src.name, "url": r.canonical_url, "name": r.data.get("name"), "price_amd": r.price_amd, "category": r.normalized_category,
                    "confidence": r.confidence, "warnings": r.data.get("validation_warnings", []), "disputed": r.data.get("disputed_fields", {})})
    return out


class ReviewIn(BaseModel):
    decision: str  # approved | rejected
    category: str | None = None


@router.post("/external/review/{rid}")
def review(rid: str, body: ReviewIn, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    r = db.get(m.ExternalProductRecord, rid)
    if not r:
        raise ApiError(404, "not_found")
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(422)
    r.review_status = body.decision
    if body.category:
        r.normalized_category = body.category
        r.data = {**r.data, "normalized_category": body.category}
    audit(db, p, f"external.{body.decision}", "external_record", rid)
    db.commit()
    return {"ok": True}


@router.get("/sources")
def public_sources(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """External sources available for the «Внешний каталог» switch (no admin details)."""
    return [{"key": s.key, "name": s.name, "domain": s.domain, "categories": s.categories, "method": s.method, "status": s.connector_status,
             "enabled": s.enabled, "note": s.notes[:240]} for s in db.scalars(select(m.ExternalSource).order_by(m.ExternalSource.name)) if s.enabled]
