"""2D geometry helpers for the scene model (millimetres)."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .model import Opening, Point, Room, Scene, SceneObject, Wall


def dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def wall_length(w: Wall) -> float:
    return dist(w.a, w.b)


def unit(a: Point, b: Point) -> Point:
    L = dist(a, b) or 1.0
    return ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


def normal(a: Point, b: Point) -> Point:
    """Left-hand normal (looking a→b) in a Y-down system."""
    ux, uy = unit(a, b)
    return (uy, -ux)


def lerp(a: Point, b: Point, t: float) -> Point:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def along(w: Wall, offset: float) -> Point:
    ux, uy = unit(w.a, w.b)
    return (w.a[0] + ux * offset, w.a[1] + uy * offset)


def wall_outline(w: Wall, start: float = 0.0, end: float | None = None) -> list[Point]:
    """Rectangle of the wall body between two offsets along the centre line."""
    end = wall_length(w) if end is None else end
    nx, ny = normal(w.a, w.b)
    h = w.thickness / 2
    p0, p1 = along(w, start), along(w, end)
    return [
        (p0[0] + nx * h, p0[1] + ny * h),
        (p1[0] + nx * h, p1[1] + ny * h),
        (p1[0] - nx * h, p1[1] - ny * h),
        (p0[0] - nx * h, p0[1] - ny * h),
    ]


def wall_solid_segments(w: Wall, openings: list[Opening]) -> list[tuple[float, float]]:
    """Offsets of the solid parts of a wall once its openings are cut out."""
    L = wall_length(w)
    cuts = sorted((max(0, o.offset), min(L, o.offset + o.width)) for o in openings if o.wall_id == w.id)
    segs, cur = [], 0.0
    for s, e in cuts:
        if s > cur:
            segs.append((cur, s))
        cur = max(cur, e)
    if cur < L:
        segs.append((cur, L))
    return [(s, e) for s, e in segs if e - s > 1]


def polygon_area(poly: list[Point]) -> float:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def polygon_perimeter(poly: list[Point]) -> float:
    return sum(dist(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def centroid(poly: list[Point]) -> Point:
    a = 0.0
    cx = cy = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        f = x1 * y2 - x2 * y1
        a += f
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    if abs(a) < 1e-9:
        xs, ys = zip(*poly)
        return (sum(xs) / len(xs), sum(ys) / len(ys))
    a *= 0.5
    return (cx / (6 * a), cy / (6 * a))


def label_point(poly: list[Point]) -> Point:
    """Centroid if it is inside the polygon, else the centre of the largest inner bbox cell."""
    c = centroid(poly)
    if point_in_polygon(c, poly):
        return c
    x0, y0, x1, y1 = bbox(poly)
    best, best_d = c, -1.0
    for i in range(1, 10):
        for j in range(1, 10):
            p = (x0 + (x1 - x0) * i / 10, y0 + (y1 - y0) * j / 10)
            if point_in_polygon(p, poly):
                d = min(dist_point_segment(p, poly[k], poly[(k + 1) % len(poly)]) for k in range(len(poly)))
                if d > best_d:
                    best, best_d = p, d
    return best


def bbox(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_polygon(p: Point, poly: list[Point]) -> bool:
    x, y = p
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def dist_point_segment(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return dist(p, a)
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L2))
    return dist(p, (ax + t * dx, ay + t * dy))


def scene_bbox(scene: Scene) -> tuple[float, float, float, float]:
    pts: list[Point] = []
    for w in scene.walls:
        pts.extend(wall_outline(w))
    for r in scene.rooms:
        pts.extend(r.polygon)
    if not pts:
        return (0, 0, 1000, 1000)
    return bbox(pts)


# ------------------------------------------------------------------ objects as rectangles
@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    def overlaps(self, o: Rect, tol: float = 1.0) -> bool:
        return self.x0 < o.x1 - tol and o.x0 < self.x1 - tol and self.y0 < o.y1 - tol and o.y0 < self.y1 - tol

    def inflate(self, d: float) -> Rect:
        return Rect(self.x0 - d, self.y0 - d, self.x1 + d, self.y1 + d)

    def corners(self) -> list[Point]:
        return [(self.x0, self.y0), (self.x1, self.y0), (self.x1, self.y1), (self.x0, self.y1)]


def footprint(o: SceneObject) -> Rect:
    rot = int(round(o.rotation)) % 180
    w, d = (o.w, o.d) if rot == 0 else (o.d, o.w)
    return Rect(o.x - w / 2, o.y - d / 2, o.x + w / 2, o.y + d / 2)


def front_vector(o: SceneObject) -> Point:
    """Direction the object's front faces (rotation 0 → +Y)."""
    r = math.radians(o.rotation)
    return (round(-math.sin(r), 6), round(math.cos(r), 6))


