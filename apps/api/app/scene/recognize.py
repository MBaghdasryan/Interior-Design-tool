"""Geometry recognition from source assets → draft BuildingGraph that the user
confirms on the review screen (green/yellow/red confidence mask)."""
from __future__ import annotations

import io
import math

import ezdxf

from .geometry import polygon_area
from .model import Assumption, Opening, Room, Scene, Wall

WALL_LAYER_HINTS = ("wall", "стен", "պատ", "a-wall", "mur")
ROOM_LAYER_HINTS = ("area", "room", "space", "помещ", "սենյակ", "a-area")


def from_dxf(data: bytes) -> Scene:
    doc = ezdxf.read(io.StringIO(data.decode("utf-8", errors="ignore")))
    msp = doc.modelspace()
    units = doc.units or 4  # 4 = mm
    k = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}.get(units, 1.0)
    layers = {e.dxf.layer for e in msp}
    wall_layers = {L for L in layers if any(h in L.lower() for h in WALL_LAYER_HINTS)} or layers
    room_layers = {L for L in layers if any(h in L.lower() for h in ROOM_LAYER_HINTS)}
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    rooms: list[list[tuple[float, float]]] = []
    for e in msp:
        lay = e.dxf.layer
        if e.dxftype() == "LINE" and lay in wall_layers:
            segs.append(((e.dxf.start.x * k, -e.dxf.start.y * k), (e.dxf.end.x * k, -e.dxf.end.y * k)))
        elif e.dxftype() == "LWPOLYLINE":
            pts = [(p[0] * k, -p[1] * k) for p in e.get_points("xy")]
            if lay in room_layers and e.closed and len(pts) >= 3:
                rooms.append(pts)
            elif lay in wall_layers:
                for i in range(len(pts) - (0 if e.closed else 1)):
                    segs.append((pts[i], pts[(i + 1) % len(pts)]))
    segs = [s for s in segs if math.dist(*s) >= 300]
    if not segs:
        raise ValueError("В DXF не найдено линий стен (слои *WALL*/стены)")
    xs = [p[0] for s in segs for p in s]
    ys = [p[1] for s in segs for p in s]
    ox, oy = min(xs), min(ys)
    walls = []
    for i, (a, b) in enumerate(segs, 1):
        walls.append(Wall(id=f"W{i}", a=(round(a[0] - ox), round(a[1] - oy)), b=(round(b[0] - ox), round(b[1] - oy)), thickness=120,
                          kind="interior", source="imported", confidence=0.6))
    out_rooms = []
    for i, poly in enumerate(rooms, 1):
        pts = [(round(x - ox), round(y - oy)) for x, y in poly]
        out_rooms.append(Room(id=f"R{i}", number=i, type="living", name=f"Помещение {i}", polygon=pts, source="imported", confidence=0.7))
    return Scene(name="Импорт DXF", walls=walls, rooms=out_rooms, assumptions=[
        Assumption(key="dxf_lines", text="Линии DXF приняты как осевые стен толщиной 120 мм — проверьте толщины и тип стен", severity="warning"),
        Assumption(key="dxf_rooms", text=f"Помещений из контуров: {len(out_rooms)}. Назначьте типы помещений", severity="warning" if out_rooms else "critical"),
    ])


def from_recognition(rec: dict, control: dict | None = None) -> Scene:
    """Converts a FloorplanRecognition (AI vision) result into a scene, applying a
    control dimension if provided."""
    walls = [Wall(id=w["id"], a=tuple(w["a"]), b=tuple(w["b"]), thickness=w["thickness"], kind=w["kind"], source="recognized", confidence=w["confidence"]) for w in rec["walls"]]
    openings = [Opening(id=o["id"], wall_id=o["wall_id"], type=o["type"], offset=o["offset"], width=o["width"], source="recognized", confidence=o["confidence"]) for o in rec["openings"]]
    rooms = []
    for i, r in enumerate(rec["rooms"], 1):
        rooms.append(Room(id=r["id"], number=i, type=r["type"] if r["type"] in Room.model_fields["type"].annotation.__args__ else "living", name=r["name"],
                          polygon=[tuple(p) for p in r["polygon"]], source="recognized", confidence=r["confidence"]))
    sc = Scene(name="Распознанный план", walls=walls, openings=openings, rooms=rooms, ceiling_height=rec.get("ceiling_height_mm") or 2700,
               assumptions=[Assumption(key=f"u{i}", text=u, severity="warning") for i, u in enumerate(rec.get("uncertainties", []))])
    for r_in, r in zip(rec["rooms"], sc.rooms):
        lab = r_in.get("area_label_m2")
        if lab:
            calc = polygon_area(r.polygon) / 1e6
            if abs(calc - lab) / lab > 0.08:
                sc.assumptions.append(Assumption(key=f"area_{r.id}", text=f"{r.name}: площадь по геометрии {calc:.2f} м² ≠ подписи {lab:.2f} м²", severity="warning", element_id=r.id))
    scaled = apply_control_dimension(sc, control)
    check_dimension_texts(sc, rec.get("dimension_texts") or [])
    if rec.get("scale_source") == "assumed" and not scaled:
        sc.assumptions.append(Assumption(key="scale", text="Масштаб не подтверждён — задайте контрольный размер хотя бы одной стены", severity="critical"))
    return sc


