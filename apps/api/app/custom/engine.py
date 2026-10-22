"""Validation, cut list and pricing of a custom furniture configuration (P2-5).

spec = {"family": "kitchen", "available_length_mm": 3600 | None, "modules": [
          {"type": "kitchen_base", "w": 600, "h": 720, "d": 560, "body": "ldsp16", "front": "mdf_paint", "qty": 1}, ...]}

Price formula (manufacturer rates, AMD; every term is shown in the breakdown):
  body_m2 × rate.body[material] + fronts_m2 × rate.front[material] + back_m2 × rate.back
  + edge_m × rate.edge_per_m + Σ hardware × rate.hardware[item]
  then × (1 + assembly_pct/100); lead time = rates.lead_time_days
Without rates the configuration is valid but `quote_required` — no price is invented."""
from __future__ import annotations

import math

from .library import FAMILIES, MAX_DOOR_W, MAX_HINGED_DOOR_H, MODULES, PANEL_T, SHEET

RATE_KEYS = ("body", "front", "back", "edge_per_m", "hardware", "assembly_pct", "lead_time_days")


def _issue(code: str, i: int | None = None, **params) -> dict:
    return {"code": code, "module": i, "params": params}


def doors_of(t: dict, w: float, h: float) -> list[tuple[float, float]]:
    rule = t.get("doors", 0)
    if t.get("drawers"):
        n = t["drawers"]
        return [(w - 4, (h - 4 * (n + 1)) / n)] * n
    if rule == "sliding":
        n = max(2, math.ceil(w / 1000))
        return [(w / n + 40, h - 60)] * n  # overlap of sliding leaves
    if rule == "auto":
        n = 1 if w <= MAX_DOOR_W else 2
        return [((w - 4 * (n + 1)) / n, h - 4)] * n
    return [((w - 4) / rule, h - 4)] * int(rule) if rule else []


def validate(spec: dict, limits: dict | None = None) -> list[dict]:
    limits = limits or {}
    sheet = tuple(limits.get("sheet_mm") or SHEET)
    out = []
    fam = spec.get("family")
    if fam not in FAMILIES:
        return [_issue("custom.family")]
    mods = spec.get("modules") or []
    if not mods:
        out.append(_issue("custom.empty"))
    run = 0.0
    for i, md in enumerate(mods):
        t = MODULES.get(md.get("type"))
        if not t:
            out.append(_issue("custom.module_type", i))
            continue
        if t["family"] != fam:
            out.append(_issue("custom.wrong_family", i))
        for k in ("w", "h", "d"):
            lo, hi, step = t[k]
            v = md.get(k)
            if not isinstance(v, int | float) or not lo <= v <= hi:
                out.append(_issue("custom.range", i, dim=k, lo=lo, hi=hi))
            elif (v - lo) % step:
                out.append(_issue("custom.step", i, dim=k, step=step))
        if md.get("body") not in PANEL_T:
            out.append(_issue("custom.material", i, what="body"))
        if (t.get("doors") or t.get("drawers")) and md.get("front") not in ("ldsp", "mdf_film", "mdf_paint", "veneer", "glass_frame"):
            out.append(_issue("custom.material", i, what="front"))
        w, h, d = md.get("w") or 0, md.get("h") or 0, md.get("d") or 0
        if max(h, d) > max(sheet) or min(h, d) > min(sheet) or (w > max(sheet) and not t.get("doors") == "sliding"):
            out.append(_issue("custom.sheet", i, sheet=f"{sheet[0]}×{sheet[1]}"))
        if t.get("doors") == "auto" and h > MAX_HINGED_DOOR_H:
            out.append(_issue("custom.door_height", i, max=MAX_HINGED_DOOR_H))
        if md.get("front") == "glass_frame" and t.get("drawers"):
            out.append(_issue("custom.glass_drawers", i))
        if t["family"] == "kitchen" and md.get("type") not in ("kitchen_wall", "kitchen_wall_liftup"):
            run += w * int(md.get("qty") or 1)
    avail = spec.get("available_length_mm")
    if fam == "kitchen" and avail and run > avail:
        out.append(_issue("custom.run_too_long", None, run=int(run), avail=int(avail)))
    return out


