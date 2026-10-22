"""Apple RoomPlan `CapturedRoom` JSON → BuildingGraph scene (P2-6, LiDAR survey import).

RoomPlan (iOS 16+) exports `CapturedRoom` as Codable JSON: `walls`, `doors`, `windows`, `openings`
are surfaces with `dimensions` [w, h, d] (metres), a 4×4 column-major `transform` (y up) and a
`confidence` (high / medium / low); iOS 17 adds `floors` with `polygonCorners`. Plan mapping:
plan X = x, plan Y = z (both in mm). Without a floor polygon the room outline is the convex hull of
the wall ends — flagged as an assumption."""
from __future__ import annotations

import json
import math

from ..scene.model import Assumption, Opening, Room, Scene, Wall

CONF = {"high": 0.95, "medium": 0.8, "low": 0.6}


class RoomPlanError(ValueError):
    pass


def _surface(s: dict) -> tuple[tuple[float, float, float], tuple[float, float], float, float, float]:
    """→ centre (x, y, z) mm, unit direction of the surface's local x in plan, width, height (mm), confidence."""
    t = s.get("transform")
    dims = s.get("dimensions")
    if not (isinstance(t, list) and len(t) == 16 and isinstance(dims, list) and len(dims) >= 2):
        raise RoomPlanError("roomplan.bad_surface")
    cx, cy, cz = t[12] * 1000, t[13] * 1000, t[14] * 1000  # column-major: translation in the last column
    dx, dz = t[0], t[2]
    n = math.hypot(dx, dz) or 1.0
    conf = s.get("confidence")
    conf = CONF.get(next(iter(conf)) if isinstance(conf, dict) else conf, 0.8)
    return (cx, cy, cz), (dx / n, dz / n), dims[0] * 1000, dims[1] * 1000, conf


def parse(data: bytes) -> tuple[Scene, dict]:
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise RoomPlanError("roomplan.not_json") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("walls"), list) or not doc["walls"]:
        raise RoomPlanError("roomplan.no_walls")
    scene = Scene(name="RoomPlan scan")
    floor_y = None
    for i, s in enumerate(doc["walls"], start=1):
        (cx, cy, cz), (ux, uz), w, h, conf = _surface(s)
        a, b = (cx - ux * w / 2, cz - uz * w / 2), (cx + ux * w / 2, cz + uz * w / 2)
        scene.walls.append(Wall(id=f"W{i}", a=(round(a[0], 1), round(a[1], 1)), b=(round(b[0], 1), round(b[1], 1)), thickness=100, height=round(h, 1),
                                source="measured", confidence=conf))
        floor_y = cy - h / 2 if floor_y is None else min(floor_y, cy - h / 2)
    k = 0
    for key, otype in (("doors", "door"), ("windows", "window"), ("openings", "opening")):
        for s in doc.get(key) or []:
            (cx, cy, cz), _, w, h, conf = _surface(s)
            best, best_d, off = None, 1e9, 0.0
            for wall in scene.walls:
                (ax, ay), (bx, by) = wall.a, wall.b
                L = math.hypot(bx - ax, by - ay) or 1
                t = max(0.0, min(1.0, ((cx - ax) * (bx - ax) + (cz - ay) * (by - ay)) / L ** 2))
                d = math.hypot(ax + (bx - ax) * t - cx, ay + (by - ay) * t - cz)
                if d < best_d:
                    best, best_d, off = wall, d, t * L - w / 2
            if best is None or best_d > 300:
                continue
            k += 1
            L = math.hypot(best.b[0] - best.a[0], best.b[1] - best.a[1])
            sill = max(0.0, (cy - h / 2) - (floor_y or 0)) if otype == "window" else 0.0
            scene.openings.append(Opening(id=f"O{k}", wall_id=best.id, type=otype, offset=round(max(0.0, min(off, L - w)), 1), width=round(w, 1), height=round(h, 1),
                                          sill=round(sill, 1), source="measured", confidence=conf))
    floors = doc.get("floors") or []
    if floors and floors[0].get("polygonCorners"):
        f = floors[0]
        t = f.get("transform") or [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        pts = []
        for p in f["polygonCorners"]:  # floor-local (x, y, z) → world via the floor transform
            x, y, z = (p + [0, 0, 0])[:3]
            wx = t[0] * x + t[4] * y + t[8] * z + t[12]
            wz = t[2] * x + t[6] * y + t[10] * z + t[14]
            pts.append((round(wx * 1000, 1), round(wz * 1000, 1)))
        scene.rooms.append(Room(id="R1", number=1, type="living", name="Room", polygon=pts, source="measured", confidence=0.9))
    else:
        from shapely.geometry import MultiPoint

        hull = MultiPoint([p for w in scene.walls for p in (w.a, w.b)]).convex_hull
        if hull.geom_type == "Polygon":
            scene.rooms.append(Room(id="R1", number=1, type="living", name="Room", polygon=[(round(x, 1), round(y, 1)) for x, y in list(hull.exterior.coords)[:-1]],
                                    source="assumed", confidence=0.6))
            scene.assumptions.append(Assumption(key="roomplan_outline", text="Контур помещения построен по стенам (в скане нет пола)", severity="warning"))
    scene.assumptions.append(Assumption(key="roomplan_thickness", text="Толщина стен в RoomPlan не измеряется — принято 100 мм", severity="warning"))
    if scene.walls:
        scene.ceiling_height = round(max(w.height or 0 for w in scene.walls), 1)
    return scene, {"walls": len(scene.walls), "openings": len(scene.openings), "rooms": len(scene.rooms), "objects_ignored": len(doc.get("objects") or [])}
