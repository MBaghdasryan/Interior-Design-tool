"""Unified product candidate used by grounding, layout and the estimator. A
candidate is always backed by a stored record (internal ProductVariant or an
ExternalProductRecord) — there is no code path that creates a product from text."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m

# Typical dimensions used ONLY for placement when a source omits dimensions.
# Such placements are flagged dims_known=False and lower confidence.
TYPICAL_DIMS = {
    "sofa": (2400, 950, 800), "armchair": (800, 800, 780), "coffee_table": (1000, 600, 400), "tv_unit": (1800, 420, 500),
    "dining_table": (1600, 900, 750), "dining_chair": (480, 540, 800), "bed": (1760, 2150, 1000), "kids_bed": (960, 2050, 800),
    "nightstand": (500, 400, 500), "wardrobe": (1800, 600, 2500), "dresser": (1200, 480, 820), "desk": (1200, 600, 750),
    "desk_chair": (600, 600, 1050), "hallway_wardrobe": (1500, 600, 2500), "shoe_cabinet": (900, 350, 900), "bench": (1000, 400, 450),
    "storage_system": (1400, 450, 2400), "kitchen_run": (3600, 600, 2400), "fridge": (600, 650, 2000), "washer": (600, 450, 850),
    "toilet": (370, 540, 400), "vanity": (800, 460, 850), "bathtub": (1700, 750, 600), "shower": (900, 900, 2000), "rug": (2000, 3000, 10),
    "tv": (1450, 80, 840), "dishwasher": (450, 570, 820),
}


@dataclass
class Candidate:
    ref: str  # "pv:<variant_id>" | "ext:<record_id>"
    category: str
    name: str
    supplier_name: str
    supplier_key: str
    price_amd: float | None
    price_status: str  # confirmed | estimated | quote_required | demo
    unit: str = "pcs"
    package_coverage_m2: float | None = None
    waste_pct: float = 0.0
    w: float = 0
    d: float = 0
    h: float = 0
    dims_known: bool = True
    color: str = ""
    color_hex: str = "#cccccc"
    material: str = ""
    styles: list[str] = field(default_factory=list)
    tier: str = "comfort"
    stock: str = "unknown"
    lead_days: int | None = None
    url: str = ""
    image_url: str = ""
    sku: str = ""
    checked_at: str | None = None
    confidence: float = 1.0
    is_demo: bool = False
    item_type: str = "serial"
    parametric: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def dict(self) -> dict:
        return asdict(self)


def candidate_from_variant(v: m.ProductVariant) -> Candidate:
    p = v.product
    return Candidate(
        ref=f"pv:{v.id}", category=p.category, name=p.name_ru, supplier_name=p.supplier.name, supplier_key=p.supplier.slug,
        price_amd=v.price if v.currency == "AMD" else None, price_status=v.price_status, unit=p.unit,
        package_coverage_m2=p.package_coverage_m2, waste_pct=p.waste_pct, w=v.width_mm, d=v.depth_mm, h=v.height_mm,
        dims_known=bool(v.width_mm) or p.item_type == "material", color=v.color, color_hex=v.color_hex, material=v.material,
        styles=list(p.styles or []), tier=p.tier, stock=v.stock_status, lead_days=v.lead_time_days, url=v.url, image_url=v.image_url,
        sku=v.sku, checked_at=v.price_checked_at.isoformat() if v.price_checked_at else None, confidence=0.6 if p.is_demo else 0.95,
        is_demo=p.is_demo, item_type=p.item_type, parametric=dict(p.parametric or {}),
        warnings=["DEMO-данные: не является реальным предложением"] if p.is_demo else [],
    )


def candidate_from_record(r: m.ExternalProductRecord, source: m.ExternalSource) -> Candidate:
    d = r.data
    dims = d.get("dimensions") or {}
    cat = r.normalized_category or "unknown"
    w, dd, h = dims.get("width_mm"), dims.get("depth_mm"), dims.get("height_mm")
    known = bool(w and dd)
    if not known:
        w, dd, h = TYPICAL_DIMS.get(cat, (0, 0, 0))
    status = "quote_required" if d.get("quote_required") else "confirmed"
    warnings = list(d.get("validation_warnings") or [])
    if not known and cat in TYPICAL_DIMS:
        warnings.append("Размеры не указаны источником — в планировке использован типовой габарит")
    return Candidate(
        ref=f"ext:{r.id}", category=cat, name=d.get("name", ""), supplier_name=source.name, supplier_key=source.key,
        price_amd=r.price_amd, price_status=status, unit=d.get("unit_of_sale", "pcs"), package_coverage_m2=d.get("package_coverage_m2"),
        waste_pct=0.1 if cat in ("floor_tile", "wall_tile") else 0.07 if cat.startswith("floor") else 0.0,
        w=w or 0, d=dd or 0, h=h or 0, dims_known=known, color=d.get("color") or "", material=d.get("material") or "",
        stock=d.get("availability_status", "unknown"), lead_days=(d.get("delivery") or {}).get("days_max"), url=r.canonical_url,
        image_url=d.get("main_image_url") or "", sku=d.get("sku") or d.get("external_product_id") or "", checked_at=d.get("price_checked_at"),
        confidence=r.confidence, item_type="material" if cat in ("floor_tile", "wall_tile", "floor_parquet", "floor_laminate", "wall_paint", "putty", "tile_adhesive") else "serial",
        warnings=warnings,
    )


def load_internal(db: Session, categories: set[str] | None = None, include_demo: bool = True) -> list[Candidate]:
    q = select(m.ProductVariant).join(m.Product).join(m.Supplier, m.Supplier.id == m.Product.supplier_id).where(m.Supplier.verification == "verified")
    if categories:
        q = q.where(m.Product.category.in_(categories))
    if not include_demo:
        q = q.where(m.Product.is_demo.is_(False))
    out = []
    for v in db.scalars(q):
        c = candidate_from_variant(v)
        st = next((s for s in (v.product.styles or []) if v.sku.endswith(s[:3].upper())), None)
        if st:
            c.styles = [st]
        out.append(c)
    return out


def resolve(db: Session, ref: str) -> Candidate | None:
    kind, _, rid = ref.partition(":")
    if kind == "pv":
        v = db.get(m.ProductVariant, rid)
        if not v:
            return None
        c = candidate_from_variant(v)
        return c
    if kind == "ext":
        r = db.get(m.ExternalProductRecord, rid)
        if not r:
            return None
        return candidate_from_record(r, db.get(m.ExternalSource, r.source_id))
    return None


TIER_TARGET = {"economy": 0.62, "comfort": 1.0, "business": 1.55, "premium": 2.4}


def score(c: Candidate, *, category: str, style: str | None, tier: str, target_price: float | None, max_width: float | None) -> tuple[float, dict]:
    """Suitability score per addon prompt §8 step 4. Returns (score 0..1, breakdown)."""
    b: dict[str, float] = {}
    b["category"] = 1.0 if c.category == category else 0.0
    if max_width and c.w:
        b["dimensions"] = 1.0 if c.w <= max_width else 0.0
    else:
        b["dimensions"] = 0.8 if c.dims_known else 0.5
    b["style"] = 1.0 if (style and style in c.styles) else (0.5 if not c.styles else 0.3)
    if target_price and c.price_amd:
        ratio = c.price_amd / target_price
        b["budget"] = max(0.0, 1 - abs(1 - ratio) * 0.8)
    else:
        b["budget"] = 0.4 if c.price_status == "quote_required" else 0.5
    b["availability"] = {"in_stock": 1.0, "to_order": 0.7, "unknown": 0.4, "out_of_stock": 0.0}.get(c.stock, 0.4)
    fresh = 0.5
    if c.checked_at:
        try:
            checked = datetime.fromisoformat(c.checked_at)
            if checked.tzinfo is None:  # timestamps from SQLite / older records are naive UTC
                checked = checked.replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - checked).total_seconds() / 3600
            fresh = 1.0 if age_h < 24 else 0.6 if age_h < 24 * 7 else 0.2
        except ValueError:
            pass
    b["freshness"] = fresh
    b["reliability"] = c.confidence
    b["completeness"] = (0.4 * c.dims_known + 0.3 * (c.price_amd is not None) + 0.3 * bool(c.sku))
    weights = {"category": 3, "dimensions": 2, "style": 1.5, "budget": 1.5, "availability": 1, "freshness": 0.5, "reliability": 1, "completeness": 0.5}
    total = sum(b[k] * w for k, w in weights.items()) / sum(weights.values())
    if b["category"] == 0 or b["dimensions"] == 0 or b["availability"] == 0:
        total *= 0.2
    return round(total, 3), {k: round(v, 2) for k, v in b.items()}