def apply_control_dimension(sc: Scene, control: dict | None) -> bool:
    """Rescales the whole recognised drawing so the control wall has its measured length.
    Returns True when a control dimension was applied (the scale is then measured, not assumed)."""
    from .geometry import wall_length
    from .model import ControlDimension

    if not control or not control.get("measured_mm"):
        return False
    w = next((x for x in sc.walls if x.id == control.get("wall_id")), None)
    if w is None:
        sc.assumptions.append(Assumption(key="control_wall", text=f"Контрольная стена {control.get('wall_id')} не найдена в распознанном плане — масштаб не проверен",
                                         severity="warning"))
        return False
    k = control["measured_mm"] / (wall_length(w) or 1)
    if abs(k - 1) > 0.005:
        for x in sc.walls:
            x.a, x.b = (x.a[0] * k, x.a[1] * k), (x.b[0] * k, x.b[1] * k)
        for o in sc.openings:
            o.offset, o.width = o.offset * k, o.width * k
        for r in sc.rooms:
            r.polygon = [(px * k, py * k) for px, py in r.polygon]
        sc.assumptions.append(Assumption(key="scale_corrected", text=f"Масштаб скорректирован по контрольному размеру {w.id}: ×{k:.3f}",
                                         severity="warning" if abs(k - 1) > 0.05 else "info", element_id=w.id))
    sc.control_dimensions = [ControlDimension(wall_id=w.id, measured_mm=control["measured_mm"])]
    return True


def check_dimension_texts(sc: Scene, texts: list[str]) -> None:
    """Cross-checks printed overall dimensions against the recognised extents (OCR sanity check)."""
    import re

    nums = []
    for t in texts:
        for m in re.findall(r"\d[\d\s,.]{2,}\d|\d{3,}", t):
            v = float(re.sub(r"[\s,]", "", m).replace(".", "")) if re.search(r"[\s,]\d{3}\b", m) else float(m.replace(",", ".").replace(" ", ""))
            if 500 <= v <= 40000:
                nums.append(v)
    if not nums or not sc.walls:
        return
    xs = [p for w in sc.walls for p in (w.a[0], w.b[0])]
    ys = [p for w in sc.walls for p in (w.a[1], w.b[1])]
    extents = [max(xs) - min(xs), max(ys) - min(ys)]
    biggest = max(nums)
    if not any(abs(biggest - e) / e <= 0.06 for e in extents if e):
        sc.assumptions.append(Assumption(key="dimension_mismatch", severity="warning",
                                         text=f"Наибольший размер на чертеже {biggest:.0f} мм не совпадает с габаритами распознанной геометрии "
                                              f"({extents[0]:.0f} × {extents[1]:.0f} мм) — проверьте масштаб"))


def confidence_mask(scene: Scene) -> dict:
    def level(c: float) -> str:
        return "green" if c >= 0.85 else "yellow" if c >= 0.6 else "red"

    return {
        "walls": {w.id: level(w.confidence) for w in scene.walls},
        "openings": {o.id: level(o.confidence) for o in scene.openings},
        "rooms": {r.id: level(r.confidence) for r in scene.rooms},
        "summary": {lvl: sum(1 for x in [*scene.walls, *scene.openings, *scene.rooms] if level(x.confidence) == lvl) for lvl in ("green", "yellow", "red")},
    }


def overall_confidence(scene: Scene) -> float:
    items = [*scene.walls, *scene.openings, *scene.rooms]
    if not items:
        return 0.0
    base = sum(x.confidence for x in items) / len(items)
    if scene.control_dimensions:
        base = min(1.0, base + 0.05)
    crit = sum(1 for a in scene.assumptions if a.severity == "critical")
    return round(max(0.0, base - 0.08 * crit), 2)
