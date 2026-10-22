"""Supplier price lists (CSV/XLSX): column mapping, row validation and the guarded apply
used by the manual import and by the scheduled feed sync. Guard: a mass update that changes
prices by more than `max_price_change_pct` for >20% of known rows is refused (broken feed)."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .normalize import classify, parse_price
from .taxonomy import CATEGORIES, STYLES

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



class PriceGuard(Exception):
    def __init__(self, count: int, pct: float, total: int):
        super().__init__(f"{count} of {total} prices change by more than {pct}%")
        self.count, self.pct, self.total = count, pct, total


IN_STOCK = ("1", "yes", "да", "в наличии", "in_stock", "true")
MATERIALS = ("floor_tile", "wall_tile", "floor_parquet", "floor_laminate", "wall_paint")


def apply_price_list(db: Session, sup: m.Supplier, rows: list[dict], mapping: dict, max_price_change_pct: float = 60.0, *, source: str = "import") -> dict:
    """Validate and upsert rows for one supplier. Raises PriceGuard before writing anything."""
    rejected = big_changes = 0
    errors, pending = [], []
    for i, r in enumerate(rows, start=2):
        g, errs = validate_row(r, mapping)
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
        raise PriceGuard(big_changes, max_price_change_pct, len(pending))
    now = datetime.now(timezone.utc)
    created = updated = 0
    for g in pending:
        v = existing.get(g["sku"])
        in_stock = str(g["stock"] or "").lower() in IN_STOCK
        if v:
            if g["price"] is not None and g["price"] != v.price:
                db.add(m.PriceHistory(variant_id=v.id, price=g["price"], currency=g["currency"], source=source))
            v.price, v.currency = g["price"], g["currency"]
            v.price_status = "confirmed" if g["price"] is not None else "quote_required"
            v.stock_status = "in_stock" if in_stock else (v.stock_status or "unknown")
            v.price_checked_at = now
            updated += 1
            continue
        prod = m.Product(supplier_id=sup.id, brand=g["brand"] or "", category=g["category"], name_ru=g["name"], tier=g["tier"] or "comfort",
                         styles=[g["style"]] if g["style"] in STYLES else [], unit={"м2": "m2", "м²": "m2"}.get(g["unit"] or "", g["unit"] or "pcs"),
                         package_coverage_m2=g["package_coverage_m2"], item_type="material" if g["category"] in MATERIALS else "serial")
        db.add(prod)
        db.flush()
        db.add(m.ProductVariant(product_id=prod.id, sku=g["sku"], color=g["color"] or "", material=g["material"] or "", width_mm=g["width_mm"] or 0, depth_mm=g["depth_mm"] or 0,
                                height_mm=g["height_mm"] or 0, price=g["price"], currency=g["currency"], price_status="confirmed" if g["price"] is not None else "quote_required",
                                stock_status="in_stock" if in_stock else "unknown",
                                lead_time_days=int(g["lead_time_days"]) if g["lead_time_days"] else None, url=g["url"] or "", image_url=g["image_url"] or "",
                                price_checked_at=now, availability_checked_at=now))
        created += 1
    return {"created": created, "updated": updated, "rejected": rejected, "errors": errors}