def front_zone(o: SceneObject, depth: float) -> Rect:
    fp = footprint(o)
    fx, fy = front_vector(o)
    if fy > 0.5:
        return Rect(fp.x0, fp.y1, fp.x1, fp.y1 + depth)
    if fy < -0.5:
        return Rect(fp.x0, fp.y0 - depth, fp.x1, fp.y0)
    if fx > 0.5:
        return Rect(fp.x1, fp.y0, fp.x1 + depth, fp.y1)
    return Rect(fp.x0 - depth, fp.y0, fp.x0, fp.y1)


def rect_inside_polygon(r: Rect, poly: list[Point], tol: float = 2.0) -> bool:
    shrunk = r.inflate(-tol)
    return all(point_in_polygon(c, poly) for c in shrunk.corners())


# ------------------------------------------------------------------ room edges & free spans
@dataclass
class RoomEdge:
    a: Point
    b: Point
    index: int
    inward: Point  # unit vector pointing into the room
    wall_id: str | None
    blocked: list[tuple[float, float]]  # offsets (from a) blocked by openings / clearances

    @property
    def length(self) -> float:
        return dist(self.a, self.b)

    def free_spans(self, min_len: float = 0) -> list[tuple[float, float]]:
        L = self.length
        cur, spans = 0.0, []
        for s, e in sorted(self.blocked):
            if s > cur:
                spans.append((cur, s))
            cur = max(cur, e)
        if cur < L:
            spans.append((cur, L))
        return [(s, e) for s, e in spans if e - s >= min_len]


def _polygon_is_cw_ydown(poly: list[Point]) -> bool:
    s = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        s += x1 * y2 - x2 * y1
    return s > 0  # positive signed area in a Y-down frame = clockwise on screen


def nearest_wall(scene: Scene, a: Point, b: Point) -> Wall | None:
    mid = lerp(a, b, 0.5)
    best, best_d = None, 1e18
    ex, ey = unit(a, b)
    for w in scene.walls:
        if w.status == "demolish":
            continue
        wx, wy = unit(w.a, w.b)
        if abs(ex * wx + ey * wy) < 0.95:  # not parallel
            continue
        d = dist_point_segment(mid, w.a, w.b)
        if d < best_d and d <= w.thickness / 2 + 80:
            best, best_d = w, d
    return best


