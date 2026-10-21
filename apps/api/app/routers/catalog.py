"""Catalogue / PIM: search, product detail, supplier CSV/XLSX import with mapping
preview and validation, external-records review queue."""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.candidates import candidate_from_record, candidate_from_variant
from ..catalog.normalize import classify, parse_price
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
FIELDS = ["sku", "name", "category", "brand", "price", "currency", "unit", "width_mm", "depth_mm", "height_mm", "color", "material", "stock", "lead_time_days",
          "url", "image_url", "package_coverage_m2", "tier", "style"]
SYNONYMS = {"sku": ["sku", "артикул", "код", "article", "կոդ"], "name": ["name", "название", "наименование", "անվանում"], "category": ["category", "категория", "կատեգորիա"],
            "brand": ["brand", "бренд", "производитель"], "price": ["price", "цена", "գին"], "currency": ["currency", "валюта"], "unit": ["unit", "ед", "единица"],
            "width_mm": ["width", "ширина", "w"], "depth_mm": ["depth", "глубина", "d"], "height_mm": ["height", "высота", "h"], "color": ["color", "цвет", "գույն"],
            "material": ["material", "материал"], "stock": ["stock", "наличие", "остаток"], "lead_time_days": ["lead", "срок"], "url": ["url", "ссылка"],
            "image_url": ["image", "фото", "изображение"], "package_coverage_m2": ["package", "упаковка", "м2 в упак"], "tier": ["tier", "сегмент"], "style": ["style", "стиль"]}


def _read_table(data: bytes, filename: str) -> list[dict]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        head = [str(h or "").strip() for h in rows[0]]
        return [{head[i]: ("" if v is None else str(v)) for i, v in enumerate(r) if i < len(head)} for r in rows[1:] if any(r)]
    text = data.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t")
    return list(csv.DictReader(io.StringIO(text), dialect=dialect))


def guess_mapping(headers: list[str]) -> dict[str, str | None]:
    out = {}
    for f in FIELDS:
        out[f] = next((h for h in headers if any(s == h.strip().lower() or s in h.strip().lower() for s in SYNONYMS.get(f, [f]))), None)
    return out


def validate_row(r: dict, mapping: dict) -> tuple[dict, list[str]]:
    g = {f: (r.get(mapping[f]) if mapping.get(f) else None) for f in FIELDS}
    errs = []
    if not g["sku"]:
        errs.append("нет SKU")
    if not g["name"]:
        errs.append("нет названия")
    price, cur = parse_price(g["price"]) if g["price"] else (None, None)
    g["price"] = price
    g["currency"] = (g["currency"] or cur or "AMD").upper()
    cat = g["category"] if g["category"] in CATEGORIES else classify(g["name"], g["category"])
    if not cat:
        errs.append("категория не распознана")
    g["category"] = cat
    for k in ("width_mm", "depth_mm", "height_mm", "lead_time_days", "package_coverage_m2"):
        try:
            g[k] = float(str(g[k]).replace(",", ".")) if g[k] not in (None, "") else None
        except ValueError:
            errs.append(f"{k}: не число")
            g[k] = None
    if g["unit"] in ("m2", "м2", "м²") and not g["package_coverage_m2"] and cat in ("floor_tile", "wall_tile", "floor_parquet", "floor_laminate"):
        errs.append("для материалов нужна площадь упаковки")
    return g, errs


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
    mp = json.loads(mapping)
    slug = "".join(ch if ch.isalnum() else "-" for ch in supplier_name.lower()).strip("-")[:60] or "supplier"
    sup = db.scalar(select(m.Supplier).where(m.Supplier.slug == slug))
    if not sup:
        org_id = next(iter(p.org_ids), None)
        sup = m.Supplier(name=supplier_name, slug=slug, org_id=org_id, is_demo=False)
        db.add(sup)
        db.flush()
    created = updated = rejected = big_changes = 0
    errors = []
    pending = []
    for i, r in enumerate(rows, start=2):
        g, errs = validate_row(r, mp)
        if errs:
            rejected += 1
            errors.append({"row": i, "errors": errs})
            continue
        pending.append(g)
    existing = {v.sku: v for v in db.scalars(select(m.ProductVariant).join(m.Product).where(m.Product.supplier_id == sup.id))}
    for g in pending:
        v = existing.get(g["sku"])
        if v and v.price and g["price"] and abs(g["price"] - v.price) / v.price * 100 > max_price_change_pct:
            big_changes += 1
    if existing and big_changes > 0.2 * max(1, len(pending)):
        raise ApiError(409, "catalog.import_price_guard", count=big_changes, pct=max_price_change_pct)
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    for g in pending:
        v = existing.get(g["sku"])
        if v:
            if g["price"] is not None and g["price"] != v.price:
                db.add(m.PriceHistory(variant_id=v.id, price=g["price"], currency=g["currency"], source="import"))
            v.price, v.currency = g["price"], g["currency"]
            v.price_status = "confirmed" if g["price"] is not None else "quote_required"
            v.stock_status = "in_stock" if str(g["stock"] or "").lower() in ("1", "yes", "да", "в наличии", "in_stock", "true") else (v.stock_status or "unknown")
            v.price_checked_at = now
            updated += 1
            continue
        prod = m.Product(supplier_id=sup.id, brand=g["brand"] or "", category=g["category"], name_ru=g["name"], tier=g["tier"] or "comfort",
                         styles=[g["style"]] if g["style"] in STYLES else [], unit={"м2": "m2", "м²": "m2"}.get(g["unit"] or "", g["unit"] or "pcs"),
                         package_coverage_m2=g["package_coverage_m2"], item_type="material" if g["category"] in ("floor_tile", "wall_tile", "floor_parquet", "floor_laminate", "wall_paint") else "serial")
        db.add(prod)
        db.flush()
        db.add(m.ProductVariant(product_id=prod.id, sku=g["sku"], color=g["color"] or "", material=g["material"] or "", width_mm=g["width_mm"] or 0, depth_mm=g["depth_mm"] or 0,
                                height_mm=g["height_mm"] or 0, price=g["price"], currency=g["currency"], price_status="confirmed" if g["price"] is not None else "quote_required",
                                stock_status="in_stock" if str(g["stock"] or "").lower() in ("1", "yes", "да", "в наличии", "in_stock", "true") else "unknown",
                                lead_time_days=int(g["lead_time_days"]) if g["lead_time_days"] else None, url=g["url"] or "", image_url=g["image_url"] or "",
                                price_checked_at=now, availability_checked_at=now))
        created += 1
    audit(db, p, "catalog.import", "supplier", sup.id, data={"created": created, "updated": updated, "rejected": rejected})
    db.commit()
    return {"supplier_id": sup.id, "created": created, "updated": updated, "rejected": rejected, "errors": errors[:100]}


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
