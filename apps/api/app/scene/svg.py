"""Server-side SVG plan rendering (previews, thumbnails, client viewer fallback)."""
from __future__ import annotations

import math
from xml.sax.saxutils import escape

from .geometry import (
    along,
    footprint,
    label_point,
    normal,
    polygon_area,
    scene_bbox,
    wall_outline,
    wall_solid_segments,
)
from .model import Scene

ZONE_FILL = {"day": "#f3e3d3", "night": "#e3e8dc", "wet": "#dde7ee", "service": "#efe9df", "outdoor": "#eef0ea"}


def render_svg(scene: Scene, *, show_objects=True, show_issues: list[dict] | None = None, width_px: int = 1200, layers: set[str] | None = None) -> str:
    x0, y0, x1, y1 = scene_bbox(scene)
    pad = 600
    vb = (x0 - pad, y0 - pad, (x1 - x0) + 2 * pad, (y1 - y0) + 2 * pad)
    h_px = int(width_px * vb[3] / vb[2])
    layers = layers or {"rooms", "walls", "openings", "objects", "labels", "fixtures"}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]:.0f} {vb[1]:.0f} {vb[2]:.0f} {vb[3]:.0f}" width="{width_px}" height="{h_px}" font-family="DejaVu Sans, Arial">',
           f'<rect x="{vb[0]}" y="{vb[1]}" width="{vb[2]}" height="{vb[3]}" fill="#fbf8f3"/>']
    if "rooms" in layers:
        for r in scene.rooms:
            pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in r.polygon)
            out.append(f'<polygon points="{pts}" fill="{ZONE_FILL.get(r.zone or "", "#f4efe8")}" stroke="none" data-room="{r.id}"/>')
    if "walls" in layers:
        for w in scene.walls:
            if w.status == "demolish" and "demolition" not in layers:
                continue
            color = {"existing": "#3b3631", "demolish": "#d9534f", "new": "#6f8f5b"}[w.status]
            for s, e in wall_solid_segments(w, scene.openings):
                pts = " ".join(f"{x:.0f},{y:.0f}" for x, y in wall_outline(w, s, e))
                fill = color if w.status != "demolish" else "url(#hatch)"
                out.append(f'<polygon points="{pts}" fill="{fill}" stroke="{color}" stroke-width="10" data-wall="{w.id}"/>')
        out.insert(2, '<defs><pattern id="hatch" width="80" height="80" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="80" height="80" fill="#f6d5d3"/><line x1="0" y1="0" x2="0" y2="80" stroke="#d9534f" stroke-width="18"/></pattern></defs>')
    if "openings" in layers:
        for o in scene.openings:
            w = scene.wall(o.wall_id)
            if not w:
                continue
            p0, p1 = along(w, o.offset), along(w, o.offset + o.width)
            nx, ny = normal(w.a, w.b)
            ht = w.thickness / 2
            if o.type in ("window",):
                for k in (-ht, 0, ht):
                    out.append(f'<line x1="{p0[0] + nx * k:.0f}" y1="{p0[1] + ny * k:.0f}" x2="{p1[0] + nx * k:.0f}" y2="{p1[1] + ny * k:.0f}" stroke="#4a7fa8" stroke-width="18"/>')
            elif o.type in ("door", "entrance_door", "balcony_door"):
                side = 1 if o.swing == "left" else -1
                hinge, free = (p0, p1) if o.hinge == "start" else (p1, p0)
                hx, hy = hinge[0] + nx * ht * side, hinge[1] + ny * ht * side
                leaf = (hx + nx * o.width * side, hy + ny * o.width * side)
                fx, fy = free[0] + nx * ht * side, free[1] + ny * ht * side
                sweep = 1 if (o.hinge == "start") == (side > 0) else 0
                out.append(f'<line x1="{hx:.0f}" y1="{hy:.0f}" x2="{leaf[0]:.0f}" y2="{leaf[1]:.0f}" stroke="#2e2e2e" stroke-width="22"/>')
                out.append(f'<path d="M {leaf[0]:.0f} {leaf[1]:.0f} A {o.width:.0f} {o.width:.0f} 0 0 {sweep} {fx:.0f} {fy:.0f}" fill="none" stroke="#2e2e2e" stroke-width="8" stroke-dasharray="40 30"/>')
            elif o.type == "sliding_door":
                out.append(f'<line x1="{p0[0]:.0f}" y1="{p0[1]:.0f}" x2="{p1[0]:.0f}" y2="{p1[1]:.0f}" stroke="#2e2e2e" stroke-width="30"/>')
    if "fixtures" in layers:
        for f in scene.fixtures:
            w, d = f.size or (180, 180)
            if f.type == "warm_floor":
                continue
            color = {"radiator": "#c97f63", "riser_water": "#4a7fa8", "riser_sewer": "#6b6b6b", "electrical_panel": "#e0a800"}.get(f.type, "#999")
            out.append(f'<rect x="{f.position[0] - w / 2:.0f}" y="{f.position[1] - d / 2:.0f}" width="{w:.0f}" height="{d:.0f}" fill="{color}" opacity="0.8"/>')
    if show_objects and "objects" in layers:
        for o in scene.objects:
            fp = footprint(o)
            op = 0.35 if o.category == "rug" else 0.9
            out.append(f'<rect x="{fp.x0:.0f}" y="{fp.y0:.0f}" width="{fp.w:.0f}" height="{fp.h:.0f}" fill="{o.color_hex}" fill-opacity="{op}" stroke="#5b4636" stroke-width="12" rx="30" data-object="{o.id}"/>')
            fx, fy = (-math.sin(math.radians(o.rotation)), math.cos(math.radians(o.rotation)))
            if o.category not in ("rug",):
                out.append(f'<line x1="{o.x:.0f}" y1="{o.y:.0f}" x2="{o.x + fx * min(fp.w, fp.h) * 0.45:.0f}" y2="{o.y + fy * min(fp.w, fp.h) * 0.45:.0f}" stroke="#5b4636" stroke-width="10"/>')
            out.append(f'<text x="{o.x:.0f}" y="{o.y:.0f}" font-size="120" text-anchor="middle" fill="#2e2e2e">{escape(o.code)}</text>')
    if "labels" in layers:
        for r in scene.rooms:
            cx, cy = label_point(r.polygon)
            out.append(f'<circle cx="{cx:.0f}" cy="{cy - 260:.0f}" r="150" fill="#fff" stroke="#c97f63" stroke-width="16"/>')
            out.append(f'<text x="{cx:.0f}" y="{cy - 215:.0f}" font-size="150" text-anchor="middle" fill="#c97f63">{r.number}</text>')
            out.append(f'<text x="{cx:.0f}" y="{cy + 20:.0f}" font-size="150" text-anchor="middle" fill="#2e2e2e">{escape(r.name)}</text>')
            out.append(f'<text x="{cx:.0f}" y="{cy + 200:.0f}" font-size="130" text-anchor="middle" fill="#7a7068">{polygon_area(r.polygon) / 1e6:.2f} м²</text>')
    for iss in show_issues or []:
        ids = set(iss.get("element_ids") or [])
        for o in scene.objects:
            if o.id in ids and iss["severity"] != "pass":
                fp = footprint(o)
                c = "#d9534f" if iss["severity"] == "block" else "#e0a800"
                out.append(f'<rect x="{fp.x0 - 40:.0f}" y="{fp.y0 - 40:.0f}" width="{fp.w + 80:.0f}" height="{fp.h + 80:.0f}" fill="none" stroke="{c}" stroke-width="25" stroke-dasharray="60 40"/>')
    out.append("</svg>")
    return "".join(out)
