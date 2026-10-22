"""Analog selection (P2-4): candidates of the same category ranked by text similarity, size fit,
style, colour (ΔE), price proximity, availability and lead time — every component is returned so
the designer sees why an analog was proposed."""
from __future__ import annotations

import math

from sqlalchemy.orm import Session

from ..catalog.candidates import Candidate
from . import index

WEIGHTS = {"text": 0.25, "size": 0.2, "style": 0.1, "color": 0.15, "price": 0.15, "availability": 0.1, "lead": 0.05}
STOCK = {"in_stock": 1.0, "to_order": 0.6, "unknown": 0.4, "out_of_stock": 0.0}


def _lab(hex_: str) -> tuple[float, float, float]:
    h = (hex_ or "#cccccc").lstrip("#")[:6].ljust(6, "c")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    x = (lin[0] * 0.4124 + lin[1] * 0.3576 + lin[2] * 0.1805) / 0.95047
    y = lin[0] * 0.2126 + lin[1] * 0.7152 + lin[2] * 0.0722
    z = (lin[0] * 0.0193 + lin[1] * 0.1192 + lin[2] * 0.9505) / 1.08883
    f = [t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116 for t in (x, y, z)]
    return 116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])


def delta_e(a: str, b: str) -> float:
    return math.dist(_lab(a), _lab(b))


def components(base: Candidate, c: Candidate, text_sim: float | None) -> dict[str, float]:
    size = 0.5
    if base.dims_known and c.dims_known and base.w and c.w:
        ratios = [abs(x - y) / max(x, 1) for x, y in ((base.w, c.w), (base.d, c.d), (base.h, c.h)) if x and y]
        size = max(0.0, 1 - (sum(ratios) / len(ratios)) / 0.3) if ratios else 0.5
    style = 1.0 if set(base.styles) & set(c.styles) else (0.5 if not base.styles or not c.styles else 0.0)
    color = max(0.0, 1 - delta_e(base.color_hex, c.color_hex) / 60)
    price = 0.5
    if base.price_amd and c.price_amd:
        price = max(0.0, 1 - abs(math.log(c.price_amd / base.price_amd)) / math.log(2))
    lead = 0.5 if c.lead_days is None else (1.0 if c.lead_days <= 7 else 0.6 if c.lead_days <= 30 else 0.3)
    return {"text": round(text_sim if text_sim is not None else 0.0, 3), "size": round(size, 3), "style": style, "color": round(color, 3), "price": round(price, 3),
            "availability": STOCK.get(c.stock, 0.4), "lead": lead}


def find(db: Session, ref: str, *, limit: int = 8) -> dict:
    pool = index.candidates(db)
    base = next((c for c in pool if c.ref == ref), None)
    if base is None:
        return {"base": None, "items": []}
    same = [c for c in pool if c.category == base.category and c.ref != ref]
    sims = index.text_similarity(db, ref, [c.ref for c in same])
    rows = []
    for c in same:
        comp = components(base, c, sims.get(c.ref))
        score = sum(WEIGHTS[k] * v for k, v in comp.items())
        rows.append({"ref": c.ref, "name": c.name, "supplier": c.supplier_name, "price_amd": c.price_amd, "price_status": c.price_status, "stock": c.stock,
                     "lead_days": c.lead_days, "dims": [c.w, c.d, c.h], "color_hex": c.color_hex, "is_demo": c.is_demo, "url": c.url, "score": round(score, 3), "components": comp})
    rows.sort(key=lambda r: -r["score"])
    return {"base": {"ref": base.ref, "name": base.name, "category": base.category}, "items": rows[:limit], "weights": WEIGHTS, "text_similarity": bool(sims)}
