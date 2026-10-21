"""Tiny vector 3D renderer (painter's algorithm) for axonometric sheets and
schematic room visualisations. Output: 2D polygons with colours, drawn by ReportLab.
These are honest model views — photoreal renders come from a render provider."""
from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass

from ..scene.geometry import along, footprint, room_edges, unit, wall_outline, wall_solid_segments
from ..scene.model import Scene

Vec = tuple[float, float, float]


@dataclass
class Face:
    pts: list[Vec]
    color: str
    stroke: str | None = "#4a4440"
    lw: float = 0.25
    bias: float = 0.0  # depth bias (negative = drawn later)
    layer: int = 3  # 0 floor/ceiling, 1 room walls, 2 openings/rugs, 3 objects & building walls
    group: str = ""  # faces of one object are sorted together (painter per object, then per face)


def shade(hex_: str, factor: float) -> str:
    h = hex_.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    ll = max(0, min(1, ll * factor))
    r, g, b = colorsys.hls_to_rgb(hh, ll, ss)
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


def box_faces(x0, y0, x1, y1, z0, z1, color, stroke="#4a4440") -> list[Face]:
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    faces = [Face([(x, y, z1) for x, y in c], shade(color, 1.12), stroke)]
    sides = [((x0, y0), (x1, y0), 0.78), ((x1, y0), (x1, y1), 0.9), ((x1, y1), (x0, y1), 1.0), ((x0, y1), (x0, y0), 0.86)]
    for a, b, f in sides:
        faces.append(Face([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], shade(color, f), stroke))
    return faces


def quad_prism(outline: list[tuple[float, float]], z0: float, z1: float, color: str, stroke="#3b3631", top_color: str | None = None) -> list[Face]:
    faces = [Face([(x, y, z1) for x, y in outline], top_color or shade(color, 1.15), stroke)]
    n = len(outline)
    for i in range(n):
        a, b = outline[i], outline[(i + 1) % n]
        f = 0.75 + 0.25 * abs(math.sin(math.atan2(b[1] - a[1], b[0] - a[0])))
        faces.append(Face([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)], shade(color, f), stroke))
    return faces


def wall_faces(scene: Scene, statuses: set[str], colors: dict[str, str], height: float | None = None, cut_height: float | None = None) -> list[Face]:
    H = height or scene.ceiling_height
    faces: list[Face] = []
    for w in scene.walls:
        if w.status not in statuses:
            continue
        color = colors.get(w.status, "#f2efea")
        top = cut_height or H
        for s, e in wall_solid_segments(w, scene.openings):
            faces += quad_prism(wall_outline(w, s, e), 0, top, color)
        for o in scene.openings:
            if o.wall_id != w.id:
                continue
            head = min(top, o.sill + o.height) if o.type != "opening" else min(top, o.height)
            if head < top:
                faces += quad_prism(wall_outline(w, o.offset, o.offset + o.width), head, top, color)
            if o.type == "window" and o.sill > 0:
                faces += quad_prism(wall_outline(w, o.offset, o.offset + o.width), 0, min(o.sill, top), color)
            if o.type == "window" and o.sill < top:
                p0, p1 = along(w, o.offset), along(w, o.offset + o.width)
                faces.append(Face([(p0[0], p0[1], o.sill), (p1[0], p1[1], o.sill), (p1[0], p1[1], min(head, top)), (p0[0], p0[1], min(head, top))], "#cfe0ec", "#6b8fae", 0.3, bias=-1))
    return faces


def floor_faces(scene: Scene, finishes: bool = True) -> list[Face]:
    out = []
    for r in scene.rooms:
        col = "#efe9df"
        if finishes:
            f = next((x for x in scene.finishes if x.room_id == r.id and x.surface == "floor"), None)
            if f:
                col = f.color_hex
        out.append(Face([(x, y, 0) for x, y in r.polygon], col, "#bdb4a9", 0.2, layer=0))
    return out


def object_faces(scene: Scene, room_id: str | None = None) -> list[Face]:
    out: list[Face] = []
    for o in scene.objects:
        start = len(out)
        _object_faces(o, out)
        for f in out[start:]:
            f.group = o.id
        if room_id and o.room_id != room_id:
            del out[start:]
    return out


