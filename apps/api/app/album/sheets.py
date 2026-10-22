"""Album sheets. Each sheet is generated from the same scene/estimate, so a change
in the design re-flows into every drawing, schedule and the estimate."""
from __future__ import annotations

import io
import math
from collections import Counter, defaultdict
from dataclasses import dataclass

import qrcode
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from ..catalog.taxonomy import label as cat_label
from ..scene.geometry import (
    along,
    bbox,
    dist,
    footprint,
    label_point,
    normal,
    point_in_polygon,
    polygon_area,
    scene_bbox,
    unit,
    wall_length,
    wall_outline,
    wall_solid_segments,
)
from ..scene.model import Scene
from . import render3d
from .draw import (
    BLUE,
    DRAW_AREA,
    FRAME,
    GREEN,
    GREY,
    INK,
    LIGHT,
    PAGE_H,
    PAGE_W,
    RED,
    SAGE,
    SAND,
    TB_W,
    TERRA,
    WALL,
    AlbumMeta,
    LegendItem,
    PlanView,
    draw_symbol,
    frame_and_titleblock,
    hexc,
    table,
    text,
    wrap,
)
from .i18n import CEILING_TYPES, TX, assumption_text, elec_label, elec_note, line_name, notice, room_name, rule_text, severity, shared, t, tx, variant_title
from .i18n import unit as unit_label

LIGHT_KEYS = {"spot": "l_spot", "pendant": "l_pendant", "wall": "l_wall", "track": "l_track", "led_strip": "l_led", "ceiling": "l_ceiling", "floor_lamp": "l_floor_lamp", "mirror": "l_mirror"}
ZONE_COLORS = {"day": "#f1d9c4", "night": "#dde6d3", "wet": "#d5e3ee", "service": "#ece4d6", "outdoor": "#e9ece4"}
FLOOR_PATTERN_COLOR = "#a4876a"


@dataclass
class SheetSpec:
    key: str
    section: int
    title_key: str
    fn: object
    arg: object = None
    title_override: str | None = None


def fmt_amd(v) -> str:
    if v is None:
        return "—"
    return f"{round(v):,}".replace(",", " ")


