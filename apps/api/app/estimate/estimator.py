"""Deterministic estimator. All arithmetic happens here — LLM output is never
summed. Quote-required lines are never counted as zero: they widen the range."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone

from ..catalog.candidates import Candidate
from ..catalog.normalize import DEFAULT_FX_TO_AMD
from ..catalog.taxonomy import group_label, group_of, label
from ..scene.geometry import polygon_area, polygon_perimeter, room_wall_area_m2, wall_length
from ..scene.model import Scene

# Typical labour rates for Yerevan (AMD). Marked "estimated · DEMO rates" until a bureau
# loads its own price list (Organization.settings["work_rates"]).
DEFAULT_WORK_RATES = {
    "demolition_m2": ("Демонтаж перегородок", "м²", 6000),
    "partition_drywall_m2": ("Монтаж перегородок ГКЛ (2 стороны)", "м²", 14000),
    "plaster_m2": ("Штукатурка стен по маякам", "м²", 5500),
    "putty_paint_m2": ("Шпаклёвка и окраска стен", "м²", 6500),
    "screed_m2": ("Стяжка пола", "м²", 5000),
    "floor_lay_m2": ("Укладка напольного покрытия", "м²", 5500),
    "tiling_m2": ("Укладка плитки", "м²", 12000),
    "ceiling_gkl_m2": ("Потолок ГКЛ с окраской", "м²", 11000),
    "ceiling_stretch_m2": ("Натяжной потолок", "м²", 7000),
    "electric_point": ("Электромонтаж (точка)", "точка", 7000),
    "light_point": ("Монтаж светильника", "шт", 4000),
    "plumbing_point": ("Сантехнический монтаж (точка)", "точка", 18000),
    "warm_floor_m2": ("Тёплый пол электрический", "м²", 9000),
    "door_install": ("Установка двери", "шт", 25000),
    "cleaning_m2": ("Финальная уборка", "м²", 700),
}

CONTINGENCY_PCT = 0.05
OBJECT_SKIP = {"kitchen_run_sink"}
LIGHT_CATEGORY = {"spot": "spot_light", "pendant": "pendant_light", "track": "track_light", "led_strip": "led_strip", "wall": "wall_light",
                  "ceiling": "pendant_light", "mirror": "wall_light"}
SURFACE_LABEL = {"floor": "пол", "walls": "стены", "wet_walls": "стены мокрой зоны", "apron": "фартук", "accent_wall": "акцентная стена", "ceiling": "потолок"}


def _line(group, category, name, qty, unit, unit_price, status, **kw) -> dict:
    total = None if unit_price is None else round(qty * unit_price)
    return {"group": group, "category": category, "name": name, "qty": round(qty, 2), "unit": unit, "unit_price": unit_price,
            "price_status": status, "total": total, **kw}


def _cand_line(c: Candidate, qty: float, unit: str | None = None, *, rooms=(), note: str = "", extra: dict | None = None, price_override=None, status_override=None):
    unit_price = price_override if price_override is not None else c.price_amd
    status = status_override or (c.price_status if unit_price is not None else "quote_required")
    extra = dict(extra or {})
    group = extra.pop("group", group_of(c.category))
    return _line(group, c.category, c.name, qty, unit or c.unit, unit_price, status,
                 ref=c.ref, sku=c.sku, supplier=c.supplier_name, supplier_key=c.supplier_key, url=c.url, checked_at=c.checked_at,
                 lead_days=c.lead_days, stock=c.stock, rooms=sorted(set(rooms)), note=note, is_demo=c.is_demo, color_hex=c.color_hex, image_url=c.image_url,
                 warnings=c.warnings[:3], **extra)


def material_purchase(area_m2: float, waste: float, coverage: float | None) -> tuple[float, int | None]:
    """Q = ceil(A·(1+w) / A_pkg). Returns (gross area, packages)."""
    gross = area_m2 * (1 + waste)
    if not coverage:
        return gross, None
    return gross, math.ceil(gross / coverage - 1e-9)


def estimate(scene: Scene, cands: dict[str, Candidate], suppliers: dict[str, dict] | None = None, *, rates: dict | None = None,
             budget_amd: float | None = None, fx: dict | None = None, accuracy_level: str = "concept") -> dict:
    suppliers = suppliers or {}
    rates = {**DEFAULT_WORK_RATES, **(rates or {})}
    lines: list[dict] = []
    get = cands.get

    # ---- placed objects
    grouped: dict[str, list] = defaultdict(list)
    for o in scene.objects:
        if not o.product_variant_id:
            continue
        grouped[o.product_variant_id].append(o)
    for ref, objs in grouped.items():
        c = get(ref)
        if not c:
            lines.append(_line("custom", objs[0].category, objs[0].name, len(objs), "шт", None, "quote_required", ref=ref, note="Товар не найден в каталоге — требуется подбор"))
            continue
        if c.item_type == "parametric" or (objs[0].custom_product or {}).get("length_mm") and (c.parametric or {}).get("price_per_m"):
            for o in objs:
                L = (o.custom_product or {}).get("length_mm") or o.w
                ppm = (c.parametric or {}).get("price_per_m")
                price = round(ppm * L / 1000, -3) if ppm else c.price_amd
                st = "demo" if c.is_demo else "estimated"
                lines.append(_cand_line(c, 1, "компл.", rooms=[o.room_id], note=f"Изготовление по размерам, L={int(L)} мм", price_override=price, status_override=st,
                                        extra={"group": "custom", "made_to_measure": True}))
            continue
        lines.append(_cand_line(c, len(objs), "шт", rooms=[o.room_id for o in objs]))

    # ---- surfaces
    room_by_id = {r.id: r for r in scene.rooms}
    surf_area: dict[tuple[str, str], float] = defaultdict(float)
    surf_rooms: dict[tuple[str, str], list[str]] = defaultdict(list)
    tile_area = 0.0
    floor_tile_area = 0.0
    paint_area = 0.0
    for f in scene.finishes:
        r = room_by_id.get(f.room_id)
        if not r or not f.product_variant_id:
            continue
        if f.surface == "floor":
            a = polygon_area(r.polygon) / 1e6
        elif f.surface == "walls":
            a = room_wall_area_m2(scene, r)
            if any(x.surface == "wet_walls" and x.room_id == r.id for x in scene.finishes):
                a *= 0.0  # fully tiled wet room
            elif any(x.surface == "accent_wall" and x.room_id == r.id for x in scene.finishes):
                a -= min(3.5, max((wall_length(w) for w in scene.walls), default=0) / 1000) * r.ceiling_height / 1000
            paint_area += max(0.0, a)
        elif f.surface == "wet_walls":
            a = room_wall_area_m2(scene, r)
        elif f.surface == "apron":
            run = next((o for o in scene.objects if o.room_id == r.id and o.category == "kitchen_run"), None)
            a = (run.w / 1000 * 0.62) if run else 0
        elif f.surface == "accent_wall":
            a = 3.2 * r.ceiling_height / 1000
        else:
            a = 0
        if a <= 0:
            continue
        surf_area[(f.product_variant_id, f.surface)] += a
        surf_rooms[(f.product_variant_id, f.surface)].append(r.id)
        fc = get(f.product_variant_id)
        if f.surface in ("wet_walls", "apron") or (f.surface == "floor" and fc and "tile" in fc.category):
            tile_area += a
            if f.surface == "floor":
                floor_tile_area += a
    for (ref, surface), area in surf_area.items():
        c = get(ref)
        if not c:
            continue
        waste = c.waste_pct or (0.1 if "tile" in c.category else 0.07)
        if c.category == "wall_paint":
            liters = math.ceil(area * 2 * (1 + waste) / (c.package_coverage_m2 or 10))
            lines.append(_cand_line(c, liters, "л", rooms=surf_rooms[(ref, surface)], note=f"{area:.1f} м² × 2 слоя, запас {int(waste * 100)}%",
                                    extra={"area_m2": round(area, 2), "surface": surface}))
            continue
        gross, packs = material_purchase(area, waste, c.package_coverage_m2)
        if c.unit == "pack" and packs is not None:
            qty, unit = packs, "упак."
        elif c.unit == "m2":
            qty, unit = (packs * c.package_coverage_m2 if packs is not None else math.ceil(gross * 10) / 10), "м²"
        else:
            qty, unit = math.ceil(gross), c.unit
        lines.append(_cand_line(c, qty, unit, rooms=surf_rooms[(ref, surface)],
                                note=f"{SURFACE_LABEL.get(surface, surface)}: {area:.2f} м² + запас {int(waste * 100)}%" + (f" = {packs} упак. по {c.package_coverage_m2} м²" if packs else ""),
                                extra={"area_m2": round(area, 2), "surface": surface, "packages": packs, "waste_pct": waste}))

    # auxiliary materials derived from areas (from the chosen catalogue if present)
    aux = {c.category: c for c in cands.values() if c.category in ("putty", "tile_adhesive", "drywall")}
    if paint_area and "putty" in aux:
        c = aux["putty"]
        lines.append(_cand_line(c, math.ceil(paint_area * 1.0 * 1.05), "кг", note=f"Финишная шпаклёвка ≈1 кг/м² × {paint_area:.1f} м²"))
    if tile_area and "tile_adhesive" in aux:
        c = aux["tile_adhesive"]
        lines.append(_cand_line(c, math.ceil(tile_area * 5 * 1.05), "кг", note=f"Плиточный клей ≈5 кг/м² × {tile_area:.1f} м²"))
    new_dw = [w for w in scene.walls if w.status == "new" and w.material == "drywall"]
    dw_area = sum(wall_length(w) / 1000 * (w.height or scene.ceiling_height) / 1000 for w in new_dw)
    if dw_area and "drywall" in aux:
        c = aux["drywall"]
        sheets = math.ceil(dw_area * 2 * 1.1 / (c.package_coverage_m2 or 3.0))
        lines.append(_cand_line(c, sheets, "лист", note=f"Перегородки {dw_area:.1f} м² × 2 стороны + 10%"))

    # ---- doors
    door_refs: dict[str, int] = defaultdict(int)
    for op in scene.openings:
        if op.product_variant_id:
            door_refs[op.product_variant_id] += 1
    for ref, n in door_refs.items():
        c = get(ref)
        if c:
            lines.append(_cand_line(c, n, "шт"))

    # ---- lighting
    light_refs: dict[str, list] = defaultdict(list)
    strip_m = 0.0
    for li in scene.lights:
        if li.type == "led_strip":
            strip_m += (((li.end[0] - li.position[0]) ** 2 + (li.end[1] - li.position[1]) ** 2) ** 0.5 / 1000) if li.end else 1
        elif li.product_variant_id:
            light_refs[li.product_variant_id].append(li)
    for ref, ls in light_refs.items():
        c = get(ref)
        if c:
            lines.append(_cand_line(c, len(ls), "шт", rooms=[x.room_id for x in ls]))
    strip_c = next((c for c in cands.values() if c.category == "led_strip"), None)
    if strip_m and strip_c:
        rolls = math.ceil(strip_m * 1.1 / 5)
        lines.append(_cand_line(strip_c, rolls, "рулон 5 м", note=f"{strip_m:.1f} пог. м + 10% (профиль и блоки питания — в работах)"))

    # ---- works (estimated)
    def work(key: str, qty: float, note: str = ""):
        if qty <= 0:
            return
        name, unit, rate = rates[key]
        lines.append(_line("works", key, name, qty, unit, rate, "estimated", note=note, rate_source="DEMO-прайс работ"))

    floor_area = sum(polygon_area(r.polygon) for r in scene.rooms if r.type != "balcony") / 1e6
    wall_area = sum(room_wall_area_m2(scene, r) for r in scene.rooms if r.type != "balcony")
    demo_area = sum(wall_length(w) / 1000 * scene.ceiling_height / 1000 for w in scene.walls if w.status == "demolish")
    work("demolition_m2", round(demo_area, 1))
    work("partition_drywall_m2", round(dw_area, 1))
    work("plaster_m2", round(wall_area, 1))
    work("putty_paint_m2", round(paint_area, 1))
    work("screed_m2", round(floor_area, 1))
    work("floor_lay_m2", round(floor_area - floor_tile_area, 1))
    work("tiling_m2", round(tile_area, 1))
    gkl = sum(polygon_area(room_by_id[c.room_id].polygon) / 1e6 for c in scene.ceilings
              if c.room_id in room_by_id and (c.type.startswith("gkl") or c.type in ("shadow_gap", "cove")))
    work("ceiling_gkl_m2", round(gkl, 1))
    work("electric_point", len(scene.electrical))
    work("light_point", len([li for li in scene.lights if li.type != "led_strip"]))
    plumbing_pts = sum(1 for o in scene.objects if o.category in ("toilet", "vanity", "bathtub", "shower", "washer", "dishwasher", "kitchen_run"))
    work("plumbing_point", plumbing_pts)
    wf = sum((f.size[0] * f.size[1] / 1e6) for f in scene.fixtures if f.type == "warm_floor" and f.size)
    work("warm_floor_m2", round(wf, 1))
    work("door_install", sum(door_refs.values()))
    work("cleaning_m2", round(floor_area, 1))

    # ---- delivery & installation by supplier
    by_sup: dict[str, list[dict]] = defaultdict(list)
    for ln in lines:
        if ln.get("supplier_key"):
            by_sup[ln["supplier_key"]].append(ln)
    for key, sl in by_sup.items():
        info = suppliers.get(key, {})
        name = sl[0].get("supplier", key)
        dl = info.get("delivery") or {}
        if "fee_amd" in dl:
            lines.append(_line("delivery", "delivery", f"Доставка — {name}", 1, "рейс", dl["fee_amd"], "demo" if info.get("is_demo") else "estimated",
                               supplier=name, supplier_key=key, note=f"{dl.get('days_min', '?')}–{dl.get('days_max', '?')} дн."))
        else:
            lines.append(_line("delivery", "delivery", f"Доставка — {name}", 1, "рейс", None, "quote_required", supplier=name, supplier_key=key,
                               note="Стоимость доставки не опубликована — уточнить у поставщика"))
        inst = info.get("installation") or {}
        goods = sum(x["total"] or 0 for x in sl if x["group"] in ("furniture", "custom", "appliances", "plumbing", "lighting"))
        if inst.get("pct") and goods:
            lines.append(_line("installation", "installation", f"Сборка/монтаж — {name}", 1, "усл.", round(goods * inst["pct"] / 100, -2),
                               "demo" if info.get("is_demo") else "estimated", supplier=name, supplier_key=key, note=f"{inst['pct']}% от стоимости"))
        elif inst.get("per_item_amd"):
            n = sum(x["qty"] for x in sl if x["group"] in ("furniture", "appliances", "lighting", "plumbing", "doors") and x["unit"] in ("шт",))
            if n:
                lines.append(_line("installation", "installation", f"Монтаж — {name}", n, "шт", inst["per_item_amd"], "demo" if info.get("is_demo") else "estimated",
                                   supplier=name, supplier_key=key))

    # ---- contingency
    base = sum(x["total"] or 0 for x in lines if x["group"] in ("works", "finishing"))
    if base:
        lines.append(_line("contingency", "contingency", f"Резерв на непредвиденные работы {int(CONTINGENCY_PCT * 100)}%", 1, "—", round(base * CONTINGENCY_PCT, -3), "estimated"))

    for i, ln in enumerate(lines, 1):
        ln["id"] = f"L{i:03d}"

    # ---- totals
    def s(pred):
        return round(sum(x["total"] for x in lines if x["total"] is not None and pred(x)))

    known = s(lambda x: True)
    quote_lines = [x for x in lines if x["total"] is None]
    from ..catalog.demo_seed import BASE

    quote_high = 0.0
    for x in quote_lines:
        base_price = BASE.get(x["category"], (None, None, 0))[2]
        quote_high += base_price * 1.6 * x["qty"] if base_price else 0
    sections = []
    for g in ["furniture", "custom", "lighting", "plumbing", "finishing", "doors", "appliances", "decor", "works", "delivery", "installation", "contingency"]:
        gl = [x for x in lines if x["group"] == g]
        if not gl:
            continue
        tot = round(sum(x["total"] or 0 for x in gl))
        sections.append({"group": g, "label": group_label(g), "total": tot, "lines": len(gl), "quote_required": sum(1 for x in gl if x["total"] is None)})
    totals = {
        "known": known,
        "confirmed": s(lambda x: x["price_status"] == "confirmed"),
        "estimated": s(lambda x: x["price_status"] == "estimated"),
        "demo": s(lambda x: x["price_status"] == "demo"),
        "quote_required_lines": len(quote_lines),
        "range_low": known,
        "range_high": round(known + quote_high),
        "currency": "AMD",
    }
    for sec in sections:
        sec["share"] = round(sec["total"] / known, 3) if known else 0
    budget = None
    if budget_amd:
        budget = {"target": budget_amd, "delta": round(known - budget_amd), "within": known <= budget_amd}
    has_demo = any(x["price_status"] == "demo" for x in lines)
    notices = [{"code": "prices_public_sources", "params": {}}]
    if has_demo:
        notices.insert(0, {"code": "demo_catalog", "params": {}})
    if quote_lines:
        notices.append({"code": "quote_lines_excluded", "params": {"n": len(quote_lines)}})
    if accuracy_level == "concept":
        notices.append({"code": "concept_accuracy", "params": {}})
    notices.append({"code": "engineering_preliminary", "params": {}})
    text = {
        "prices_public_sources": "Цены и наличие получены из публичных источников и могут измениться. Перед оплатой требуется подтверждение поставщика.",
        "demo_catalog": "Смета содержит DEMO-данные демонстрационного каталога — это не реальные предложения магазинов.",
        "quote_lines_excluded": f"{len(quote_lines)} позиций «цена по запросу» не включены в сумму; верхняя граница диапазона — оценка по типовым ценам категории.",
        "concept_accuracy": "Уровень точности «Concept Estimate»: площади и объёмы ориентировочные до подтверждения обмеров.",
        "engineering_preliminary": "Электрика, свет, сантехника и отопление — предварительное предложение до проверки профильным специалистом.",
    }
    disclaimers = [text[n["code"]] for n in notices]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "currency": "AMD",
        "fx_snapshot": fx or DEFAULT_FX_TO_AMD,
        "lines": lines,
        "sections": sections,
        "totals": totals,
        "budget": budget,
        "disclaimers": disclaimers,
        "notices": notices,
        "areas": {"floor_m2": round(floor_area, 2), "walls_m2": round(wall_area, 2), "tile_m2": round(tile_area, 2), "paint_m2": round(paint_area, 2),
                  "perimeter_m": round(sum(polygon_perimeter(r.polygon) for r in scene.rooms) / 1000, 2)},
        "labels": {x["category"]: label(x["category"]) for x in lines},
    }