def cut_list(spec: dict) -> list[dict]:
    """Panels per module (mm): sides, top/bottom, shelves, back (HDF), fronts; edging per panel."""
    rows = []
    for i, md in enumerate(spec.get("modules") or []):
        t = MODULES.get(md.get("type"))
        if not t:
            continue
        w, h, d, q = md["w"], md["h"], md["d"], int(md.get("qty") or 1)
        th = PANEL_T.get(md.get("body"), 16)
        body = md.get("body", "ldsp16")
        if t.get("panel"):
            rows.append({"module": i, "part": "panel", "l": w, "w": h, "n": q, "material": body, "edge_mm": 2 * (w + h) * q})
            continue
        inner = w - 2 * th
        rows += [{"module": i, "part": "side", "l": h, "w": d, "n": 2 * q, "material": body, "edge_mm": (h + d) * 2 * q},
                 {"module": i, "part": "top_bottom", "l": inner, "w": d, "n": 2 * q, "material": body, "edge_mm": inner * 2 * q}]
        if t.get("shelves"):
            rows.append({"module": i, "part": "shelf", "l": inner - 2, "w": d - 20, "n": t["shelves"] * q, "material": body, "edge_mm": (inner - 2) * t["shelves"] * q})
        if t.get("back", True):
            rows.append({"module": i, "part": "back", "l": w - 4, "w": h - 4, "n": q, "material": "hdf3", "edge_mm": 0})
        for dw, dh in doors_of(t, w, h):
            rows.append({"module": i, "part": "drawer_front" if t.get("drawers") else "door", "l": round(dh), "w": round(dw), "n": q, "material": md.get("front", "ldsp"),
                         "edge_mm": round(2 * (dw + dh)) * q})
    return rows


def price(spec: dict, rates: dict | None) -> dict:
    """→ {status: priced|quote_required, total_amd, breakdown[], lead_time_days, missing[]}"""
    cl = cut_list(spec)
    area: dict[tuple[str, str], float] = {}
    edge_m = 0.0
    for r in cl:
        kind = "front" if r["part"] in ("door", "drawer_front") else "back" if r["part"] == "back" else "body"
        key = (kind, r["material"])
        area[key] = area.get(key, 0) + r["l"] * r["w"] * r["n"] / 1e6
        edge_m += r["edge_mm"] / 1000
    hw: dict[str, int] = {}
    for md in spec.get("modules") or []:
        t = MODULES.get(md.get("type"), {})
        for k, n in {**t.get("hw", {}), **(md.get("hardware") or {})}.items():
            hw[k] = hw.get(k, 0) + int(n) * int(md.get("qty") or 1)
    summary = {"areas_m2": {f"{k}:{m}": round(v, 3) for (k, m), v in sorted(area.items())}, "edge_m": round(edge_m, 2), "hardware": {k: v for k, v in hw.items() if v}}
    if not rates:
        return {"status": "quote_required", "total_amd": None, "breakdown": [], "lead_time_days": None, "missing": ["rates"], **summary}
    lines, missing = [], []
    for (kind, mat), a in sorted(area.items()):
        rate = rates.get("back") if kind == "back" else (rates.get(kind) or {}).get(mat)
        if rate is None:
            missing.append(f"{kind}:{mat}")
            continue
        lines.append({"item": f"{kind}:{mat}", "qty": round(a, 3), "unit": "m2", "rate": rate, "amount": round(a * rate)})
    if rates.get("edge_per_m") is None:
        missing.append("edge_per_m")
    else:
        lines.append({"item": "edge", "qty": round(edge_m, 2), "unit": "m", "rate": rates["edge_per_m"], "amount": round(edge_m * rates["edge_per_m"])})
    for k, n in summary["hardware"].items():
        rate = (rates.get("hardware") or {}).get(k)
        if rate is None:
            missing.append(f"hardware:{k}")
            continue
        lines.append({"item": f"hardware:{k}", "qty": n, "unit": "pcs", "rate": rate, "amount": round(n * rate)})
    if missing:
        return {"status": "quote_required", "total_amd": None, "breakdown": lines, "lead_time_days": rates.get("lead_time_days"), "missing": missing, **summary}
    sub = sum(x["amount"] for x in lines)
    assembly = round(sub * float(rates.get("assembly_pct") or 0) / 100)
    if assembly:
        lines.append({"item": "assembly", "qty": float(rates.get("assembly_pct") or 0), "unit": "%", "rate": None, "amount": assembly})
    return {"status": "priced", "total_amd": sub + assembly, "breakdown": lines, "lead_time_days": rates.get("lead_time_days"), "missing": [], **summary}
