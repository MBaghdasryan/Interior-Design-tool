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
    # self-registered suppliers appear only after platform verification
    stmt = select(m.ProductVariant).join(m.Product).join(m.Supplier, m.Supplier.id == m.Product.supplier_id).where(m.Supplier.verification == "verified", m.Product.status == "active")
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
async def import_commit(file: UploadFile = File(...), supplier_name: str = Form(""), mapping: str = Form(...), max_price_change_pct: float = Form(60.0), supplier_id: str | None = Form(None),
                        p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    """Commits a supplier price list. Guard: a mass update that changes prices by more
    than max_price_change_pct for >20% of rows is rejected (protection from broken feeds)."""
    import json

    data = await file.read()
    rows = _read_table(data, file.filename or "")
    from .manage import _writable_supplier

    if not supplier_id and not supplier_name.strip():
        raise ApiError(422, "validation", fields=["supplier_name"])
    slug = "".join(ch if ch.isalnum() else "-" for ch in supplier_name.lower()).strip("-")[:60] or "supplier"
    sup = db.scalar(select(m.Supplier).where(m.Supplier.id == supplier_id)) if supplier_id else db.scalar(select(m.Supplier).where(m.Supplier.slug == slug))
    if sup:
        _writable_supplier(p, db, sup.id)  # a price list never lands in another supplier's catalogue
    elif supplier_id:
        raise ApiError(404, "not_found")
    else:
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
def review(rid: str, body: ReviewIn, p: Principal = Depends(require("sources:manage")), db: Session = Depends(get_db)):
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


# ------------------------------------------------------------------ semantic / visual search, analogs (P2-4)
def _resolve(db: Session, hits: list[tuple[str, float]]) -> list[dict]:
    from ..search import index

    pool = {c.ref: c for c in index.candidates(db)}
    out = []
    for ref, score in hits:
        c = pool.get(ref)
        if c:
            out.append({**c.dict(), "source": "external" if ref.startswith("ext:") else "internal", "score": round(score, 3)})
    return out


@router.get("/search/status")
def search_status(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..search import embeddings

    counts = dict(db.execute(select(m.ProductEmbedding.modality, func.count(m.ProductEmbedding.id)).group_by(m.ProductEmbedding.modality)).all())
    return {**embeddings.status(), "indexed": {"text": counts.get("text", 0), "image": counts.get("image", 0)}}


@router.get("/search/semantic")
def semantic_search(q: str = Query(min_length=2, max_length=200), limit: int = Query(30, ge=1, le=100), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..search import embeddings, index

    try:
        hits, info = index.search_text(db, q, k=limit)
    except embeddings.EmbeddingError:
        raise ApiError(409, "search.off") from None
    return {"items": _resolve(db, hits), **info}


@router.post("/search/image")
async def image_search(file: UploadFile = File(...), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..search import index

    data = await file.read()
    if len(data) > 15 << 20:
        raise ApiError(422, "file.too_large")
    try:
        hits, info = index.search_image(db, data)
    except Exception:  # noqa: BLE001 - undecodable upload
        raise ApiError(422, "asset.not_image") from None
    return {"items": _resolve(db, hits), **info}


@router.get("/analogs")
def analogs(ref: str = Query(pattern=r"^(pv|ext):[0-9a-f]{32}$"), limit: int = Query(8, ge=1, le=30), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..search import analogs as an

    r = an.find(db, ref, limit=limit)
    if r["base"] is None:
        raise ApiError(404, "product.not_found")
    return r
