"""SKU manifest of a camera view: every visible object with its product (name, SKU,
supplier, colour, size, link, reference photo) — the structured input of the render.
The image model never chooses products; it only depicts this list."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.candidates import resolve
from ..catalog.net import FetchBlocked, SafeFetcher
from ..catalog.taxonomy import label
from ..scene.model import Scene

log = logging.getLogger("forma.render")
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")


def build_manifest(db: Session, scene: Scene, room_id: str, visible: dict[str, dict]) -> list[dict]:
    items = []
    for o in scene.objects:
        if o.room_id != room_id or o.id not in visible:
            continue
        c = resolve(db, o.product_variant_id) if o.product_variant_id else None
        items.append({
            "code": o.code or o.id, "object_id": o.id, "category": o.category, "type": label(o.category, "en"),
            "name": (c.name if c else o.name) or label(o.category, "en"), "sku": c.sku if c else "", "supplier": c.supplier_name if c else "",
            "url": c.url if c else "", "image_url": c.image_url if c else "", "color_hex": o.color_hex,
            "size_mm": [round(o.w), round(o.d), round(o.h)], "position": visible[o.id]["position"], "pixels": visible[o.id]["pixels"], "bbox": visible[o.id]["bbox"],
            "mode": "real" if c and not getattr(c, "is_demo", False) and c.sku else ("demo" if c else "concept"),
        })
    items.sort(key=lambda x: -x["pixels"])
    return items


def reference_images(db: Session, manifest: list[dict], limit: int = 4, fetcher: SafeFetcher | None = None) -> list[tuple[str, bytes, str]]:
    """Product photos for the largest visible items, fetched only from allowlisted catalogue hosts
    (same SSRF/robots/rate-limit protections as discovery). → [(code, bytes, mime)]"""
    hosts = sorted({h for s in db.scalars(select(m.ExternalSource).where(m.ExternalSource.enabled.is_(True))) for h in (s.allowed_hosts or [])})
    fetcher = fetcher or SafeFetcher()
    out = []
    for it in manifest:
        if len(out) >= limit:
            break
        if not it["image_url"] or it["mode"] != "real":
            continue
        try:
            r = fetcher.fetch(it["image_url"], hosts, rate_limit_s=2.0, max_bytes=3_000_000, allowed_types=IMAGE_TYPES)
            out.append((it["code"], r.content, r.headers.get("content-type", "image/jpeg").split(";")[0]))
        except FetchBlocked as e:
            log.info("reference image skipped for %s: %s", it["code"], e)
    return out