def room_edges(scene: Scene, room: Room, door_clearance: float = 150) -> list[RoomEdge]:
    poly = room.polygon
    cw = _polygon_is_cw_ydown(poly)
    edges: list[RoomEdge] = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        nx, ny = normal(a, b)
        inward = (-nx, -ny) if cw else (nx, ny)
        # sanity: verify inward with a probe
        mid = lerp(a, b, 0.5)
        probe = (mid[0] + inward[0] * 50, mid[1] + inward[1] * 50)
        if not point_in_polygon(probe, poly):
            inward = (-inward[0], -inward[1])
        wall = nearest_wall(scene, a, b)
        blocked: list[tuple[float, float]] = []
        if wall:
            ux, uy = unit(a, b)
            for o in scene.openings:
                if o.wall_id != wall.id:
                    continue
                p0, p1 = along(wall, o.offset), along(wall, o.offset + o.width)
                t0 = (p0[0] - a[0]) * ux + (p0[1] - a[1]) * uy
                t1 = (p1[0] - a[0]) * ux + (p1[1] - a[1]) * uy
                lo, hi = min(t0, t1), max(t0, t1)
                # windows block only their own span (radiator/curtain access); doors get extra clearance
                clearance = door_clearance if o.type != "window" else 0
                blocked.append((lo - clearance, hi + clearance))
        edges.append(RoomEdge(a=a, b=b, index=i, inward=inward, wall_id=wall.id if wall else None, blocked=blocked))
    return edges


def opening_world(scene: Scene, o: Opening) -> tuple[Point, Point] | None:
    w = scene.wall(o.wall_id)
    if not w:
        return None
    return along(w, o.offset), along(w, o.offset + o.width)


def door_swing_rect(scene: Scene, o: Opening) -> Rect | None:
    """Axis-aligned bounds of the door leaf sweep (quarter circle radius = width)."""
    if o.type not in ("door", "entrance_door", "balcony_door"):
        return None
    w = scene.wall(o.wall_id)
    if not w:
        return None
    p0, p1 = along(w, o.offset), along(w, o.offset + o.width)
    nx, ny = normal(w.a, w.b)
    side = 1 if o.swing == "left" else -1
    off = w.thickness / 2
    q0 = (p0[0] + nx * off * side, p0[1] + ny * off * side)
    q1 = (p1[0] + nx * off * side, p1[1] + ny * off * side)
    far0 = (q0[0] + nx * o.width * side, q0[1] + ny * o.width * side)
    far1 = (q1[0] + nx * o.width * side, q1[1] + ny * o.width * side)
    xs = [q0[0], q1[0], far0[0], far1[0]]
    ys = [q0[1], q1[1], far0[1], far1[1]]
    return Rect(min(xs), min(ys), max(xs), max(ys))


def scale_scene(scene: Scene, factor: float) -> Scene:
    """Uniformly rescale the geometry (used after a control dimension is entered)."""

    def sp(p: Point) -> Point:
        return (round(p[0] * factor, 1), round(p[1] * factor, 1))

    s = scene.model_copy(deep=True)
    for w in s.walls:
        w.a, w.b = sp(w.a), sp(w.b)
    for o in s.openings:
        o.offset *= factor
        o.width *= factor
    for r in s.rooms:
        r.polygon = [sp(p) for p in r.polygon]
    for f in s.fixtures:
        f.position = sp(f.position)
    for o in s.objects:
        o.x, o.y = sp((o.x, o.y))
    for e in s.electrical:
        e.position = sp(e.position)
    for li in s.lights:
        li.position = sp(li.position)
        if li.end:
            li.end = sp(li.end)
    for c in s.cameras:
        c.position, c.target = sp(c.position), sp(c.target)
    return s


def room_area_m2(room: Room) -> float:
    return round(polygon_area(room.polygon) / 1e6, 2)


def room_wall_area_m2(scene: Scene, room: Room) -> float:
    """Net wall surface for finishing: perimeter × height − openings on the room's walls."""
    gross = polygon_perimeter(room.polygon) * room.ceiling_height
    openings = 0.0
    for e in room_edges(scene, room, door_clearance=0):
        if not e.wall_id:
            continue
        for o in scene.openings:
            if o.wall_id == e.wall_id:
                w = scene.wall(o.wall_id)
                if not w:
                    continue
                p0 = along(w, o.offset + o.width / 2)
                if dist_point_segment(p0, e.a, e.b) <= w.thickness / 2 + 80:
                    openings += o.width * (o.height if o.type != "window" else o.height)
    return round(max(0.0, gross - openings) / 1e6, 2)