def _object_faces(o, out: list[Face]) -> None:
    fp = footprint(o)
    h = max(20, o.h)
    if o.category == "rug":
        out.append(Face([(fp.x0, fp.y0, 8), (fp.x1, fp.y0, 8), (fp.x1, fp.y1, 8), (fp.x0, fp.y1, 8)], o.color_hex, None, layer=2))
        return
    if o.category in ("bed", "kids_bed"):
        out += box_faces(fp.x0, fp.y0, fp.x1, fp.y1, 0, 450, o.color_hex)
        # headboard on the back side
        fx, fy = (-math.sin(math.radians(o.rotation)), math.cos(math.radians(o.rotation)))
        t = 80
        if abs(fy) > 0.5:
            y0b = fp.y0 if fy > 0 else fp.y1 - t
            out += box_faces(fp.x0, y0b, fp.x1, y0b + t, 0, h, shade(o.color_hex, 0.8))
        else:
            x0b = fp.x0 if fx > 0 else fp.x1 - t
            out += box_faces(x0b, fp.y0, x0b + t, fp.y1, 0, h, shade(o.color_hex, 0.8))
        return
    if o.category == "sofa":
        out += box_faces(fp.x0, fp.y0, fp.x1, fp.y1, 0, 420, o.color_hex)
        fx, fy = (-math.sin(math.radians(o.rotation)), math.cos(math.radians(o.rotation)))
        t = 220
        if abs(fy) > 0.5:
            y0b = fp.y0 if fy > 0 else fp.y1 - t
            out += box_faces(fp.x0, y0b, fp.x1, y0b + t, 0, h, shade(o.color_hex, 0.92))
        else:
            x0b = fp.x0 if fx > 0 else fp.x1 - t
            out += box_faces(x0b, fp.y0, x0b + t, fp.y1, 0, h, shade(o.color_hex, 0.92))
        return
    if o.category in ("dining_table", "desk", "coffee_table"):
        top = h
        out += box_faces(fp.x0, fp.y0, fp.x1, fp.y1, top - 40, top, o.color_hex)
        leg = 50
        for lx, ly in ((fp.x0, fp.y0), (fp.x1 - leg, fp.y0), (fp.x1 - leg, fp.y1 - leg), (fp.x0, fp.y1 - leg)):
            out += box_faces(lx, ly, lx + leg, ly + leg, 0, top - 40, shade(o.color_hex, 0.7))
        return
    if o.category == "kitchen_run":
        out += box_faces(fp.x0, fp.y0, fp.x1, fp.y1, 0, 860, o.color_hex)
        out += box_faces(fp.x0, fp.y0, fp.x1, fp.y1, 860, 900, "#e8e4de")
        # upper cabinets against the wall (35 cm deep)
        fx, fy = (-math.sin(math.radians(o.rotation)), math.cos(math.radians(o.rotation)))
        d = 350
        if abs(fy) > 0.5:
            yy = fp.y0 if fy > 0 else fp.y1 - d
            out += box_faces(fp.x0, yy, fp.x1, yy + d, 1500, 2250, shade(o.color_hex, 1.05))
        else:
            xx = fp.x0 if fx > 0 else fp.x1 - d
            out += box_faces(xx, fp.y0, xx + d, fp.y1, 1500, 2250, shade(o.color_hex, 1.05))
        return
    z0 = o.elevation
    out += box_faces(fp.x0, fp.y0, fp.x1, fp.y1, z0, z0 + h, o.color_hex)


# ---------------------------------------------------------------- projections
def axonometric(faces: list[Face], angle_deg: float = 35.0, elev_deg: float = 32.0) -> list[tuple[list[tuple[float, float]], Face]]:
    a = math.radians(angle_deg)
    e = math.radians(elev_deg)
    ca, sa, ce, se = math.cos(a), math.sin(a), math.cos(e), math.sin(e)

    def proj(p: Vec):
        x, y, z = p
        x1 = x * ca - y * sa
        y1 = x * sa + y * ca
        return (x1, -y1 * se + z * ce), y1 * ce + z * se

    items = []
    for f in faces:
        pts, depths = zip(*(proj(p) for p in f.pts))
        items.append((0 if f.layer == 0 else 1, sum(depths) / len(depths) - f.bias, list(pts), f))
    gdepth: dict[str, list[float]] = {}
    for _, d, _, f in items:
        if f.group:
            gdepth.setdefault(f.group, []).append(d)
    gd = {g: sum(v) / len(v) for g, v in gdepth.items()}
    items.sort(key=lambda t: (t[0], gd.get(t[3].group, t[1]), t[1]))
    return [(pts, f) for _, _, pts, f in items]


