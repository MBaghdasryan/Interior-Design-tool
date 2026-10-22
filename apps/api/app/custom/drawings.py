"""Production drawings of a custom configuration (P2-5): DXF (front elevation with dimensions,
cut list as text) and an A4-landscape PDF (elevation + cut list + spec version). Every sheet
carries the spec version; an order is accepted only for Production Ready projects."""
from __future__ import annotations

import io

import ezdxf
from ezdxf.enums import TextEntityAlignment

from .engine import cut_list, doors_of
from .library import MODULES


def _layout(spec: dict) -> list[tuple[int, dict, float, float]]:
    """(index, module, x, y) — base/tall modules on the floor in a row, wall modules above at 1400 mm."""
    out, x_floor, x_wall = [], 0.0, 0.0
    for i, md in enumerate(spec.get("modules") or []):
        for _ in range(int(md.get("qty") or 1)):
            if md.get("type", "").startswith("kitchen_wall"):
                out.append((i, md, x_wall, 1400.0))
                x_wall += md["w"]
            else:
                out.append((i, md, x_floor, 0.0))
                x_floor += md["w"]
    return out


def to_dxf(name: str, spec: dict, version: int) -> bytes:
    doc = ezdxf.new("R2018", setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for lay, col in (("MODULES", 7), ("FRONTS", 3), ("DIMS", 1), ("TEXT", 2)):
        doc.layers.add(lay, color=col)
    for i, md, x, y in _layout(spec):
        w, h = md["w"], md["h"]
        msp.add_lwpolyline([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], close=True, dxfattribs={"layer": "MODULES"})
        dx = x + 2
        for dw, dh in doors_of(MODULES.get(md["type"], {}), w, h):
            if MODULES.get(md["type"], {}).get("drawers"):
                continue
            msp.add_lwpolyline([(dx, y + 2), (dx + dw, y + 2), (dx + dw, y + 2 + dh), (dx, y + 2 + dh)], close=True, dxfattribs={"layer": "FRONTS"})
            dx += dw + 4
        msp.add_linear_dim(base=(x, y - 120), p1=(x, y), p2=(x + w, y), dxfattribs={"layer": "DIMS"}).render()
        msp.add_text(f"M{i + 1}", height=60, dxfattribs={"layer": "TEXT"}).set_placement((x + w / 2, y + h / 2), align=TextEntityAlignment.MIDDLE_CENTER)
    ty = -600.0
    msp.add_text(f"{name} — spec v{version}", height=80, dxfattribs={"layer": "TEXT"}).set_placement((0, ty))
    for r in cut_list(spec):
        ty -= 110
        msp.add_text(f"M{r['module'] + 1} {r['part']} {r['l']}x{r['w']} x{r['n']} {r['material']}", height=60, dxfattribs={"layer": "TEXT"}).set_placement((0, ty))
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


def to_pdf(name: str, spec: dict, version: int, pricing: dict, production_ready: bool, labels: dict[str, str]) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas

    from ..album import draw as d

    d.ensure_fonts()  # DejaVu: Armenian and Cyrillic glyphs

    W, H = landscape(A4)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setFont(d.FONT_B, 14)
    c.drawString(30, H - 36, f"{name}")
    c.setFont(d.FONT, 9)
    c.drawString(30, H - 52, f"{labels['spec']} v{version} · {labels['status_ready'] if production_ready else labels['status_not_ready']}")
    lay = _layout(spec)
    if lay:
        span_w = max(x + md["w"] for _, md, x, _ in lay)
        span_h = max(y + md["h"] for _, md, _, y in lay)
        s = min((W * 0.55) / max(span_w, 1), (H - 140) / max(span_h, 1))
        ox, oy = 30, 60
        for i, md, x, y in lay:
            c.rect(ox + x * s, oy + y * s, md["w"] * s, md["h"] * s)
            c.drawCentredString(ox + (x + md["w"] / 2) * s, oy + (y + md["h"] / 2) * s, f"M{i + 1} {md['w']}×{md['h']}×{md['d']}")
    tx, ty = W * 0.62, H - 80
    c.setFont(d.FONT_B, 9)
    c.drawString(tx, ty, labels["cut_list"])
    c.setFont(d.FONT, 7.5)
    for r in cut_list(spec)[:60]:
        ty -= 10
        c.drawString(tx, ty, f"M{r['module'] + 1}  {r['part']}  {r['l']}×{r['w']}  ×{r['n']}  {r['material']}")
    ty -= 18
    c.setFont(d.FONT_B, 9)
    total = pricing.get("total_amd")
    c.drawString(tx, ty, f"{labels['price']}: {f'{total:,} AMD'.replace(',', ' ') if total else labels['quote']}")
    c.showPage()
    c.save()
    return buf.getvalue()