class AlbumBuilder:
    def __init__(self, scene: Scene, base: Scene, estimate: dict, issues: list[dict], meta: AlbumMeta, *, project: dict, variant: dict,
                 viewer_url: str, approvals: list[dict], renders: dict[str, list[tuple[bytes, dict]]] | None = None):
        self.renders = renders or {}  # room_id -> [(jpeg bytes, meta)] photoreal renders of this version
        self.scene = scene
        self.base = base
        self.est = estimate
        self.issues = issues
        self.meta = meta
        self.lang = meta.lang
        self.project = project
        self.variant = variant
        self.viewer_url = viewer_url
        self.approvals = approvals
        self.bb = scene_bbox(scene)
        self.lines_by_ref = {ln.get("ref"): ln for ln in estimate.get("lines", []) if ln.get("ref")}

    # ------------------------------------------------------------ helpers
    def code(self, section: int, idx: int) -> str:
        return f"{t('code', self.lang)}{section}.{idx}"

    def new_plan(self, c: Canvas, scale=None, area=None, margin=1500) -> PlanView:
        # the right 80 mm of the drawing field are reserved for room tables / schedules
        area = area or (DRAW_AREA[0], DRAW_AREA[1], DRAW_AREA[2] - 80 * mm, DRAW_AREA[3])
        return PlanView(c, self.bb, area=area, margin_mm=margin, scale=scale)

    def draw_walls(self, pv: PlanView, scene: Scene, mode: str = "design", hatch_existing=True):
        for w in scene.walls:
            if mode == "design" and w.status == "demolish":
                continue
            if mode == "existing" and w.status == "new":
                continue
            segs = wall_solid_segments(w, scene.openings) if mode != "demolition" or w.status != "demolish" else [(0, wall_length(w))]
            for s, e in segs:
                outline = wall_outline(w, s, e)
                if mode == "demolition" and w.status == "demolish":
                    pv.poly(outline, fill=HexColor("#f8d7d5"), stroke=RED, lw=0.6)
                    pv.hatch(outline, RED, 1.0, 45, 0.35)
                elif w.status == "new" and mode in ("construction", "design"):
                    pv.poly(outline, fill=HexColor("#dcefd5") if mode == "construction" else HexColor("#cfcac4"), stroke=GREEN if mode == "construction" else WALL, lw=0.6)
                    if mode == "construction":
                        pv.hatch(outline, GREEN, 1.2, -45, 0.3)
                else:
                    pv.poly(outline, fill=HexColor("#9a938c") if w.material in ("concrete",) else HexColor("#b9b2aa"), stroke=WALL, lw=0.6)
                    if hatch_existing and w.material == "concrete":
                        pv.hatch(outline, WALL, 1.4, 45, 0.2)
        self.draw_openings(pv, scene, mode)

    def draw_openings(self, pv: PlanView, scene: Scene, mode: str = "design"):
        for o in scene.openings:
            w = scene.wall(o.wall_id)
            if not w or (mode == "existing" and o.status == "new"):
                continue
            p0, p1 = along(w, o.offset), along(w, o.offset + o.width)
            nx, ny = normal(w.a, w.b)
            ht = w.thickness / 2
            if o.type == "window":
                for k in (-ht, -ht / 3, ht / 3, ht):
                    pv.line((p0[0] + nx * k, p0[1] + ny * k), (p1[0] + nx * k, p1[1] + ny * k), BLUE if abs(k) < ht else INK, 0.35)
                pv.line((p0[0] + nx * ht, p0[1] + ny * ht), (p0[0] - nx * ht, p0[1] - ny * ht), INK, 0.4)
                pv.line((p1[0] + nx * ht, p1[1] + ny * ht), (p1[0] - nx * ht, p1[1] - ny * ht), INK, 0.4)
            elif o.type in ("door", "entrance_door", "balcony_door"):
                side = 1 if o.swing == "left" else -1
                hinge, free = (p0, p1) if o.hinge == "start" else (p1, p0)
                h0 = (hinge[0] + nx * ht * side, hinge[1] + ny * ht * side)
                leaf = (h0[0] + nx * o.width * side, h0[1] + ny * o.width * side)
                f0 = (free[0] + nx * ht * side, free[1] + ny * ht * side)
                pv.line(h0, leaf, INK, 0.9)
                # arc from leaf end to free jamb
                a0 = math.atan2(leaf[1] - h0[1], leaf[0] - h0[0])
                a1 = math.atan2(f0[1] - h0[1], f0[0] - h0[0])
                da = (a1 - a0 + math.pi) % (2 * math.pi) - math.pi
                prev = leaf
                for k in range(1, 13):
                    a = a0 + da * k / 12
                    q = (h0[0] + math.cos(a) * o.width, h0[1] + math.sin(a) * o.width)
                    pv.line(prev, q, GREY, 0.25)
                    prev = q
                pv.line((p0[0] + nx * ht, p0[1] + ny * ht), (p0[0] - nx * ht, p0[1] - ny * ht), INK, 0.4)
                pv.line((p1[0] + nx * ht, p1[1] + ny * ht), (p1[0] - nx * ht, p1[1] - ny * ht), INK, 0.4)
            elif o.type == "sliding_door":
                pv.line((p0[0] + nx * 30, p0[1] + ny * 30), (p0[0] + (p1[0] - p0[0]) * 0.6 + nx * 30, p0[1] + (p1[1] - p0[1]) * 0.6 + ny * 30), INK, 1.2)
                pv.line((p0[0] + (p1[0] - p0[0]) * 0.4 - nx * 30, p0[1] + (p1[1] - p0[1]) * 0.4 - ny * 30), (p1[0] - nx * 30, p1[1] - ny * 30), INK, 1.2)

    def room_labels(self, pv: PlanView, scene: Scene, area=True, names=False, size=8):
        for r in scene.rooms:
            cx, cy = label_point(r.polygon)
            pv.circle_label(cx, cy, str(r.number), r_pt=6.5, size=7.5)
            if names:
                pv.text(cx, cy - 650, room_name(r, self.lang), 6.5, color=INK)
            if area:
                pv.text(cx, cy + 520, f"{polygon_area(r.polygon) / 1e6:.2f} {tx('u_m2', self.lang)}", 6, color=GREY)

    def room_table(self, c: Canvas, scene: Scene, x=None, y=None):
        x = x if x is not None else DRAW_AREA[2] - 74 * mm
        y = y if y is not None else DRAW_AREA[3] - 2 * mm
        rows = []
        total = 0.0
        for r in sorted(scene.rooms, key=lambda r: r.number):
            a = polygon_area(r.polygon) / 1e6
            if r.type != "balcony":
                total += a
            rows.append([str(r.number), room_name(r, self.lang), f"{a:.2f}"])
        yb = table(c, x, y, [("№", 7 * mm), (t("name", self.lang), 44 * mm), (t("area", self.lang), 23 * mm)], rows, size=6.3, row_h=4.6 * mm)
        text(c, x + 74 * mm - 1.5 * mm, yb - 4 * mm, f"{t('total', self.lang)}: {total:.2f} {tx('u_m2', self.lang)}", 7, bold=True, anchor="end")

    def chain_dims(self, pv: PlanView, scene: Scene, offset1=700, offset2=1300):
        cx = (self.bb[0] + self.bb[2]) / 2
        cy = (self.bb[1] + self.bb[3]) / 2
        for w in scene.walls:
            if w.kind not in ("exterior",):
                continue
            nx, ny = normal(w.a, w.b)
            mid = along(w, wall_length(w) / 2)
            out = 1 if (mid[0] + nx * 10 - cx) * nx + (mid[1] + ny * 10 - cy) * ny > 0 else -1
            ht = w.thickness / 2
            a = (w.a[0] + nx * ht * out, w.a[1] + ny * ht * out)
            b = (w.b[0] + nx * ht * out, w.b[1] + ny * ht * out)
            L = wall_length(w)
            ux, uy = unit(w.a, w.b)
            ticks = [0.0]
            for o in sorted((o for o in scene.openings if o.wall_id == w.id), key=lambda o: o.offset):
                ticks += [o.offset, o.offset + o.width]
            ticks.append(L)
            ticks = sorted(set(round(t_, 1) for t_ in ticks))
            # dimension helpers expect offset to the left of a→b; flip sign by orientation
            sgn = out
            for t0, t1 in zip(ticks, ticks[1:]):
                pa = (a[0] + ux * t0, a[1] + uy * t0)
                pb = (a[0] + ux * t1, a[1] + uy * t1)
                pv.dim(pa, pb, offset1 * sgn, size=4.8)
            pv.dim(a, b, offset2 * sgn, size=5.4)

    def room_dims(self, pv: PlanView, scene: Scene):
        for r in scene.rooms:
            x0, y0, x1, y1 = bbox(r.polygon)
            if (x1 - x0) < 900 or (y1 - y0) < 900:
                continue
            pv.dim((x0, y0 + 350), (x1, y0 + 350), 0, size=4.6, color=HexColor("#6a5f55"))
            pv.dim((x0 + 350, y0), (x0 + 350, y1), 0, size=4.6, color=HexColor("#6a5f55"))

    def page(self, c: Canvas, spec: SheetSpec, code: str, scale: int | None, legend: list[LegendItem] | None = None):
        sec_title = t(f"sec{spec.section}", self.lang)
        title = spec.title_override or t(spec.title_key, self.lang)
        frame_and_titleblock(c, self.meta, section=sec_title, sheet_title=title, code=code, number=0, scale=str(scale) if scale else None, legend=legend)

    # ------------------------------------------------------------ cover & TOC
    def cover(self, c: Canvas, specs: list[SheetSpec]):
        c.setFillColor(HexColor("#2e2e2e"))
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)
        # axonometric hero of the designed apartment
        faces = render3d.floor_faces(self.scene) + render3d.wall_faces(self.scene, {"existing", "new"}, {"existing": "#efeae3", "new": "#efeae3"}, cut_height=1300) + render3d.object_faces(self.scene)
        self.draw_projected(c, render3d.axonometric(faces, 35, 35), (60 * mm, 40 * mm, PAGE_W - 60 * mm, PAGE_H - 55 * mm), stroke_scale=0.6)
        text(c, PAGE_W / 2, PAGE_H - 26 * mm, t("album_title", self.lang), 15, color=HexColor("#f3eee8"), anchor="middle")
        text(c, PAGE_W / 2, 30 * mm, self.meta.company, 30, color=HexColor("#f3eee8"), anchor="middle")
        text(c, PAGE_W / 2, 23 * mm, self.meta.tagline, 9, color=HexColor("#c9bfb3"), anchor="middle")
        text(c, PAGE_W / 2, 12 * mm, self.meta.project_address, 12, color=HexColor("#f3eee8"), anchor="middle")
        text(c, PAGE_W - 15 * mm, 18 * mm, self.meta.phone, 7, color=HexColor("#c9bfb3"), anchor="end")
        text(c, PAGE_W - 15 * mm, 14 * mm, self.meta.address, 7, color=HexColor("#c9bfb3"), anchor="end")
        text(c, PAGE_W - 15 * mm, 10 * mm, self.meta.email, 7, color=HexColor("#c9bfb3"), anchor="end")
        self.qr(c, 15 * mm, 8 * mm, 22 * mm, self.viewer_url)
        text(c, 15 * mm, 5 * mm, "3D / Client viewer", 6, color=HexColor("#c9bfb3"))
        text(c, PAGE_W / 2, PAGE_H - 33 * mm, f"{variant_title(self.variant, self.lang)} · {self.meta.accuracy_label}", 9, color=HexColor("#c9bfb3"), anchor="middle")
        if self.meta.demo:
            text(c, PAGE_W / 2, PAGE_H - 39 * mm, t("demo_note", self.lang), 8, color=HexColor("#e7a58f"), anchor="middle")

    def toc(self, c: Canvas, specs: list[SheetSpec], codes: list[str]):
        frame_and_titleblock(c, self.meta, section=t("toc", self.lang), sheet_title=t("toc", self.lang), code="—", number=0, scale=None)
        x = DRAW_AREA[0] + 40 * mm
        y = DRAW_AREA[3] - 8 * mm
        cols = [(t("section", self.lang), 60 * mm), (t("page", self.lang), 30 * mm), (t("name", self.lang), 150 * mm)]
        rows, colors = [], []
        last = None
        for spec, code in zip(specs, codes):
            sec = t(f"sec{spec.section}", self.lang)
            rows.append([f"{t('code', self.lang)}{spec.section} {sec}" if spec.section != last else "", code, spec.title_override or t(spec.title_key, self.lang)])
            colors.append(SAND if spec.section != last else None)
            last = spec.section
        table(c, x, y, cols, rows, size=6.6, row_h=min(5.0 * mm, (y - DRAW_AREA[1]) / (len(rows) + 2)), colors=colors)

    # ------------------------------------------------------------ helpers for projected drawings
    def draw_projected(self, c: Canvas, items, rect, stroke_scale=1.0, background: str | None = None):
        if not items:
            return
        xs = [x for pts, _ in items for x, _ in pts]
        ys = [y for pts, _ in items for _, y in pts]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        rx0, ry0, rx1, ry1 = rect
        k = min((rx1 - rx0) / ((x1 - x0) or 1), (ry1 - ry0) / ((y1 - y0) or 1))
        ox = rx0 + ((rx1 - rx0) - (x1 - x0) * k) / 2 - x0 * k
        oy = ry0 + ((ry1 - ry0) - (y1 - y0) * k) / 2 - y0 * k
        c.saveState()
        if background:
            c.setFillColor(hexc(background))
            c.rect(rx0, ry0, rx1 - rx0, ry1 - ry0, fill=1, stroke=0)
        p = c.beginPath()
        p.rect(rx0, ry0, rx1 - rx0, ry1 - ry0)
        c.clipPath(p, stroke=0, fill=0)
        for pts, f in items:
            path = c.beginPath()
            for i, (x, y) in enumerate(pts):
                (path.moveTo if i == 0 else path.lineTo)(ox + x * k, oy + y * k)
            path.close()
            c.setFillColor(hexc(f.color))
            if f.stroke:
                c.setStrokeColor(hexc(f.stroke))
                c.setLineWidth(f.lw * stroke_scale)
            c.drawPath(path, fill=1, stroke=1 if f.stroke else 0)
        c.restoreState()

    def draw_perspective(self, c: Canvas, items, rect, fov_scale=1.0):
        rx0, ry0, rx1, ry1 = rect
        w, h = rx1 - rx0, ry1 - ry0
        k = max(w, h) / 2 * fov_scale
        cx, cy = (rx0 + rx1) / 2, (ry0 + ry1) / 2
        c.saveState()
        p = c.beginPath()
        p.rect(rx0, ry0, w, h)
        c.clipPath(p, stroke=0, fill=0)
        c.setFillColor(HexColor("#f6f2ec"))
        c.rect(rx0, ry0, w, h, fill=1, stroke=0)
        for pts, f in items:
            path = c.beginPath()
            for i, (x, y) in enumerate(pts):
                (path.moveTo if i == 0 else path.lineTo)(cx + x * k, cy + y * k)
            path.close()
            c.setFillColor(hexc(f.color))
            if f.stroke:
                c.setStrokeColor(hexc(f.stroke))
                c.setLineWidth(f.lw)
            c.drawPath(path, fill=1, stroke=1 if f.stroke else 0)
        c.restoreState()
        c.setStrokeColor(LIGHT)
        c.rect(rx0, ry0, w, h, fill=0, stroke=1)

    def qr(self, c: Canvas, x, y, size, data: str):
        img = qrcode.make(data, box_size=6, border=1)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        c.drawImage(ImageReader(buf), x, y, size, size)

    # ------------------------------------------------------------ ДН1 engineering
    def s_measure(self, c, spec, code):
        pv = self.new_plan(c, margin=1800)
        self.draw_walls(pv, self.base, mode="existing")
        self.chain_dims(pv, self.base)
        self.room_dims(pv, self.base)
        self.room_labels(pv, self.base)
        self.room_table(c, self.base)
        h = self.base.ceiling_height
        text(c, DRAW_AREA[0] + 2 * mm, DRAW_AREA[1] + 2 * mm, f"{t('ceiling_h', self.lang)}: {tx('slab_to_slab', self.lang, h=f'{h:.0f}')}. " +
             ("; ".join(f"{cd.wall_id} = {cd.measured_mm:.0f} {tx('u_mm', self.lang)}" for cd in self.base.control_dimensions) or ""), 6.5, color=GREY)
        self.page(c, spec, code, pv.scale, [LegendItem("fill", HexColor("#9a938c"), t("existing_wall", self.lang))])

    def s_demolish(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        self.draw_walls(pv, self.base, mode="demolition")
        for w in self.base.walls:
            if w.status == "demolish":
                mid = along(w, wall_length(w) / 2)
                nx, ny = normal(w.a, w.b)
                pv.dim(w.a, w.b, 500, size=5)
                pv.text(mid[0] + nx * 900, mid[1] + ny * 900, f"{w.id}: {wall_length(w) / 1000:.2f} × {self.base.ceiling_height / 1000:.2f} {tx('u_m', self.lang)}", 6, color=RED)
        self.room_labels(pv, self.base, area=False)
        self.room_table(c, self.base)
        self.page(c, spec, code, pv.scale, [LegendItem("fill", HexColor("#9a938c"), t("existing_wall", self.lang)), LegendItem("hatch", RED, t("demolish_wall", self.lang))])

    def s_new(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        self.draw_walls(pv, self.scene, mode="construction")
        for w in self.scene.walls:
            if w.status == "new":
                pv.dim(w.a, w.b, -450 if w.a[1] == w.b[1] else 450, size=5, color=GREEN)
                mid = along(w, wall_length(w) / 2)
                pv.text(mid[0], mid[1] - 250, f"{w.id} · {w.material} {w.thickness:.0f}", 5.5, color=GREEN)
        self.room_labels(pv, self.scene)
        self.room_table(c, self.scene)
        self.page(c, spec, code, pv.scale, [LegendItem("fill", HexColor("#9a938c"), t("existing_wall", self.lang)), LegendItem("hatch", GREEN, t("new_wall", self.lang))])

    def s_axo(self, c, spec, code):
        x0, y0, x1, y1 = DRAW_AREA
        cells = [(x0, (y0 + y1) / 2, (x0 + x1) / 2, y1), ((x0 + x1) / 2, (y0 + y1) / 2, x1, y1), (x0, y0, (x0 + x1) / 2, (y0 + y1) / 2), ((x0 + x1) / 2, y0, x1, (y0 + y1) / 2)]
        views = [("demolish", 35), ("new", 35), ("demolish", 215), ("new", 215)]
        for (kind, ang), cell in zip(views, cells):
            sc = self.base if kind == "demolish" else self.scene
            cols = {"existing": "#f4f1ec", "demolish": "#e8726c" if kind == "demolish" else "#f4f1ec", "new": "#7dbb6c"}
            statuses = {"existing", "demolish"} if kind == "demolish" else {"existing", "new"}
            faces = render3d.floor_faces(sc, finishes=False) + render3d.wall_faces(sc, statuses, cols)
            self.draw_projected(c, render3d.axonometric(faces, ang, 32), (cell[0] + 4 * mm, cell[1] + 4 * mm, cell[2] - 4 * mm, cell[3] - 4 * mm), 0.8)
        self.page(c, spec, code, None, [LegendItem("fill", HexColor("#e8726c"), t("demolish_wall", self.lang)), LegendItem("fill", HexColor("#7dbb6c"), t("new_wall", self.lang))])

    def s_zoning(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        for r in self.scene.rooms:
            pv.poly(r.polygon, fill=hexc(ZONE_COLORS.get(r.zone or "service")), stroke=None)
        self.draw_walls(pv, self.scene)
        self.room_labels(pv, self.scene, names=True)
        self.room_table(c, self.scene)
        legend = [LegendItem("fill", hexc(ZONE_COLORS[z]), t(f"zone_{z}", self.lang)) for z in ("day", "night", "wet", "service", "outdoor") if any(r.zone == z for r in self.scene.rooms)]
        self.page(c, spec, code, pv.scale, legend)

    def plumbing_points(self) -> list[dict]:
        pts = []
        spec = {"toilet": (("cold", 150), ("drain", 0)), "vanity": (("cold", 550), ("hot", 550), ("drain", 500)), "bathtub": (("cold", 750), ("hot", 750), ("drain", 0)),
                "shower": (("cold", 1100), ("hot", 1100), ("drain", 0)), "washer": (("cold", 900), ("drain", 600)), "kitchen_run": (("cold", 500), ("hot", 500), ("drain", 450)),
                "dishwasher": (("cold", 300), ("drain", 300))}
        n = 0
        for o in self.scene.objects:
            if o.category not in spec:
                continue
            fp = footprint(o)
            fx, fy = (-math.sin(math.radians(o.rotation)), math.cos(math.radians(o.rotation)))
            base = (o.x - fx * (min(fp.w, fp.h) / 2 - 80), o.y - fy * (min(fp.w, fp.h) / 2 - 80))
            if o.category == "kitchen_run" and (o.custom_product or {}).get("sink_xy"):
                base = tuple(o.custom_product["sink_xy"])
            for k, (kind, h) in enumerate(spec[o.category]):
                n += 1
                off = (k - 1) * 120
                p = (base[0] + fy * off, base[1] - fx * off)
                pts.append({"id": f"P-{n:02d}", "kind": kind, "pos": p, "height": h, "object": o, "room_id": o.room_id})
        return pts

    def s_plumbing(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        for f in self.scene.fixtures:
            if f.type == "warm_floor" and f.size:
                w, d = f.size
                rect = [(f.position[0] - w / 2, f.position[1] - d / 2), (f.position[0] + w / 2, f.position[1] - d / 2), (f.position[0] + w / 2, f.position[1] + d / 2), (f.position[0] - w / 2, f.position[1] + d / 2)]
                pv.poly(rect, fill=HexColor("#fbe4dc"), stroke=TERRA, lw=0.3, dash=(2, 1))
                pv.hatch(rect, TERRA, 2.2, 0, 0.2)
        self.draw_walls(pv, self.scene)
        for o in self.scene.objects:
            if o.category in ("toilet", "vanity", "bathtub", "shower", "washer", "kitchen_run", "dishwasher"):
                fp = footprint(o)
                pv.poly(fp.corners(), fill=None, stroke=GREY, lw=0.35)
        risers = [f for f in self.scene.fixtures if f.type.startswith("riser")]
        pts = self.plumbing_points()
        colors = {"cold": BLUE, "hot": RED, "drain": HexColor("#6b6b6b")}
        for p in pts:
            src = min(risers, key=lambda f: dist(f.position, p["pos"])) if risers else None
            water = next((f for f in self.scene.fixtures if f.type in ("water_cold", "drain") and f.room_id == p["room_id"]), None)
            if water and (not src or dist(water.position, p["pos"]) < dist(src.position, p["pos"])):
                src = water
            if src:
                a, b = src.position, p["pos"]
                mid = (b[0], a[1])
                dash = None if p["kind"] != "drain" else (3, 1.5)
                off = {"cold": 0, "hot": 60, "drain": -60}[p["kind"]]
                pv.line((a[0] + off, a[1] + off), (mid[0] + off, mid[1] + off), colors[p["kind"]], 0.5, dash)
                pv.line((mid[0] + off, mid[1] + off), (b[0], b[1]), colors[p["kind"]], 0.5, dash)
            px, py = pv.p(*p["pos"])
            draw_symbol(c, px, py, "drain" if p["kind"] == "drain" else "water", colors[p["kind"]], 2.2 * mm)
            pv.text(p["pos"][0] + 160, p["pos"][1] - 120, f"{p['id']} h={p['height']}", 4.5, color=colors[p["kind"]], anchor="start")
        for f in self.scene.fixtures:
            px, py = pv.p(*f.position)
            if f.type.startswith("riser"):
                draw_symbol(c, px, py, "riser", BLUE if f.type == "riser_water" else HexColor("#6b6b6b"), 3 * mm)
                pv.text(f.position[0], f.position[1] - 250, tx("riser_w" if f.type == "riser_water" else "riser_s", self.lang), 5, bold=True)
            elif f.type == "radiator" and f.size:
                w, d = f.size
                pv.poly([(f.position[0] - w / 2, f.position[1] - d / 2), (f.position[0] + w / 2, f.position[1] - d / 2), (f.position[0] + w / 2, f.position[1] + d / 2), (f.position[0] - w / 2, f.position[1] + d / 2)], fill=TERRA, stroke=INK, lw=0.3)
        self.room_labels(pv, self.scene, area=False)
        rows = [[p["id"], {"cold": t("cold_water", self.lang), "hot": t("hot_water", self.lang), "drain": t("sewer", self.lang)}[p["kind"]], cat_label(p["object"].category, self.lang), str(p["height"])] for p in pts]
        table(c, DRAW_AREA[2] - 92 * mm, DRAW_AREA[3] - 2 * mm, [("ID", 13 * mm), (t("type", self.lang), 26 * mm), (t("product", self.lang), 35 * mm), (f"h, {tx('u_mm', self.lang)}", 18 * mm)], rows, size=5.6, row_h=4.0 * mm, max_y=DRAW_AREA[1] + 5 * mm)
        legend = [LegendItem("line", BLUE, t("cold_water", self.lang)), LegendItem("line", RED, t("hot_water", self.lang)), LegendItem("dash", HexColor("#6b6b6b"), t("sewer", self.lang)),
                  LegendItem("symbol", BLUE, t("riser", self.lang), {"symbol": "riser"}), LegendItem("fill", TERRA, t("radiator", self.lang)), LegendItem("hatch", TERRA, t("warm_floor", self.lang))]
        self.page(c, spec, code, pv.scale, legend)

    def s_drywall_plan(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        self.draw_walls(pv, self.scene, mode="construction")
        for w in self.scene.walls:
            if w.material == "drywall":
                pv.dim(w.a, w.b, 450, size=5, color=GREEN)
                mid = along(w, wall_length(w) / 2)
                pv.text(mid[0] + 250, mid[1] + 250, f"{tx('gkl', self.lang)}-{w.id}", 6, bold=True, color=GREEN, anchor="start")
        for f in self.scene.fixtures:
            if f.type == "ventilation" and f.size:
                w, d = f.size
                rect = [(f.position[0] - w, f.position[1] - d), (f.position[0] + w, f.position[1] - d), (f.position[0] + w, f.position[1] + d), (f.position[0] - w, f.position[1] + d)]
                pv.poly(rect, fill=HexColor("#e6efe1"), stroke=GREEN, lw=0.4, dash=(2, 1))
                pv.text(f.position[0], f.position[1] + d + 200, tx("gkl_box", self.lang), 5, color=GREEN)
        self.room_labels(pv, self.scene, area=False)
        self.page(c, spec, code, pv.scale, [LegendItem("hatch", GREEN, t("drywall", self.lang))])

    def s_drywall(self, c, spec, code):
        rows = []
        for w in self.scene.walls:
            if w.material != "drywall":
                continue
            L = wall_length(w) / 1000
            H = (w.height or self.scene.ceiling_height) / 1000
            rows.append([f"{tx('gkl', self.lang)}-{w.id}", f"{L:.2f}", f"{H:.2f}", f"{L * H:.2f}", f"{w.thickness:.0f}", tx("gkl_profile", self.lang), tx("gkl_layers", self.lang)])
        table(c, DRAW_AREA[0] + 5 * mm, DRAW_AREA[3] - 5 * mm, [("ID", 18 * mm), (t("length", self.lang) + f", {tx('u_m', self.lang)}", 22 * mm), (t("height", self.lang) + f", {tx('u_m', self.lang)}", 22 * mm), (tx("u_m2", self.lang), 18 * mm),
                                                                   (f"t, {tx('u_mm', self.lang)}", 16 * mm), (t("profile", self.lang), 60 * mm), (t("layers", self.lang), 95 * mm)], rows or [["—"] * 7], size=6.5)
        # generic section detail through a drywall partition
        x, yb, s = DRAW_AREA[0] + 20 * mm, DRAW_AREA[1] + 20 * mm, 0.9 * mm  # 1 drawing-mm = 0.9 paper-mm (≈1:1.1 detail)
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        total = 12.5 * 2 + 75 + 12.5 * 2
        layers = [(12.5, "#efe9df"), (12.5, "#efe9df"), (75, "#fdf7d8"), (12.5, "#efe9df"), (12.5, "#efe9df")]
        xx = x
        for wdt, col in layers:
            c.setFillColor(hexc(col))
            c.rect(xx, yb, wdt * s, 110 * mm, fill=1, stroke=1)
            xx += wdt * s
        c.setDash(2, 2)
        for k in range(8):
            c.line(x + 25 * s, yb + k * 14 * mm, x + 100 * s, yb + k * 14 * mm + 7 * mm)
        c.setDash()
        text(c, x + total * s + 6 * mm, yb + 100 * mm, tx("gkl_node", self.lang), 8, bold=True)
        notes = [tx(f"gkl_n{i}", self.lang) for i in range(1, 6)]
        for i, n in enumerate(notes):
            text(c, x + total * s + 6 * mm, yb + 92 * mm - i * 5 * mm, n, 6.8)
        self.page(c, spec, code, None)

    def s_sockets(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        self.draw_walls(pv, self.scene)
        for o in self.scene.objects:
            fp = footprint(o)
            pv.poly(fp.corners(), fill=None, stroke=LIGHT, lw=0.3)
        for e in self.scene.electrical:
            px, py = pv.p(*e.position)
            col = RED if e.type.startswith("switch") else HexColor("#c0392b") if e.height >= 900 else INK
            draw_symbol(c, px, py, e.type, col, 2.6 * mm)
            pv.text(e.position[0] + 170, e.position[1] - 100, f"{e.code}", 4.6, bold=True, color=col, anchor="start")
            pv.text(e.position[0] + 170, e.position[1] + 120, f"h={e.height:.0f}", 4.2, color=GREY, anchor="start")
        self.room_labels(pv, self.scene, area=False)
        notes = [tx(f"el_n{i}", self.lang) for i in range(1, 4)]
        for i, n in enumerate(notes):
            text(c, DRAW_AREA[0] + 2 * mm, DRAW_AREA[1] + 2 * mm + i * 3.3 * mm, n, 6, color=GREY)
        types = sorted({e.type for e in self.scene.electrical})
        legend = [LegendItem("symbol", RED if tp.startswith("switch") else INK, elec_label(tp, self.lang), {"symbol": tp}) for tp in types]
        self.page(c, spec, code, pv.scale, legend)

    def s_sockets_list(self, c, spec, code):
        rows = []
        for e in self.scene.electrical:
            r = self.scene.room(e.room_id or "")
            rows.append([e.code, elec_label(e.type, self.lang), "1", f"{e.height:.0f}", room_name(r, self.lang) if r else "—", elec_note(e, self.lang)])
        cols = [("ID", 16 * mm), (t("type", self.lang), 62 * mm), (t("qty", self.lang), 14 * mm), (t("height", self.lang) + f", {tx('u_mm', self.lang)}", 22 * mm), (t("room", self.lang), 40 * mm), (t("note", self.lang), 100 * mm)]
        table(c, DRAW_AREA[0] + 5 * mm, DRAW_AREA[3] - 5 * mm, cols, rows, size=6.2, row_h=4.6 * mm, max_y=DRAW_AREA[1] + 4 * mm)
        cnt = Counter(elec_label(e.type, self.lang) for e in self.scene.electrical)
        y = DRAW_AREA[3] - 5 * mm
        x = DRAW_AREA[2] - 60 * mm
        text(c, x, y, t("total", self.lang), 8, bold=True)
        for i, (k, v) in enumerate(sorted(cnt.items())):
            text(c, x, y - 6 * mm - i * 4 * mm, f"{k}: {v}", 6.5)
        self.page(c, spec, code, None)

    def s_lighting(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        self.draw_walls(pv, self.scene)
        for o in self.scene.objects:
            pv.poly(footprint(o).corners(), fill=None, stroke=LIGHT, lw=0.3)
        switches = [e for e in self.scene.electrical if e.type.startswith("switch")]
        for li in self.scene.lights:
            if li.type == "led_strip" and li.end:
                pv.line(li.position, li.end, HexColor("#e0a800"), 1.0, (3, 1.5))
                continue
            if li.type == "track" and li.end:
                pv.line(li.position, li.end, INK, 1.4)
            px, py = pv.p(*li.position)
            draw_symbol(c, px, py, li.type if li.type in ("spot", "pendant", "ceiling", "wall") else "spot", INK, 3 * mm)
            pv.text(li.position[0] + 150, li.position[1] - 160, li.switch_group, 5, bold=True, color=TERRA, anchor="start")
            sw = min((s for s in switches if s.room_id == li.room_id), key=lambda s: dist(s.position, li.position), default=None)
            if sw and li.type in ("pendant", "ceiling"):
                pv.line(li.position, sw.position, TERRA, 0.3, (1, 1.5))
        for s in switches:
            px, py = pv.p(*s.position)
            draw_symbol(c, px, py, s.type, RED, 2.6 * mm)
        self.room_labels(pv, self.scene, area=False)
        L = self.lang
        legend = [LegendItem("symbol", INK, tx("l_spot", L), {"symbol": "spot"}), LegendItem("symbol", INK, tx("l_pendant", L), {"symbol": "pendant"}),
                  LegendItem("symbol", INK, tx("l_wall", L), {"symbol": "wall"}), LegendItem("line", INK, tx("l_track", L)), LegendItem("dash", HexColor("#e0a800"), tx("l_led", L)),
                  LegendItem("symbol", RED, tx("l_switch", L), {"symbol": "switch"})]
        self.page(c, spec, code, pv.scale, legend)

    def s_lighting_list(self, c, spec, code):
        groups: dict[tuple, list] = defaultdict(list)
        for li in self.scene.lights:
            groups[(li.type, li.room_id, li.product_variant_id, li.scenario, li.switch_group)].append(li)
        rows = []
        for (tp, room_id, ref, scen, grp), ls in groups.items():
            r = self.scene.room(room_id or "")
            ln = self.lines_by_ref.get(ref) or {}
            qty = len(ls) if tp != "led_strip" else f"{sum(dist(x.position, x.end) for x in ls if x.end) / 1000:.1f} {tx('u_m', self.lang)}"
            rows.append([", ".join(x.code for x in ls[:3]) + ("…" if len(ls) > 3 else ""), tx(LIGHT_KEYS.get(tp, ""), self.lang) if tp in LIGHT_KEYS else tp, str(qty), f"{sum(x.power_w for x in ls):.0f} W", scen, grp, room_name(r, self.lang) if r else "—",
                         (ln.get("name") or "—")[:40], ln.get("supplier") or "—"])
        cols = [("ID", 28 * mm), (t("type", self.lang), 20 * mm), (t("qty", self.lang), 16 * mm), (t("power", self.lang), 18 * mm), (t("scenario", self.lang), 20 * mm),
                (t("group", self.lang), 14 * mm), (t("room", self.lang), 34 * mm), (t("product", self.lang), 70 * mm), (t("supplier", self.lang), 50 * mm)]
        table(c, DRAW_AREA[0] + 5 * mm, DRAW_AREA[3] - 5 * mm, cols, rows, size=6.2, row_h=4.8 * mm, max_y=DRAW_AREA[1] + 4 * mm)
        self.page(c, spec, code, None)

    def s_ceiling(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        fills = {"paint": "#f6f4f0", "gkl_flat": "#efeae2", "gkl_multilevel": "#e7ddcf", "stretch": "#e2ebf1", "shadow_gap": "#ece6dc", "cove": "#efe1cf"}
        for cs in self.scene.ceilings:
            r = self.scene.room(cs.room_id)
            if not r:
                continue
            pv.poly(r.polygon, fill=hexc(fills.get(cs.type, "#eee")), stroke=None)
            if cs.type in ("gkl_multilevel", "shadow_gap", "cove"):
                x0, y0, x1, y1 = bbox(r.polygon)
                inset = 350 if cs.type == "gkl_multilevel" else 30
                pv.poly([(x0 + inset, y0 + inset), (x1 - inset, y0 + inset), (x1 - inset, y1 - inset), (x0 + inset, y1 - inset)], fill=None, stroke=TERRA, lw=0.4, dash=(3, 1.5))
            if cs.curtain_niche:
                x0, y0, x1, y1 = bbox(r.polygon)
                pv.poly([(x0, y0), (x1, y0), (x1, y0 + 160), (x0, y0 + 160)], fill=HexColor("#d9cfc2"), stroke=INK, lw=0.3)
            cx, cy = label_point(r.polygon)
            pv.text(cx, cy + 350, f"+{cs.height:.0f}", 6.5, bold=True, color=TERRA)
            pv.text(cx, cy + 700, CEILING_TYPES.get(cs.type, {}).get(self.lang, cs.type), 5, color=GREY)
        self.draw_walls(pv, self.scene)
        for li in self.scene.lights:
            if li.type in ("spot", "pendant", "ceiling", "track"):
                px, py = pv.p(*li.position)
                draw_symbol(c, px, py, li.type if li.type != "track" else "spot", INK, 2.6 * mm)
            if li.type == "led_strip" and li.end:
                pv.line(li.position, li.end, HexColor("#e0a800"), 0.8, (3, 1.5))
        self.room_labels(pv, self.scene, area=False)
        legend = [LegendItem("fill", hexc(fills[k]), CEILING_TYPES[k][self.lang]) for k in fills if any(cs.type == k for cs in self.scene.ceilings)]
        self.page(c, spec, code, pv.scale, legend)

    def s_ceiling_nodes(self, c, spec, code):
        x0, y0, x1, y1 = DRAW_AREA
        w3 = (x1 - x0) / 3
        details = [(tx("d_shadow", self.lang), self._detail_shadow), (tx("d_niche", self.lang), self._detail_niche), (tx("d_cove", self.lang), self._detail_cove)]
        for i, (title, fn) in enumerate(details):
            cx0 = x0 + i * w3 + 6 * mm
            text(c, cx0, y1 - 10 * mm, f"{i + 1}. {title}", 8, bold=True)
            fn(c, cx0 + 4 * mm, y0 + 40 * mm, w3 - 18 * mm)
            text(c, cx0, y0 + 25 * mm, f"{t('scale', self.lang)} 1:5", 6.5, color=GREY)
        self.page(c, spec, code, 5)

    def _slab(self, c, x, y, w):
        c.setFillColor(HexColor("#c9c3bb"))
        c.rect(x, y + 120 * mm, w, 18 * mm, fill=1, stroke=1)
        c.saveState()
        p = c.beginPath()
        p.rect(x, y + 120 * mm, w, 18 * mm)
        c.clipPath(p, stroke=0, fill=0)
        c.setStrokeColor(GREY)
        for k in range(0, int(w / mm) + 30, 3):
            c.line(x + k * mm, y + 120 * mm, x + k * mm - 18 * mm, y + 138 * mm)
        c.restoreState()

    def _detail_shadow(self, c, x, y, w):
        self._slab(c, x, y, w)
        c.setStrokeColor(INK)
        c.setFillColor(HexColor("#efe9df"))
        c.rect(x, y + 40 * mm, 14 * mm, 80 * mm, fill=1, stroke=1)  # wall
        c.rect(x + 16 * mm, y + 100 * mm, w - 16 * mm, 4 * mm, fill=1, stroke=1)  # gkl
        c.setFillColor(white)
        c.rect(x + 14 * mm, y + 100 * mm, 2 * mm, 4 * mm, fill=1, stroke=1)
        c.line(x + 30 * mm, y + 104 * mm, x + 30 * mm, y + 120 * mm)
        text(c, x + 32 * mm, y + 110 * mm, tx("d_hanger", self.lang), 6)
        text(c, x + 18 * mm, y + 94 * mm, tx("d_shadow_profile", self.lang), 6)

    def _detail_niche(self, c, x, y, w):
        self._slab(c, x, y, w)
        c.setStrokeColor(INK)
        c.setFillColor(HexColor("#efe9df"))
        c.rect(x, y + 20 * mm, 14 * mm, 100 * mm, fill=1, stroke=1)
        c.rect(x + 30 * mm, y + 100 * mm, w - 30 * mm, 4 * mm, fill=1, stroke=1)
        c.rect(x + 30 * mm, y + 100 * mm, 4 * mm, 20 * mm, fill=1, stroke=1)
        c.setStrokeColor(TERRA)
        c.line(x + 18 * mm, y + 112 * mm, x + 26 * mm, y + 112 * mm)
        text(c, x + 14 * mm, y + 90 * mm, tx("d_niche160", self.lang), 6)
        text(c, x + 14 * mm, y + 85 * mm, tx("d_niche_backing", self.lang), 6)

    def _detail_cove(self, c, x, y, w):
        self._slab(c, x, y, w)
        c.setStrokeColor(INK)
        c.setFillColor(HexColor("#efe9df"))
        c.rect(x, y + 20 * mm, 14 * mm, 100 * mm, fill=1, stroke=1)
        c.rect(x + 14 * mm, y + 88 * mm, 40 * mm, 4 * mm, fill=1, stroke=1)
        c.rect(x + 50 * mm, y + 92 * mm, 4 * mm, 10 * mm, fill=1, stroke=1)
        c.rect(x + 54 * mm, y + 104 * mm, w - 54 * mm, 4 * mm, fill=1, stroke=1)
        c.setFillColor(HexColor("#f5c542"))
        c.rect(x + 44 * mm, y + 93 * mm, 4 * mm, 2 * mm, fill=1, stroke=0)
        text(c, x + 16 * mm, y + 80 * mm, tx("d_led", self.lang), 6)
        text(c, x + 16 * mm, y + 75 * mm, tx("d_psu", self.lang), 6)

    # ------------------------------------------------------------ ДН2 finishing
    def floor_pattern(self, pv: PlanView, poly, pattern: str):
        if pattern == "herringbone":
            pv.hatch(poly, hexc(FLOOR_PATTERN_COLOR), 1.2, 45, 0.2)
            pv.hatch(poly, hexc(FLOOR_PATTERN_COLOR), 3.6, -45, 0.2)
        elif pattern == "plank":
            pv.hatch(poly, hexc(FLOOR_PATTERN_COLOR), 1.6, 0, 0.2)
        elif pattern in ("tile_grid", "large_tile"):
            step = 1.5 if pattern == "large_tile" else 0.8
            pv.hatch(poly, GREY, step * 10 / pv.scale * 4, 0, 0.2)
            pv.hatch(poly, GREY, step * 10 / pv.scale * 4, 90, 0.2)

    def s_floors(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        legend = []
        seen = set()
        rows = []
        for f in self.scene.finishes:
            if f.surface != "floor":
                continue
            r = self.scene.room(f.room_id)
            if not r:
                continue
            pv.poly(r.polygon, fill=hexc(f.color_hex), stroke=None, alpha=0.55)
            self.floor_pattern(pv, r.polygon, f.pattern)
            if f.product_variant_id not in seen:
                seen.add(f.product_variant_id)
                legend.append(LegendItem("fill", hexc(f.color_hex), f"{f.material_code} {f.name[:38]}"))
            rows.append([f.material_code, room_name(r, self.lang), f"{polygon_area(r.polygon) / 1e6:.2f}", f.pattern])
        self.draw_walls(pv, self.scene)
        self.room_labels(pv, self.scene)
        table(c, DRAW_AREA[2] - 80 * mm, DRAW_AREA[3] - 2 * mm, [(tx("code_col", self.lang), 14 * mm), (t("room", self.lang), 30 * mm), (tx("u_m2", self.lang), 14 * mm), (tx("layout_col", self.lang), 22 * mm)], rows, size=6, row_h=4.4 * mm)
        self.page(c, spec, code, pv.scale, legend)

    def s_doors(self, c, spec, code):
        doors = [o for o in self.scene.openings if o.type in ("door", "entrance_door", "sliding_door", "balcony_door")]
        x0 = DRAW_AREA[0] + 15 * mm
        y_top = DRAW_AREA[3] - 10 * mm
        head_w = 70 * mm
        col_w = min(48 * mm, (DRAW_AREA[2] - x0 - head_w - 5 * mm) / max(1, len(doors)))
        rows_h = [10 * mm, 10 * mm, 10 * mm, 30 * mm, 62 * mm]
        labels = ["ID", t("size", self.lang), t("opening_dir", self.lang), t("plan_view", self.lang), t("elev_view", self.lang)]
        y = y_top
        c.setStrokeColor(INK)
        c.setLineWidth(0.3)
        for lab, h in zip(labels, rows_h):
            c.rect(x0, y - h, head_w, h, fill=0, stroke=1)
            text(c, x0 + 2 * mm, y - h / 2 - 1 * mm, lab, 7, bold=True)
            for i, d in enumerate(doors):
                cx = x0 + head_w + i * col_w
                c.rect(cx, y - h, col_w, h, fill=0, stroke=1)
                if lab == "ID":
                    text(c, cx + col_w / 2, y - h / 2 - 1 * mm, f"{tx('door', self.lang)}-{i + 1:02d} ({d.id})", 7, anchor="middle")
                elif lab == labels[1]:
                    text(c, cx + col_w / 2, y - h / 2 - 1 * mm, f"{d.width:.0f}×{d.height:.0f}", 7, anchor="middle")
                elif lab == labels[2]:
                    text(c, cx + col_w / 2, y - h / 2 - 1 * mm, "—" if d.type == "sliding_door" else tx("left" if d.swing == "left" else "right", self.lang), 7, anchor="middle")
                elif lab == labels[3]:
                    ox, oy = cx + col_w / 2 - 12 * mm, y - h + 8 * mm
                    c.line(ox, oy, ox + 24 * mm, oy)
                    if d.type == "sliding_door":
                        c.setLineWidth(1)
                        c.line(ox + 2 * mm, oy + 1.5 * mm, ox + 16 * mm, oy + 1.5 * mm)
                        c.line(ox + 8 * mm, oy + 3 * mm, ox + 22 * mm, oy + 3 * mm)
                        c.setLineWidth(0.3)
                    else:
                        R = 20 * mm
                        hx = ox + 2 * mm if d.hinge == "start" else ox + 22 * mm
                        c.line(hx, oy, hx, oy + R)
                        c.arc(hx - R, oy - R, hx + R, oy + R, 0 if d.hinge == "start" else 90, 90)
                else:
                    ln = self.lines_by_ref.get(d.product_variant_id) or {}
                    dw, dh = col_w * 0.55, h * 0.78
                    ex, ey = cx + (col_w - dw) / 2, y - h + 5 * mm
                    c.setFillColor(hexc(ln.get("color_hex") or "#efe9df"))
                    c.rect(ex, ey, dw, dh, fill=1, stroke=1)
                    c.setFillColor(INK)
                    hx = ex + dw - 2.5 * mm if d.hinge == "start" else ex + 1.5 * mm
                    c.rect(hx, ey + dh * 0.45, 1 * mm, 3 * mm, fill=1, stroke=0)
                    text(c, cx + col_w / 2, y - h + 1.5 * mm, wrap(ln.get("name") or "—", col_w - 2 * mm, 5)[0], 5, anchor="middle")
            y -= h
        self.page(c, spec, code, None)

    def s_walls(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        for r in self.scene.rooms:
            pv.poly(r.polygon, fill=HexColor("#faf8f4"), stroke=None)
        self.draw_walls(pv, self.scene, hatch_existing=False)
        legend = []
        seen = set()
        for f in self.scene.finishes:
            if f.surface not in ("walls", "wet_walls", "accent_wall", "apron"):
                continue
            r = self.scene.room(f.room_id)
            if not r:
                continue
            poly = r.polygon
            inset = {"walls": 60, "wet_walls": 60, "accent_wall": 140, "apron": 220}[f.surface]
            for i in range(len(poly)):
                a, b = poly[i], poly[(i + 1) % len(poly)]
                if f.surface == "accent_wall" and dist(a, b) < max(dist(poly[k], poly[(k + 1) % len(poly)]) for k in range(len(poly))) - 1:
                    continue
                if f.surface == "apron":
                    run = next((o for o in self.scene.objects if o.room_id == r.id and o.category == "kitchen_run"), None)
                    if not run:
                        continue
                    fp = footprint(run)
                    a, b = (fp.x0, fp.y0), (fp.x1, fp.y0)
                nx, ny = normal(a, b)
                mid = ((a[0] + b[0]) / 2 + nx * 30, (a[1] + b[1]) / 2 + ny * 30)
                s = 1 if point_in_polygon(mid, poly) else -1
                pv.line((a[0] + nx * inset * s, a[1] + ny * inset * s), (b[0] + nx * inset * s, b[1] + ny * inset * s), hexc(f.color_hex), 2.2)
            key = (f.product_variant_id, f.surface)
            if key not in seen:
                seen.add(key)
                legend.append(LegendItem("line", hexc(f.color_hex), f"{f.material_code} · {f.surface}: {f.name[:30]}"))
        self.room_labels(pv, self.scene, area=False, names=True)
        self.page(c, spec, code, pv.scale, legend)

    def s_materials(self, c, spec, code):
        rows, colors = [], []
        for f in self.scene.finishes:
            ln = self.lines_by_ref.get(f.product_variant_id) or {}
            r = self.scene.room(f.room_id)
            rows.append(["", f.material_code, f.surface, room_name(r, self.lang) if r else "—", f.name[:44], ln.get("supplier") or "—", ln.get("sku") or "—",
                         f"{ln.get('area_m2') or '—'}", ln.get("price_status") or "—"])
            colors.append(hexc(f.color_hex))
        cols = [("", 10 * mm), (tx("code_col", self.lang), 14 * mm), (tx("surface", self.lang), 24 * mm), (t("room", self.lang), 32 * mm), (t("product", self.lang), 80 * mm), (t("supplier", self.lang), 44 * mm),
                ("SKU", 40 * mm), (tx("m2_total", self.lang), 18 * mm), (t("status", self.lang), 22 * mm)]
        table(c, DRAW_AREA[0] + 5 * mm, DRAW_AREA[3] - 5 * mm, cols, rows, size=6.2, row_h=6 * mm, colors=colors, max_y=DRAW_AREA[1] + 4 * mm)
        self.page(c, spec, code, None)

    def s_furniture_plan(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        self.draw_walls(pv, self.scene)
        for o in self.scene.objects:
            fp = footprint(o)
            pv.poly(fp.corners(), fill=hexc(o.color_hex), stroke=GREEN, lw=0.5, alpha=0.25 if o.category == "rug" else 0.5)
            if o.category != "rug":
                pv.text(o.x, o.y + 60, o.code, 5, bold=True)
                if fp.w > 900 and o.category not in ("dining_chair",):
                    pv.dim((fp.x0, fp.y0), (fp.x1, fp.y0), 120, size=4.2, color=GREEN)
        self.room_labels(pv, self.scene, area=False)
        self.room_table(c, self.scene)
        self.page(c, spec, code, pv.scale, [LegendItem("fill", HexColor("#cfe5c8"), tx("furn_legend", self.lang))])

    def furniture_rows(self) -> list[list[str]]:
        rows = []
        for o in self.scene.objects:
            ln = self.lines_by_ref.get(o.product_variant_id) or {}
            r = self.scene.room(o.room_id)
            price = ln.get("unit_price")
            rows.append([o.code, cat_label(o.category, self.lang), (o.name or "—")[:40], room_name(r, self.lang) if r else "—", f"{o.w:.0f}×{o.d:.0f}×{o.h:.0f}",
                         ln.get("supplier") or "—", ln.get("sku") or "—", fmt_amd(price), ln.get("price_status") or ("concept" if o.mode == "concept" else "—")])
        return rows

    def s_furniture(self, c, spec, code):
        rows = spec.arg or []
        cols = [(tx("code_col", self.lang), 14 * mm), (t("type", self.lang), 34 * mm), (t("product", self.lang), 70 * mm), (t("room", self.lang), 30 * mm), (t("dims", self.lang) + f", {tx('u_mm', self.lang)}", 30 * mm),
                (t("supplier", self.lang), 40 * mm), ("SKU", 40 * mm), (t("price", self.lang) + ", AMD", 22 * mm), (t("status", self.lang), 20 * mm)]
        table(c, DRAW_AREA[0] + 3 * mm, DRAW_AREA[3] - 5 * mm, cols, rows, size=6.2, row_h=5.4 * mm, max_y=DRAW_AREA[1] + 3 * mm)
        self.page(c, spec, code, None)

    # ------------------------------------------------------------ ДН3 elevations
    def s_elev_key(self, c, spec, code):
        pv = self.new_plan(c, margin=1200)
        self.draw_walls(pv, self.scene)
        for o in self.scene.objects:
            pv.poly(footprint(o).corners(), fill=None, stroke=LIGHT, lw=0.3)
        for r in self.scene.rooms:
            if r.type == "balcony":
                continue
            cx, cy = label_point(r.polygon)
            for k, (dx, dy) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0)), 1):
                px, py = cx + dx * 500, cy + dy * 500
                pv.line((cx, cy), (px, py), TERRA, 0.4)
                ppx, ppy = pv.p(px, py)
                c.setFillColor(TERRA)
                c.circle(ppx, ppy, 2.2 * mm, fill=1, stroke=0)
                text(c, ppx, ppy - 1 * mm, f"{r.number}.{k}", 4.6, bold=True, color=white, anchor="middle")
        self.room_labels(pv, self.scene, area=False, names=True)
        self.page(c, spec, code, pv.scale, [LegendItem("symbol", TERRA, tx("elev_legend", self.lang), {"symbol": "riser"})])

    def elevation(self, c, room, edge_idx: int, rect, label: str):
        from ..scene.geometry import room_edges

        edges = room_edges(self.scene, room, door_clearance=0)
        if edge_idx >= len(edges):
            return
        e = edges[edge_idx]
        L = e.length
        H = room.ceiling_height
        rx0, ry0, rx1, ry1 = rect
        k = min((rx1 - rx0 - 16 * mm) / L, (ry1 - ry0 - 18 * mm) / H)
        ox = rx0 + ((rx1 - rx0) - L * k) / 2
        oy = ry0 + 10 * mm
        wall_col = next((f.color_hex for f in self.scene.finishes if f.room_id == room.id and f.surface in ("wet_walls",)), None) or \
            next((f.color_hex for f in self.scene.finishes if f.room_id == room.id and f.surface == "walls"), "#f3efe9")
        c.setFillColor(hexc(wall_col))
        c.setStrokeColor(INK)
        c.setLineWidth(0.6)
        c.rect(ox, oy, L * k, H * k, fill=1, stroke=1)
        ux, uy = unit(e.a, e.b)
        # openings on this wall
        if e.wall_id:
            w = self.scene.wall(e.wall_id)
            for o in self.scene.openings:
                if o.wall_id != e.wall_id:
                    continue
                p0, p1 = along(w, o.offset), along(w, o.offset + o.width)
                t0 = (p0[0] - e.a[0]) * ux + (p0[1] - e.a[1]) * uy
                t1 = (p1[0] - e.a[0]) * ux + (p1[1] - e.a[1]) * uy
                lo, hi = sorted((t0, t1))
                if hi < 0 or lo > L:
                    continue
                lo, hi = max(0, lo), min(L, hi)
                z0 = o.sill if o.type == "window" else 0
                z1 = min(H, (o.sill + o.height) if o.type == "window" else o.height)
                c.setFillColor(HexColor("#d6e6f0") if o.type in ("window", "balcony_door") else HexColor("#e8dccb"))
                c.rect(ox + lo * k, oy + z0 * k, (hi - lo) * k, (z1 - z0) * k, fill=1, stroke=1)
                if o.type in ("window", "balcony_door"):
                    c.line(ox + (lo + hi) / 2 * k, oy + z0 * k, ox + (lo + hi) / 2 * k, oy + z1 * k)
                self._edim(c, ox + lo * k, ox + hi * k, oy - 4 * mm, f"{hi - lo:.0f}")
                self._vdim(c, ox + hi * k + 2 * mm, oy + z0 * k, oy + z1 * k, f"{z1 - z0:.0f}")
        # objects against this wall
        for o in self.scene.objects:
            if o.room_id != room.id or o.category == "rug":
                continue
            fp = footprint(o)
            # distance from the wall line along the inward normal
            d_back = min(abs((cx - e.a[0]) * e.inward[0] + (cy - e.a[1]) * e.inward[1]) for cx, cy in fp.corners())
            if d_back > 120:
                continue
            ts = [(cx - e.a[0]) * ux + (cy - e.a[1]) * uy for cx, cy in fp.corners()]
            lo, hi = max(0, min(ts)), min(L, max(ts))
            if hi - lo < 50:
                continue
            z0 = o.elevation
            z1 = z0 + (o.h if o.category != "kitchen_run" else 900)
            c.setFillColor(hexc(o.color_hex))
            c.setStrokeColor(INK)
            c.setLineWidth(0.5)
            c.rect(ox + lo * k, oy + z0 * k, (hi - lo) * k, (z1 - z0) * k, fill=1, stroke=1)
            if o.category == "kitchen_run":
                n = max(2, int((hi - lo) // 600))
                for m_ in range(1, n):
                    xx = ox + (lo + (hi - lo) * m_ / n) * k
                    c.line(xx, oy + 100 * k, xx, oy + 860 * k)
                    c.line(xx, oy + 1500 * k, xx, oy + 2250 * k)
                c.rect(ox + lo * k, oy + 1500 * k, (hi - lo) * k, 750 * k, fill=1, stroke=1)
                c.setFillColor(HexColor("#e8e2d9"))
                c.rect(ox + lo * k, oy + 900 * k, (hi - lo) * k, 600 * k, fill=1, stroke=1)
                self._vdim(c, ox + lo * k - 3 * mm, oy, oy + 900 * k, "900")
                self._vdim(c, ox + lo * k - 3 * mm, oy + 900 * k, oy + 1500 * k, "600")
            elif o.category in ("wardrobe", "hallway_wardrobe", "storage_system"):
                n = max(2, int((hi - lo) // 500))
                for m_ in range(1, n):
                    xx = ox + (lo + (hi - lo) * m_ / n) * k
                    c.line(xx, oy + z0 * k, xx, oy + z1 * k)
            text(c, ox + (lo + hi) / 2 * k, oy + z1 * k + 1.5 * mm, o.code, 5, bold=True, anchor="middle")
            self._edim(c, ox + lo * k, ox + hi * k, oy - 8 * mm, f"{hi - lo:.0f}")
        # sockets on this wall
        for el in self.scene.electrical:
            if el.room_id != room.id:
                continue
            dd = abs((el.position[0] - e.a[0]) * e.inward[0] + (el.position[1] - e.a[1]) * e.inward[1])
            if dd > 120:
                continue
            tt = (el.position[0] - e.a[0]) * ux + (el.position[1] - e.a[1]) * uy
            if 0 <= tt <= L:
                draw_symbol(c, ox + tt * k, oy + el.height * k, el.type, RED if el.type.startswith("switch") else INK, 2 * mm)
        self._edim(c, ox, ox + L * k, oy - 12 * mm, f"{L:.0f}")
        self._vdim(c, ox + L * k + 8 * mm, oy, oy + H * k, f"{H:.0f}")
        text(c, rx0 + 2 * mm, ry1 - 4 * mm, label, 7, bold=True, color=TERRA)

    def _edim(self, c, x0, x1, y, s):
        c.setStrokeColor(INK)
        c.setLineWidth(0.25)
        c.line(x0, y, x1, y)
        for x in (x0, x1):
            c.line(x - 0.8 * mm, y - 0.8 * mm, x + 0.8 * mm, y + 0.8 * mm)
        text(c, (x0 + x1) / 2, y + 0.8 * mm, s, 4.6, anchor="middle")

    def _vdim(self, c, x, y0, y1, s):
        c.setStrokeColor(INK)
        c.setLineWidth(0.25)
        c.line(x, y0, x, y1)
        for y in (y0, y1):
            c.line(x - 0.8 * mm, y - 0.8 * mm, x + 0.8 * mm, y + 0.8 * mm)
        c.saveState()
        c.translate(x - 0.8 * mm, (y0 + y1) / 2)
        c.rotate(90)
        text(c, 0, 0, s, 4.6, anchor="middle")
        c.restoreState()

    def s_elevations(self, c, spec, code):
        room, edge_ids = spec.arg
        x0, y0, x1, y1 = DRAW_AREA
        cells = [(x0, (y0 + y1) / 2, (x0 + x1) / 2, y1), ((x0 + x1) / 2, (y0 + y1) / 2, x1, y1), (x0, y0, (x0 + x1) / 2, (y0 + y1) / 2), ((x0 + x1) / 2, y0, x1, (y0 + y1) / 2)]
        for cell, ei in zip(cells, edge_ids):
            self.elevation(c, room, ei, cell, f"{room.number}.{ei + 1}")
        c.setStrokeColor(LIGHT)
        c.line((x0 + x1) / 2, y0, (x0 + x1) / 2, y1)
        c.line(x0, (y0 + y1) / 2, x1, (y0 + y1) / 2)
        self.page(c, spec, code, 50)

    # ------------------------------------------------------------ ДН4 visualisation
    def s_visual(self, c, spec, code):
        room = spec.arg
        x0, y0, x1, y1 = DRAW_AREA
        cams = [cm for cm in self.scene.cameras if cm.room_id == room.id][:3]
        n = max(1, len(cams))
        gap = 4 * mm
        w = (x1 - x0 - gap * (n - 1)) / n
        if self.renders.get(room.id):
            self._photoreal(c, room, self.renders[room.id])
            self.page(c, spec, code, None)
            return
        faces = render3d.room_interior_faces(self.scene, room.id)
        for i, cam in enumerate(cams):
            rect = (x0 + i * (w + gap), y0 + 20 * mm, x0 + i * (w + gap) + w, y1 - 18 * mm)
            items = render3d.perspective(faces, (cam.position[0], cam.position[1], 1450), (cam.target[0], cam.target[1], 1150), fov_deg=72)
            self.draw_perspective(c, items, rect, fov_scale=1.0)
        text(c, x0, y0 + 12 * mm, t("schematic_note", self.lang), 6.5, color=GREY)
        text(c, x0, y1 - 10 * mm, f"{room.number}. {room_name(room, self.lang)} — {variant_title(self.variant, self.lang)}", 10, bold=True)
        self.page(c, spec, code, None)

    def _photoreal(self, c, room, renders):
        """AI visualisation sheet: the render (fit to the drawing area) + an honest caption with the
        product-match score and the items that are only visual analogs."""
        x0, y0, x1, y1 = DRAW_AREA
        jpeg, meta = renders[0]
        w, h = meta.get("width") or 16, meta.get("height") or 9
        aw, ah = x1 - x0, y1 - y0 - 34 * mm
        k = min(aw / w, ah / h)
        iw, ih = w * k, h * k
        c.drawImage(ImageReader(io.BytesIO(jpeg)), x0 + (aw - iw) / 2, y0 + 24 * mm + (ah - ih) / 2, iw, ih)
        text(c, x0, y1 - 8 * mm, f"{room.number}. {room_name(room, self.lang)} — {variant_title(self.variant, self.lang)}", 10, bold=True)
        g = meta.get("grounding") or {}
        score = g.get("score")
        cap = tx("ai_render", self.lang, model=meta.get("model", "")) + " · " + (
            tx("ai_render_match", self.lang, pct=round(score * 100)) if score is not None and g.get("verified", True) else tx("ai_render_unverified", self.lang))
        text(c, x0, y0 + 16 * mm, cap, 7.5, color=GREY)
        analogs = g.get("visual_analogs") or []
        if analogs:
            text(c, x0, y0 + 11 * mm, tx("ai_render_analogs", self.lang, codes=", ".join(analogs)), 7, color=RED)
        for i, ln in enumerate(wrap(tx("ai_render_note", self.lang), x1 - x0, 6.5)[:2]):
            text(c, x0, y0 + 6 * mm - i * 3.4 * mm, ln, 6.5, color=GREY)

    # ------------------------------------------------------------ ДН5 specification / estimate
    def s_spec(self, c, spec, code):
        rows = []
        for ln in self.est.get("lines", []):
            if not ln.get("ref"):
                continue
            rows.append([ln["id"], cat_label(ln.get("category", ""), self.lang), line_name(ln, self.lang)[:46], ln.get("supplier") or "—", ln.get("sku") or "—",
                         f"{ln['qty']} {unit_label(ln['unit'], self.lang)}", fmt_amd(ln.get("unit_price")), fmt_amd(ln.get("total")), shared(f"enum.price.{ln['price_status']}", self.lang), (ln.get("checked_at") or "")[:10] or "—"])
        rows = rows[spec.arg[0]:spec.arg[1]] if spec.arg else rows
        cols = [("№", 12 * mm), (tx("category", self.lang), 26 * mm), (t("product", self.lang), 72 * mm), (t("supplier", self.lang), 38 * mm), ("SKU", 38 * mm), (t("qty", self.lang), 22 * mm),
                (t("price", self.lang), 22 * mm), (t("sum", self.lang), 24 * mm), (t("status", self.lang), 20 * mm), (tx("checked", self.lang), 18 * mm)]
        table(c, DRAW_AREA[0] + 2 * mm, DRAW_AREA[3] - 5 * mm, cols, rows, size=5.9, row_h=4.9 * mm, max_y=DRAW_AREA[1] + 3 * mm)
        self.page(c, spec, code, None)

    def s_estimate(self, c, spec, code):
        tot = self.est.get("totals", {})
        rows = [[shared(f"enum.group.{s['group']}", self.lang, default=s["label"]), str(s["lines"]), fmt_amd(s["total"]), f"{s['share'] * 100:.0f}%", str(s["quote_required"])] for s in self.est.get("sections", [])]
        y = table(c, DRAW_AREA[0] + 5 * mm, DRAW_AREA[3] - 5 * mm, [(tx("est_section", self.lang), 70 * mm), (tx("items", self.lang), 20 * mm), (tx("sum_amd", self.lang), 34 * mm), (tx("share", self.lang), 16 * mm), (tx("on_request", self.lang), 22 * mm)], rows, size=7, row_h=6 * mm)
        y -= 10 * mm
        for key, val in (("tot_known", tot.get("known")), ("tot_confirmed", tot.get("confirmed")), ("tot_estimated", tot.get("estimated")), ("tot_demo", tot.get("demo")), ("tot_range", None)):
            text(c, DRAW_AREA[0] + 5 * mm, y, tx(key, self.lang), 8, bold=key == "tot_known")
            text(c, DRAW_AREA[0] + 160 * mm, y, fmt_amd(val) if val is not None else f"{fmt_amd(tot.get('range_low'))} – {fmt_amd(tot.get('range_high'))} AMD", 8, bold=key == "tot_known", anchor="end")
            y -= 6 * mm
        if self.est.get("budget"):
            b = self.est["budget"]
            text(c, DRAW_AREA[0] + 5 * mm, y, tx("budget_line", self.lang, target=fmt_amd(b["target"]), delta=fmt_amd(b["delta"])), 8, color=GREEN if b["within"] else RED)
            y -= 6 * mm
        y -= 4 * mm
        notes = [notice(n, self.lang) for n in self.est["notices"]] if self.est.get("notices") else self.est.get("disclaimers", [])
        for d in notes:
            for ln in wrap("• " + d, 170 * mm, 7):
                text(c, DRAW_AREA[0] + 5 * mm, y, ln, 7, color=GREY)
                y -= 4 * mm
        text(c, DRAW_AREA[0] + 5 * mm, y - 3 * mm, tx("est_generated", self.lang, at=self.est.get("generated_at", "")[:16].replace("T", " "), fx=self.est.get("fx_snapshot")), 6, color=GREY)
        # donut of shares
        cx, cy, r = DRAW_AREA[2] - 70 * mm, DRAW_AREA[3] - 70 * mm, 45 * mm
        palette = ["#c97f63", "#8f9f7e", "#d9c9b7", "#2e2e2e", "#b98f6a", "#6f8fae", "#e0a800", "#a4593c", "#5c5248", "#cfc6bb", "#7a7068", "#efe6da"]
        start = 90.0
        for i, s in enumerate(self.est.get("sections", [])):
            ext = 360 * s["share"]
            if ext <= 0:
                continue
            c.setFillColor(hexc(palette[i % len(palette)]))
            c.wedge(cx - r, cy - r, cx + r, cy + r, start, ext, fill=1, stroke=0)
            text(c, cx + r + 6 * mm, cy + r - i * 5 * mm, "■ " + shared("enum.group." + s["group"], self.lang, default=s["label"]), 6.5, color=hexc(palette[i % len(palette)]))
            start += ext
        c.setFillColor(white)
        c.circle(cx, cy, r * 0.55, fill=1, stroke=0)
        text(c, cx, cy + 1 * mm, fmt_amd(tot.get("known")), 9, bold=True, anchor="middle")
        text(c, cx, cy - 4 * mm, "AMD", 7, color=GREY, anchor="middle")
        self.page(c, spec, code, None)

    def s_suppliers(self, c, spec, code):
        by: dict[str, dict] = {}
        for ln in self.est.get("lines", []):
            k = ln.get("supplier")
            if not k:
                continue
            d = by.setdefault(k, {"items": 0, "sum": 0, "lead": 0, "quote": 0})
            d["items"] += 1
            d["sum"] += ln.get("total") or 0
            d["lead"] = max(d["lead"], ln.get("lead_days") or 0)
            d["quote"] += ln.get("total") is None
        rows = [[k, str(v["items"]), fmt_amd(v["sum"]), tx("days", self.lang, n=v["lead"]) if v["lead"] else "—", str(v["quote"])] for k, v in sorted(by.items(), key=lambda kv: -kv[1]["sum"])]
        table(c, DRAW_AREA[0] + 5 * mm, DRAW_AREA[3] - 5 * mm, [(t("supplier", self.lang), 80 * mm), (tx("items", self.lang), 20 * mm), (tx("sum_amd", self.lang), 34 * mm), (tx("max_lead", self.lang), 24 * mm), ("RFQ", 16 * mm)], rows, size=7, row_h=6 * mm)
        # timeline (Gantt-like) of works
        stages = [(tx(f"st_{k}", self.lang), a, b) for k, a, b in (("demolition", 0, 5), ("rough", 4, 12), ("partitions", 8, 18), ("screed", 14, 21), ("tile", 21, 30), ("ceilings", 26, 34),
                                                                   ("paint", 32, 44), ("floors", 42, 48), ("doors", 46, 52), ("custom", 50, 58), ("delivery", 52, 60))]
        gx, gy, gw = DRAW_AREA[0] + 5 * mm, DRAW_AREA[1] + 75 * mm, 230 * mm
        text(c, gx, gy + 8 * mm, tx("schedule_title", self.lang), 8, bold=True)
        for i, (name, s, e) in enumerate(stages):
            y = gy - i * 5.5 * mm
            text(c, gx, y, name, 6.3)
            c.setFillColor(TERRA if i % 2 == 0 else SAGE)
            c.rect(gx + 70 * mm + s / 60 * (gw - 70 * mm), y - 0.5 * mm, (e - s) / 60 * (gw - 70 * mm), 3.2 * mm, fill=1, stroke=0)
        self.qr(c, DRAW_AREA[2] - 55 * mm, DRAW_AREA[1] + 10 * mm, 45 * mm, self.viewer_url)
        text(c, DRAW_AREA[2] - 55 * mm, DRAW_AREA[1] + 6 * mm, tx("scene_qr", self.lang), 6.5, color=GREY)
        for i, ln in enumerate(wrap(self.viewer_url, 55 * mm, 5.5)[:3]):
            text(c, DRAW_AREA[2] - 55 * mm, DRAW_AREA[1] + 2.5 * mm - i * 2.5 * mm, ln, 5.5, color=GREY)
        self.page(c, spec, code, None)

    def s_approval(self, c, spec, code):
        x, y = DRAW_AREA[0] + 5 * mm, DRAW_AREA[3] - 8 * mm
        text(c, x, y, tx("accuracy", self.lang, v=self.meta.accuracy_label), 10, bold=True)
        y -= 7 * mm
        dims = ", ".join(f"{cd.wall_id}={cd.measured_mm:.0f}" for cd in self.base.control_dimensions) or tx("none", self.lang)
        text(c, x, y, tx("confidence", self.lang, pct=f"{self.project.get('confidence', 0) * 100:.0f}", dims=dims), 7.5)
        y -= 9 * mm
        text(c, x, y, tx("assumptions", self.lang), 8.5, bold=True)
        y -= 5 * mm
        for a in self.base.assumptions:
            for ln in wrap(f"[{severity(a.severity, self.lang)}] {assumption_text(a, self.lang)}", 180 * mm, 7):
                text(c, x, y, ln, 7, color=RED if a.severity == "critical" else INK)
                y -= 4 * mm
        y -= 4 * mm
        text(c, x, y, tx("rule_checks", self.lang), 8.5, bold=True)
        y -= 5 * mm
        for iss in [i for i in self.issues if i["severity"] != "pass"][:14]:
            for ln in wrap(f"[{severity(iss['severity'], self.lang)}] {rule_text(iss, self.lang)}", 180 * mm, 6.8):
                text(c, x, y, ln, 6.8, color=RED if iss["severity"] == "block" else INK)
                y -= 3.8 * mm
        # approvals / signatures
        sx = DRAW_AREA[0] + 200 * mm
        sy = DRAW_AREA[3] - 8 * mm
        text(c, sx, sy, tx("approval_log", self.lang), 8.5, bold=True)
        sy -= 6 * mm
        for ap in self.approvals[:8]:
            text(c, sx, sy, f"{ap['created_at'][:16].replace('T', ' ')} · {ap['actor_name']} ({ap['actor_role']}) — {tx('dec_' + ap['decision'], self.lang) if 'dec_' + ap['decision'] in TX else ap['decision']}", 6.8)
            sy -= 4.2 * mm
        if not self.approvals:
            text(c, sx, sy, tx("not_approved", self.lang), 6.8, color=GREY)
            sy -= 4.2 * mm
        sy -= 10 * mm
        for role in (tx("sign_designer", self.lang), tx("sign_specialist", self.lang), tx("sign_client", self.lang)):
            c.setStrokeColor(INK)
            c.line(sx, sy, sx + 110 * mm, sy)
            text(c, sx, sy - 4 * mm, tx("sign_line", self.lang, role=role), 6.5, color=GREY)
            sy -= 16 * mm
        for ln in wrap(tx("ai_disclaimer", self.lang), 110 * mm, 6.5):
            text(c, sx, sy, ln, 6.5, color=GREY)
            sy -= 3.6 * mm
        self.page(c, spec, code, None)

    # ------------------------------------------------------------ assembly
    def specs(self) -> list[SheetSpec]:
        s: list[SheetSpec] = [
            SheetSpec("measure", 1, "s_measure", self.s_measure), SheetSpec("demolish", 1, "s_demolish", self.s_demolish), SheetSpec("new", 1, "s_new", self.s_new),
            SheetSpec("axo", 1, "s_axo", self.s_axo), SheetSpec("zoning", 1, "s_zoning", self.s_zoning), SheetSpec("plumbing", 1, "s_plumbing", self.s_plumbing),
            SheetSpec("drywall_plan", 1, "s_drywall_plan", self.s_drywall_plan), SheetSpec("drywall", 1, "s_drywall", self.s_drywall),
            SheetSpec("sockets", 1, "s_sockets", self.s_sockets), SheetSpec("sockets_list", 1, "s_sockets_list", self.s_sockets_list),
            SheetSpec("lighting", 1, "s_lighting", self.s_lighting), SheetSpec("lighting_list", 1, "s_lighting_list", self.s_lighting_list),
            SheetSpec("ceiling", 1, "s_ceiling", self.s_ceiling), SheetSpec("ceiling_nodes", 1, "s_ceiling_nodes", self.s_ceiling_nodes),
            SheetSpec("floors", 2, "s_floors", self.s_floors), SheetSpec("doors", 2, "s_doors", self.s_doors), SheetSpec("walls", 2, "s_walls", self.s_walls),
            SheetSpec("materials", 2, "s_materials", self.s_materials), SheetSpec("furniture_plan", 2, "s_furniture_plan", self.s_furniture_plan),
        ]
        rows = self.furniture_rows()
        per = 30
        for i in range(0, max(1, len(rows)), per):
            s.append(SheetSpec(f"furniture_{i // per}", 2, "s_furniture", self.s_furniture, rows[i:i + per]))
        s.append(SheetSpec("elev_key", 3, "s_elev_key", self.s_elev_key))
        from ..scene.geometry import room_edges

        for r in self.scene.rooms:
            if r.type in ("balcony",):
                continue
            n = len(room_edges(self.scene, r))
            for start in range(0, n, 4):
                s.append(SheetSpec(f"elev_{r.id}_{start}", 3, "s_elev_key", self.s_elevations, (r, list(range(start, min(n, start + 4)))), title_override=room_name(r, self.lang)))
        for r in self.scene.rooms:
            if r.type in ("balcony",):
                continue
            s.append(SheetSpec(f"visual_{r.id}", 4, "s_visual", self.s_visual, r, title_override=room_name(r, self.lang)))
        spec_rows = [ln for ln in self.est.get("lines", []) if ln.get("ref")]
        per = 32
        for i in range(0, max(1, len(spec_rows)), per):
            s.append(SheetSpec(f"spec_{i // per}", 5, "s_spec", self.s_spec, (i, i + per)))
        s += [SheetSpec("estimate", 5, "s_estimate", self.s_estimate), SheetSpec("suppliers", 5, "s_suppliers", self.s_suppliers), SheetSpec("approval", 5, "s_approval", self.s_approval)]
        return s

    def build(self, sections: set[int] | None = None) -> tuple[bytes, list[dict]]:
        from .draw import ensure_fonts

        ensure_fonts()
        from . import draw as _draw

        buf = io.BytesIO()
        # initial font = embedded Unicode font, so no page references a non-embedded base-14 font (print preflight)
        c = Canvas(buf, pagesize=(PAGE_W, PAGE_H), initialFontName=_draw.FONT)
        c.setTitle(f"{t('album_title', self.lang)} — {self.meta.project_address}")
        c.setAuthor(self.meta.company)
        c.setCreator(self.meta.brand)
        specs = [sp for sp in self.specs() if not sections or sp.section in sections]
        counters: dict[int, int] = defaultdict(int)
        codes = []
        for sp in specs:
            counters[sp.section] += 1
            codes.append(self.code(sp.section, counters[sp.section]))
        self.meta.total_sheets = len(specs) + 2
        self.cover(c, specs)
        c.showPage()
        self.toc(c, specs, codes)
        c.showPage()
        sheets = []
        for sp, code in zip(specs, codes):
            sp.fn(c, sp, code)
            c.showPage()
            sheets.append({"code": code, "key": sp.key, "section": sp.section, "title": sp.title_override or t(sp.title_key, self.lang)})
        c.save()
        return buf.getvalue(), sheets


# keep imports referenced for linters
_ = (FRAME, TB_W, SAND)