def perspective(faces: list[Face], eye: Vec, target: Vec, fov_deg: float = 70.0, near: float = 120.0) -> list[tuple[list[tuple[float, float]], Face]]:
    fx, fy, fz = target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]
    L = math.sqrt(fx * fx + fy * fy + fz * fz) or 1
    f = (fx / L, fy / L, fz / L)
    up = (0.0, 0.0, 1.0)
    # right = up × f  (plan Y points down → this keeps the image un-mirrored)
    r = (up[1] * f[2] - up[2] * f[1], up[2] * f[0] - up[0] * f[2], up[0] * f[1] - up[1] * f[0])
    rl = math.sqrt(sum(v * v for v in r)) or 1
    r = (r[0] / rl, r[1] / rl, r[2] / rl)
    u = (f[1] * r[2] - f[2] * r[1], f[2] * r[0] - f[0] * r[2], f[0] * r[1] - f[1] * r[0])
    if u[2] < 0:
        u = (-u[0], -u[1], -u[2])
    focal = 1 / math.tan(math.radians(fov_deg) / 2)

    def cam(p: Vec) -> Vec:
        d = (p[0] - eye[0], p[1] - eye[1], p[2] - eye[2])
        return (d[0] * r[0] + d[1] * r[1] + d[2] * r[2], d[0] * u[0] + d[1] * u[1] + d[2] * u[2], d[0] * f[0] + d[1] * f[1] + d[2] * f[2])

    def clip(poly: list[Vec]) -> list[Vec]:
        out: list[Vec] = []
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            ain, bin_ = a[2] >= near, b[2] >= near
            if ain:
                out.append(a)
            if ain != bin_:
                t = (near - a[2]) / (b[2] - a[2])
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, near))
        return out

    items = []
    for fc in faces:
        cp = clip([cam(p) for p in fc.pts])
        if len(cp) < 3:
            continue
        pts = [(x / z * focal, y / z * focal) for x, y, z in cp]
        depth = sum(z for _, _, z in cp) / len(cp)
        items.append((fc.layer, depth, pts, fc))
    gdepth: dict[str, list[float]] = {}
    for _, d, _, fc in items:
        if fc.group:
            gdepth.setdefault(fc.group, []).append(d)
    gd = {g: sum(v) / len(v) for g, v in gdepth.items()}
    # envelope layers first, then objects far → near (whole object), then faces far → near
    items.sort(key=lambda t: (t[0], -(gd.get(t[3].group, t[1])), -t[1]))
    return [(pts, fc) for _, _, pts, fc in items]


def room_interior_faces(scene: Scene, room_id: str) -> list[Face]:
    """Faces of one room seen from inside: inner wall faces, openings, floor, objects."""
    room = scene.room(room_id)
    H = room.ceiling_height if room else scene.ceiling_height
    wall_col = "#f1ece5"
    paint = next((x for x in scene.finishes if x.room_id == room_id and x.surface in ("walls",)), None)
    wet = next((x for x in scene.finishes if x.room_id == room_id and x.surface == "wet_walls"), None)
    if paint:
        wall_col = paint.color_hex
    if wet:
        wall_col = wet.color_hex
    faces: list[Face] = []
    edges = room_edges(scene, room, door_clearance=0)
    accent = next((x for x in scene.finishes if x.room_id == room_id and x.surface == "accent_wall"), None)
    longest = max(edges, key=lambda e: e.length) if edges else None
    for e in edges:
        col = accent.color_hex if accent and e is longest else wall_col
        faces.append(Face([(e.a[0], e.a[1], 0), (e.b[0], e.b[1], 0), (e.b[0], e.b[1], H), (e.a[0], e.a[1], H)], col, "#b8afa4", 0.3, layer=1))
        if not e.wall_id:
            continue
        w = scene.wall(e.wall_id)
        ux, uy = unit(e.a, e.b)
        for o in scene.openings:
            if o.wall_id != e.wall_id:
                continue
            p0, p1 = along(w, o.offset), along(w, o.offset + o.width)
            t0 = (p0[0] - e.a[0]) * ux + (p0[1] - e.a[1]) * uy
            t1 = (p1[0] - e.a[0]) * ux + (p1[1] - e.a[1]) * uy
            lo, hi = sorted((t0, t1))
            if hi < 0 or lo > e.length:
                continue
            lo, hi = max(0, lo), min(e.length, hi)
            q0 = (e.a[0] + ux * lo + e.inward[0] * 5, e.a[1] + uy * lo + e.inward[1] * 5)
            q1 = (e.a[0] + ux * hi + e.inward[0] * 5, e.a[1] + uy * hi + e.inward[1] * 5)
            z0 = o.sill if o.type == "window" else 0
            z1 = min(H - 10, (o.sill + o.height) if o.type == "window" else o.height)
            color = {"window": "#d6e6f0", "balcony_door": "#d6e6f0", "opening": "#e9e3da"}.get(o.type, "#e2d6c6")
            faces.append(Face([(q0[0], q0[1], z0), (q1[0], q1[1], z0), (q1[0], q1[1], z1), (q0[0], q0[1], z1)], color, "#8c8378", 0.4, layer=2))
    faces.append(Face([(x, y, 0) for x, y in room.polygon], next((x.color_hex for x in scene.finishes if x.room_id == room_id and x.surface == "floor"), "#d8c7b0"), None, layer=0))
    faces.append(Face([(x, y, H) for x, y in room.polygon], "#faf8f5", None, layer=0))
    faces += object_faces(scene, room_id)
    return faces
