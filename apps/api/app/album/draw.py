"""Drawing primitives for A3 album sheets (ReportLab)."""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from ..config import get_settings
from .i18n import t

PAGE_W, PAGE_H = 420 * mm, 297 * mm
FRAME = (20 * mm, 5 * mm, PAGE_W - 5 * mm, PAGE_H - 5 * mm)  # x0, y0, x1, y1 (left binding margin 20 mm)
TB_W = 72 * mm
DRAW_AREA = (FRAME[0] + 6 * mm, FRAME[1] + 6 * mm, FRAME[2] - TB_W - 6 * mm, FRAME[3] - 6 * mm)

INK = HexColor("#1f1d1b")
GREY = HexColor("#7a7068")
LIGHT = HexColor("#d8d2ca")
WALL = HexColor("#3b3631")
WALL_FILL = HexColor("#8a837c")
RED = HexColor("#d9534f")
GREEN = HexColor("#5f9f4f")
BLUE = HexColor("#3d7fb5")
TERRA = HexColor("#c97f63")
SAGE = HexColor("#8f9f7e")
SAND = HexColor("#d9c9b7")

_fonts_ready = False
FONT, FONT_B = "Helvetica", "Helvetica-Bold"


def ensure_fonts() -> None:
    global _fonts_ready, FONT, FONT_B
    if _fonts_ready:
        return
    s = get_settings()
    candidates = [s.album_font_path, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf"]
    bold = [s.album_font_bold_path, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"]
    reg = next((p for p in candidates if p and os.path.exists(p)), None)
    bld = next((p for p in bold if p and os.path.exists(p)), None)
    if reg:
        pdfmetrics.registerFont(TTFont("Body", reg))
        FONT = "Body"
        if bld:
            pdfmetrics.registerFont(TTFont("BodyBold", bld))
            FONT_B = "BodyBold"
        else:
            FONT_B = "Body"
    _fonts_ready = True


@dataclass
class AlbumMeta:
    lang: str
    company: str
    tagline: str
    phone: str
    address: str
    email: str
    project_address: str
    client: str
    designer: str
    total_sheets: int = 0
    brand: str = "Renovara"
    accuracy_label: str = ""
    demo: bool = False


@dataclass
class LegendItem:
    kind: str  # fill | line | dash | symbol | hatch
    color: object
    label: str
    extra: dict = field(default_factory=dict)


def hexc(c: str):
    try:
        return HexColor(c)
    except Exception:  # noqa: BLE001
        return SAND


def text(c: Canvas, x, y, s, size=8, bold=False, color=INK, anchor="start"):
    c.setFillColor(color)
    c.setFont(FONT_B if bold else FONT, size)
    if anchor == "middle":
        c.drawCentredString(x, y, s)
    elif anchor == "end":
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)


def wrap(s: str, width_pt: float, size: float, bold=False) -> list[str]:
    words, lines, cur = (s or "").split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if pdfmetrics.stringWidth(trial, FONT_B if bold else FONT, size) <= width_pt:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def frame_and_titleblock(c: Canvas, meta: AlbumMeta, *, section: str, sheet_title: str, code: str, number: int, scale: str | None, legend: list[LegendItem] | None = None) -> None:
    lang = meta.lang
    x0, y0, x1, y1 = FRAME
    c.setStrokeColor(INK)
    c.setLineWidth(0.8)
    c.rect(x0, y0, x1 - x0, y1 - y0)
    tbx = x1 - TB_W
    c.line(tbx, y0, tbx, y1)
    px = tbx + 5 * mm
    w = TB_W - 10 * mm
    # brand
    y = y1 - 14 * mm
    text(c, px, y, meta.company, 17, bold=False)
    text(c, px + w, y - 4.5 * mm, meta.tagline, 6.5, color=GREY, anchor="end")
    y -= 12 * mm
    for line in (meta.phone, meta.address, meta.email):
        if line:
            text(c, px, y, line, 6.5, color=GREY)
            y -= 3.6 * mm

    def block(label: str, value: str, yy: float) -> float:
        text(c, px, yy, label, 6.3, color=GREY)
        c.setStrokeColor(LIGHT)
        c.line(px, yy - 1.5 * mm, px + w, yy - 1.5 * mm)
        lines = wrap(value, w, 9)
        for i, ln in enumerate(lines[:2]):
            text(c, px, yy - 5.5 * mm - i * 4 * mm, ln, 9)
        return yy - 9 * mm - (len(lines[:2]) - 1) * 4 * mm

    y -= 6 * mm
    y = block(t("project_address", lang), meta.project_address, y)
    y -= 3 * mm
    y = block(t("client", lang), meta.client or "—", y)
    # legend
    if legend:
        y -= 4 * mm
        text(c, px, y, t("legend", lang), 6.3, color=GREY)
        y -= 5 * mm
        for item in legend[:14]:
            draw_legend_item(c, px, y, item)
            for i, ln in enumerate(wrap(item.label, w - 12 * mm, 6.5)[:2]):
                text(c, px + 11 * mm, y - i * 2.8 * mm, ln, 6.5)
            y -= 6 * mm if len(wrap(item.label, w - 12 * mm, 6.5)) > 1 else 4.6 * mm
    # bottom blocks
    yb = y0 + 62 * mm
    block(t("designer", lang), meta.designer or "—", yb)
    yb -= 15 * mm
    text(c, px, yb, t("sheet_name", lang), 6.3, color=GREY)
    c.setStrokeColor(LIGHT)
    c.line(px, yb - 1.5 * mm, px + w, yb - 1.5 * mm)
    text(c, px, yb - 6 * mm, section, 9, bold=True)
    for i, ln in enumerate(wrap(sheet_title, w, 6.8)[:3]):
        text(c, px, yb - 9.6 * mm - i * 2.9 * mm, ln, 6.8, color=GREY)
    yb = y0 + 22 * mm
    c.setStrokeColor(INK)
    c.line(tbx, yb + 6 * mm, x1, yb + 6 * mm)
    text(c, px, yb, t("sheet_no", lang), 6.3, color=GREY)
    text(c, x1 - 13 * mm, yb - 1 * mm, code, 14, bold=True, anchor="end")
    text(c, x1 - 4 * mm, yb - 1 * mm, f"/{meta.total_sheets}", 7, color=GREY, anchor="end")
    c.line(tbx, y0 + 9 * mm, x1, y0 + 9 * mm)
    text(c, px, y0 + 3.5 * mm, f"{t('format', lang)} A3", 6.5)
    if scale:
        text(c, x1 - 4 * mm, y0 + 3.5 * mm, f"{t('scale', lang)}1:{scale}", 6.5, anchor="end")
    # generator / status stamp along the binding margin
    c.saveState()
    c.translate(x0 - 4 * mm, y0 + 4 * mm)
    c.rotate(90)
    stamp = f"{meta.brand} · {meta.accuracy_label}" + (" · DEMO" if meta.demo else "")
    text(c, 0, 0, stamp, 5.5, color=GREY)
    c.restoreState()


def draw_legend_item(c: Canvas, x, y, it: LegendItem) -> None:
    w, h = 9 * mm, 2.6 * mm
    if it.kind == "fill":
        c.setFillColor(it.color)
        c.setStrokeColor(INK)
        c.setLineWidth(0.3)
        c.rect(x, y - 0.6 * mm, w, h, fill=1, stroke=1)
    elif it.kind == "hatch":
        c.setStrokeColor(it.color)
        c.setLineWidth(0.4)
        c.rect(x, y - 0.6 * mm, w, h, fill=0, stroke=1)
        for k in range(0, 10):
            xx = x + k * 1 * mm
            c.line(xx, y - 0.6 * mm, min(xx + h, x + w), y - 0.6 * mm + min(h, x + w - xx))
    elif it.kind in ("line", "dash"):
        c.setStrokeColor(it.color)
        c.setLineWidth(1.2)
        if it.kind == "dash":
            c.setDash(3, 2)
        c.line(x, y + 0.6 * mm, x + w, y + 0.6 * mm)
        c.setDash()
    elif it.kind == "symbol":
        sym = it.extra.get("symbol", "circle")
        draw_symbol(c, x + w / 2, y + 0.7 * mm, sym, it.color, 2.4 * mm)


def draw_symbol(c: Canvas, x, y, sym: str, color, size) -> None:
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(0.5)
    r = size / 2
    if sym in ("socket", "socket_waterproof", "socket_power", "fridge", "washer", "dishwasher", "oven", "cooktop", "hood", "boiler"):
        c.circle(x, y, r, fill=0)
        c.line(x - r, y, x + r, y)
        if sym != "socket":
            c.setFont(FONT_B, size * 0.55)
            c.drawCentredString(x, y - r * 0.9, {"socket_waterproof": "IP", "socket_power": "⚡", "fridge": "F", "washer": "W", "dishwasher": "D",
                                                 "oven": "O", "cooktop": "H", "hood": "V", "boiler": "B"}.get(sym, ""))
    elif sym in ("socket_double", "socket_triple"):
        n = 2 if sym == "socket_double" else 3
        for k in range(n):
            xx = x + (k - (n - 1) / 2) * r * 1.4
            c.circle(xx, y, r * 0.7, fill=0)
    elif sym in ("tv", "data"):
        c.rect(x - r, y - r * 0.7, 2 * r, 1.4 * r, fill=0)
        c.setFont(FONT_B, size * 0.5)
        c.drawCentredString(x, y - r * 0.3, "TV" if sym == "tv" else "IT")
    elif sym in ("switch", "switch_double", "switch_pass", "thermostat"):
        c.circle(x, y, r * 0.55, fill=1)
        c.line(x, y, x + r * 1.2, y + r * 1.2)
        if sym == "switch_double":
            c.line(x, y, x + r * 1.4, y + r * 0.5)
        if sym == "switch_pass":
            c.line(x, y, x - r * 1.2, y - r * 1.2)
    elif sym == "spot":
        c.circle(x, y, r * 0.6, fill=0)
        c.line(x - r * 0.6, y, x + r * 0.6, y)
        c.line(x, y - r * 0.6, x, y + r * 0.6)
    elif sym in ("pendant", "ceiling"):
        c.circle(x, y, r, fill=0)
        c.line(x - r * 0.7, y - r * 0.7, x + r * 0.7, y + r * 0.7)
        c.line(x - r * 0.7, y + r * 0.7, x + r * 0.7, y - r * 0.7)
    elif sym == "wall":
        c.wedge(x - r, y - r, x + r, y + r, 0, 180, fill=0)
    elif sym == "riser":
        c.circle(x, y, r, fill=1)
    elif sym == "water":
        c.circle(x, y, r * 0.6, fill=0)
    elif sym == "drain":
        c.rect(x - r * 0.6, y - r * 0.6, r * 1.2, r * 1.2, fill=0)
    else:
        c.circle(x, y, r * 0.5, fill=1)


class PlanView:
    """Maps scene millimetres onto the sheet at a standard architectural scale."""

    SCALES = [20, 25, 30, 40, 50, 75, 100, 150, 200]

    def __init__(self, c: Canvas, bbox_mm: tuple[float, float, float, float], area: tuple[float, float, float, float] = DRAW_AREA,
                 margin_mm: float = 1400, scale: int | None = None, align: str = "center"):
        self.c = c
        x0, y0, x1, y1 = bbox_mm
        x0, y0, x1, y1 = x0 - margin_mm, y0 - margin_mm, x1 + margin_mm, y1 + margin_mm
        ax0, ay0, ax1, ay1 = area
        aw, ah = ax1 - ax0, ay1 - ay0
        if scale is None:
            need = max((x1 - x0) * mm / aw, (y1 - y0) * mm / ah)
            scale = next((s for s in self.SCALES if s >= need), self.SCALES[-1])
        self.scale = scale
        self.k = mm / scale  # points per scene-mm
        w_pt, h_pt = (x1 - x0) * self.k, (y1 - y0) * self.k
        self.ox = ax0 + (aw - w_pt) / 2 - x0 * self.k if align == "center" else ax0 - x0 * self.k
        self.oy = ay1 - (ah - h_pt) / 2 + y0 * self.k

    def p(self, x: float, y: float) -> tuple[float, float]:
        return (self.ox + x * self.k, self.oy - y * self.k)

    def poly(self, pts, fill=None, stroke=INK, lw=0.4, dash=None, alpha: float | None = None):
        c = self.c
        path = c.beginPath()
        for i, (x, y) in enumerate(pts):
            px, py = self.p(x, y)
            (path.moveTo if i == 0 else path.lineTo)(px, py)
        path.close()
        c.saveState()
        if alpha is not None:
            c.setFillAlpha(alpha)
        if fill is not None:
            c.setFillColor(fill)
        if stroke is not None:
            c.setStrokeColor(stroke)
            c.setLineWidth(lw)
        if dash:
            c.setDash(*dash)
        c.drawPath(path, fill=1 if fill is not None else 0, stroke=1 if stroke is not None else 0)
        c.restoreState()

    def line(self, a, b, color=INK, lw=0.4, dash=None):
        c = self.c
        c.saveState()
        c.setStrokeColor(color)
        c.setLineWidth(lw)
        if dash:
            c.setDash(*dash)
        c.line(*self.p(*a), *self.p(*b))
        c.restoreState()

    def text(self, x, y, s, size=6, bold=False, color=INK, anchor="middle", rotate: float = 0):
        px, py = self.p(x, y)
        if rotate:
            self.c.saveState()
            self.c.translate(px, py)
            self.c.rotate(rotate)
            text(self.c, 0, 0, s, size, bold, color, anchor)
            self.c.restoreState()
        else:
            text(self.c, px, py, s, size, bold, color, anchor)

    def hatch(self, pts, color=GREY, spacing_mm_paper: float = 1.6, angle: float = 45, lw=0.25):
        """Clipped parallel hatch inside a polygon."""
        c = self.c
        c.saveState()
        path = c.beginPath()
        for i, (x, y) in enumerate(pts):
            px, py = self.p(x, y)
            (path.moveTo if i == 0 else path.lineTo)(px, py)
        path.close()
        c.clipPath(path, stroke=0, fill=0)
        xs = [self.p(*q)[0] for q in pts]
        ys = [self.p(*q)[1] for q in pts]
        bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
        c.setStrokeColor(color)
        c.setLineWidth(lw)
        step = spacing_mm_paper * mm
        diag = (bx1 - bx0) + (by1 - by0)
        a = math.radians(angle)
        dx, dy = math.cos(a), math.sin(a)
        nx, ny = -dy, dx
        cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
        n = int(diag / step) + 2
        for k in range(-n, n + 1):
            ox, oy = cx + nx * k * step, cy + ny * k * step
            c.line(ox - dx * diag, oy - dy * diag, ox + dx * diag, oy + dy * diag)
        c.restoreState()

    def dim(self, a, b, offset_mm: float, label: str | None = None, color=INK, size=5.2):
        """Linear dimension between scene points a and b, offset perpendicular (scene mm)."""
        (ax, ay), (bx, by) = a, b
        L = math.hypot(bx - ax, by - ay)
        if L < 1:
            return
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = uy, -ux
        a2 = (ax + nx * offset_mm, ay + ny * offset_mm)
        b2 = (bx + nx * offset_mm, by + ny * offset_mm)
        self.line(a, (a2[0] + nx * 150 * (1 if offset_mm > 0 else -1), a2[1] + ny * 150 * (1 if offset_mm > 0 else -1)), color, 0.2)
        self.line(b, (b2[0] + nx * 150 * (1 if offset_mm > 0 else -1), b2[1] + ny * 150 * (1 if offset_mm > 0 else -1)), color, 0.2)
        self.line(a2, b2, color, 0.3)
        tick = 90
        for q in (a2, b2):
            self.line((q[0] - (ux - nx) * tick, q[1] - (uy - ny) * tick), (q[0] + (ux - nx) * tick, q[1] + (uy - ny) * tick), color, 0.6)
        mx, my = (a2[0] + b2[0]) / 2 + nx * 90, (a2[1] + b2[1]) / 2 + ny * 90
        ang = -math.degrees(math.atan2(uy, ux))
        if ang <= -90 or ang > 90:
            ang += 180
        self.text(mx, my, label or f"{round(L):,}".replace(",", " "), size, color=color, rotate=ang)

    def circle_label(self, x, y, s, r_pt=7, color=TERRA, size=8):
        px, py = self.p(x, y)
        c = self.c
        c.setFillColor(white)
        c.setStrokeColor(color)
        c.setLineWidth(0.8)
        c.circle(px, py, r_pt, fill=1, stroke=1)
        text(c, px, py - size * 0.35, s, size, bold=True, color=color, anchor="middle")


def table(c: Canvas, x, y_top, cols: list[tuple[str, float]], rows: list[list[str]], *, size=6.5, row_h=5.2 * mm, header_fill=SAND,
          max_y: float | None = None, colors: list | None = None) -> float:
    """Draws a simple grid table; returns the y below the table."""
    total_w = sum(w for _, w in cols)
    c.setLineWidth(0.3)
    c.setStrokeColor(INK)
    c.setFillColor(header_fill)
    c.rect(x, y_top - row_h, total_w, row_h, fill=1, stroke=1)
    xx = x
    for title, w in cols:
        lines = wrap(title, w - 2 * mm, size, bold=True)
        text(c, xx + 1.2 * mm, y_top - row_h + 1.7 * mm + (2.4 * mm if len(lines) > 1 else 0), lines[0], size, bold=True)
        if len(lines) > 1:
            text(c, xx + 1.2 * mm, y_top - row_h + 0.6 * mm, lines[1], size * 0.9, bold=True)
        xx += w
    y = y_top - row_h
    for ri, r in enumerate(rows):
        if max_y is not None and y - row_h < max_y:
            break
        if colors and ri < len(colors) and colors[ri] is not None:
            c.setFillColor(colors[ri])
            c.rect(x, y - row_h, cols[0][1], row_h, fill=1, stroke=0)
        c.setStrokeColor(LIGHT)
        c.rect(x, y - row_h, total_w, row_h, fill=0, stroke=1)
        xx = x
        for (_title, w), val in zip(cols, r):
            s = str(val)
            while pdfmetrics.stringWidth(s, FONT, size) > w - 2 * mm and len(s) > 3:
                s = s[:-2] + "…" if not s.endswith("…") else s[:-3] + "…"
            text(c, xx + 1.2 * mm, y - row_h + 1.7 * mm, s, size)
            xx += w
        y -= row_h
    c.setStrokeColor(INK)
    c.rect(x, y, total_w, y_top - y, fill=0, stroke=1)
    return y
