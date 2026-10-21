"""Deterministic layout engine: places grounded products into rooms using wall spans,
door/window clearances and the rules engine, then derives electrical points,
lighting, finishes and cameras. The LLM never positions objects directly — it may
only change the inputs (program, preferences, chosen products)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..catalog.candidates import Candidate
from .geometry import (
    Rect,
    RoomEdge,
    bbox,
    dist,
    door_swing_rect,
    footprint,
    front_zone,
    label_point,
    lerp,
    point_in_polygon,
    polygon_area,
    rect_inside_polygon,
    room_edges,
    unit,
)
from .model import Camera, Electrical, Light, Room, Scene, SceneObject, SurfaceFinish

# Room programmes: ordered list of (category, qty, required)
PROGRAMS: dict[str, list[tuple[str, int, bool]]] = {
    "bedroom": [("bed", 1, True), ("nightstand", 2, False), ("wardrobe", 1, False), ("dresser", 1, False), ("rug", 1, False)],
    "kids": [("kids_bed", 1, True), ("desk", 1, False), ("desk_chair", 1, False), ("wardrobe", 1, False), ("rug", 1, False)],
    "kitchen_living": [("kitchen_run", 1, True), ("fridge", 1, True), ("dining_table", 1, True), ("dining_chair", 4, False),
                       ("sofa", 1, True), ("tv_unit", 1, False), ("coffee_table", 1, False), ("rug", 1, False), ("armchair", 1, False), ("floor_lamp", 1, False)],
    "living": [("sofa", 1, True), ("tv_unit", 1, False), ("coffee_table", 1, False), ("rug", 1, False), ("armchair", 1, False), ("floor_lamp", 1, False)],
    "kitchen": [("kitchen_run", 1, True), ("fridge", 1, True), ("dining_table", 1, False), ("dining_chair", 4, False)],
    "bathroom": [("bathtub", 1, False), ("toilet", 1, True), ("vanity", 1, True), ("washer", 1, False), ("towel_dryer", 1, False)],
    "wc": [("toilet", 1, True), ("vanity", 1, False)],
    "hallway": [("hallway_wardrobe", 1, False), ("shoe_cabinet", 1, False), ("bench", 1, False), ("mirror", 1, False)],
    "wardrobe": [("storage_system", 3, False)],
    "office": [("desk", 1, True), ("desk_chair", 1, True), ("wardrobe", 1, False)],
    "balcony": [("plant", 1, False)],
}

# Additional per-room needs that are not floor objects (lighting, decor, finishing)
WALL_HUNG = {"mirror", "towel_dryer", "artwork"}
OBSTACLE_FIXTURES = {"riser_water", "riser_sewer", "electrical_panel", "ventilation", "boiler"}

CODE_PREFIX = "К"
from .rules import FRONT_CLEARANCE, ZONE_FRIENDS  # noqa: E402  # drawing tag prefix (Կ in HY album, K in EN)


@dataclass
class PlacementResult:
    scene: Scene
    unplaced: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _rot_for_inward(inward: tuple[float, float]) -> float:
    ix, iy = inward
    if abs(iy) >= abs(ix):
        return 0.0 if iy > 0 else 180.0
    return 270.0 if ix > 0 else 90.0


class Placer:
    def __init__(self, scene: Scene):
        self.scene = scene
        self.obstacles: list[Rect] = []
        for f in scene.fixtures:
            if f.type in OBSTACLE_FIXTURES:
                w, d = f.size or (200, 200)
                self.obstacles.append(Rect(f.position[0] - w / 2, f.position[1] - d / 2, f.position[0] + w / 2, f.position[1] + d / 2))
        self.swings = [r for r in (door_swing_rect(scene, o) for o in scene.openings) if r]
        # zones that tall furniture must not cover: windows (+450 mm for access/curtains) and radiators
        from .geometry import opening_world

        self.window_zones: list[Rect] = []
        for o in scene.openings:
            if o.type in ("window", "balcony_door"):
                seg = opening_world(scene, o)
                if seg:
                    (ax, ay), (bx, by) = seg
                    self.window_zones.append(Rect(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)).inflate(450))
        self.radiators = []
        for f in scene.fixtures:
            if f.type == "radiator" and f.size:
                w, d = f.size
                self.radiators.append(Rect(f.position[0] - w / 2, f.position[1] - d / 2, f.position[0] + w / 2, f.position[1] + d / 2).inflate(150))
        self.counter = 0

    def _fits(self, o: SceneObject, room: Room, ignore_ids: set[str] = frozenset()) -> bool:
        fp = footprint(o)
        if not rect_inside_polygon(fp, room.polygon, tol=5):
            return False
        if o.category in ("rug",):
            return True
        for r in self.obstacles:
            if fp.overlaps(r):
                return False
        for s in self.swings:
            if s.inflate(-20).overlaps(fp):
                return False
        if o.h > 900 and o.elevation < 1200:
            if any(z.overlaps(fp, tol=50) for z in self.window_zones):
                return False
        if o.h > 600 and o.category not in ("dining_chair", "desk_chair"):
            if any(z.overlaps(fp, tol=20) for z in self.radiators):
                return False
        for other in self.scene.objects:
            if other.id in ignore_ids or other.room_id != room.id or other.category in ("rug",):
                continue
            if {o.category, other.category} in ({"dining_chair", "dining_table"}, {"desk_chair", "desk"}):
                continue
            if fp.overlaps(footprint(other), tol=2):
                return False
        return True

    def _front_ok(self, o: SceneObject, room: Room, need: float) -> bool:
        fp = footprint(o)
        if o.category == "rug":
            return True
        # the new item must not stand in the service zone of items already placed
        for other in self.scene.objects:
            if other.room_id != room.id or other.id == o.id or other.category in ("rug",):
                continue
            if {o.category, other.category} in ZONE_FRIENDS:
                continue
            oz = FRONT_CLEARANCE.get(other.category, 0)
            if oz and front_zone(other, oz).overlaps(fp, tol=30):
                return False
        if need <= 0:
            return True
        z = front_zone(o, need)
        if not rect_inside_polygon(z, room.polygon, tol=20):
            return False
        for other in self.scene.objects:
            if other.room_id == room.id and other.id != o.id and other.category not in ("rug", "dining_chair", "desk_chair"):
                if z.overlaps(footprint(other), tol=30):
                    return False
        return True

    def new_obj(self, room: Room, cand: Candidate | None, category: str, w: float, d: float, h: float, **kw) -> SceneObject:
        self.counter += 1
        return SceneObject(
            id=f"O{self.counter:03d}", code=f"{CODE_PREFIX}-{self.counter:02d}", room_id=room.id, category=category,
            name=cand.name if cand else category, product_variant_id=cand.ref if cand else None, x=0, y=0, w=w, d=d, h=h,
            color_hex=cand.color_hex if cand else "#bbbbbb", source="ai", confidence=(cand.confidence if cand else 0.5) * (1 if (cand and cand.dims_known) else 0.7),
            mode="real" if cand and cand.price_status != "concept" else "concept", **kw,
        )

    def against_wall(self, room: Room, o: SceneObject, edges: list[RoomEdge], align: str = "center", gap: float = 10,
                     front_need: float = 600, prefer: list[int] | None = None, offset_t: float | None = None, allow_relaxed: bool = True) -> bool:
        order = list(edges)
        if prefer is not None:
            order.sort(key=lambda e: prefer.index(e.index) if e.index in prefer else 999)
        for strict in ((True, False) if allow_relaxed else (True,)):
            for e in order:
                for s, t in e.free_spans(min_len=o.w + 20):
                    ux, uy = unit(e.a, e.b)
                    if offset_t is not None and s <= offset_t <= t - o.w:
                        positions = [offset_t + o.w / 2]
                    elif align == "start":
                        positions = [s + o.w / 2 + 10 + k * 100 for k in range(int((t - s - o.w) // 100) + 1)]
                    elif align == "end":
                        positions = [t - o.w / 2 - 10 - k * 100 for k in range(int((t - s - o.w) // 100) + 1)]
                    else:
                        mid = (s + t) / 2
                        positions = [mid] + [mid + k * 150 * sgn for k in range(1, 12) for sgn in (1, -1)]
                    for tc in positions:
                        if tc - o.w / 2 < s - 1 or tc + o.w / 2 > t + 1:
                            continue
                        px = e.a[0] + ux * tc + e.inward[0] * (o.d / 2 + gap)
                        py = e.a[1] + uy * tc + e.inward[1] * (o.d / 2 + gap)
                        o.x, o.y = round(px), round(py)
                        o.rotation = _rot_for_inward(e.inward)
                        o.against_wall_id = e.wall_id
                        if self._fits(o, room) and (not strict or self._front_ok(o, room, front_need)):
                            return True
        return False

    def at_point(self, room: Room, o: SceneObject, x: float, y: float, rotation: float = 0, respect_zones: bool = True) -> bool:
        o.x, o.y, o.rotation = round(x), round(y), rotation
        return self._fits(o, room) and (not respect_zones or self._front_ok(o, room, 0))


def _pick(cands: dict[str, list[Candidate]], category: str, n: int = 0) -> Candidate | None:
    lst = cands.get(category) or []
    return lst[min(n, len(lst) - 1)] if lst else None


def furnish(scene: Scene, chosen: dict[str, dict[str, list[Candidate]]], tier: str = "comfort",
            extras: dict[str, list[str]] | None = None, locked: list[SceneObject] | None = None) -> PlacementResult:
    """chosen[room_id][category] -> ranked candidates (first = primary choice).
    extras: additional categories per room requested by the user (AI change commands).
    locked: objects the user locked — kept exactly where they are."""
    sc = scene.model_copy(deep=True)
    sc.objects = []
    placer = Placer(sc)
    res = PlacementResult(scene=sc)
    locked = locked or []
    locked_keys = {(o.room_id, o.category) for o in locked}
    sc.objects.extend(o.model_copy() for o in locked)
    placer.counter = max([int(o.id[1:]) for o in locked if o.id[1:].isdigit()] + [0])
    for room in sc.rooms:
        prog = [p for p in PROGRAMS.get(room.type, []) if (room.id, p[0]) not in locked_keys]
        cands = {k: v for k, v in chosen.get(room.id, {}).items() if (room.id, k) not in locked_keys}
        edges = room_edges(sc, room)
        handler = ROOM_HANDLERS.get(room.type, _generic_room)
        handler(placer, room, edges, prog, cands, res, tier)
        for cat in (extras or {}).get(room.id, []):
            if any(o.room_id == room.id and o.category == cat for o in sc.objects):
                continue
            _place_simple(placer, room, room_edges(sc, room), cat, _pick(cands, cat), res, required=True)
    _electrical(sc)
    _lighting(sc)
    _cameras(sc)
    return res


# ---------------------------------------------------------------- room handlers
def _place_simple(placer: Placer, room: Room, edges, cat: str, cand: Candidate | None, res: PlacementResult, *, align="center", front=None, prefer=None, required=False) -> SceneObject | None:
    front = FRONT_CLEARANCE.get(cat, 600) if front is None else front
    if cand is None:
        if required:
            res.unplaced.append({"room_id": room.id, "category": cat, "reason": "Нет подходящего товара в каталоге"})
        return None
    w, d, h = cand.w or 600, cand.d or 600, cand.h or 800
    o = placer.new_obj(room, cand, cat, w, d, h)
    # optional items are only placed where every clearance is respected
    if placer.against_wall(room, o, edges, align=align, front_need=front, prefer=prefer, allow_relaxed=required):
        placer.scene.objects.append(o)
        return o
    res.unplaced.append({"room_id": room.id, "category": cat, "reason": f"Не помещается ({int(w)}×{int(d)} мм) с соблюдением проходов"})
    return None


def _generic_room(placer, room, edges, prog, cands, res, tier):
    for cat, qty, req in prog:
        for i in range(qty):
            _place_simple(placer, room, edges, cat, _pick(cands, cat, i), res, required=req)


def _longest_edges(edges: list[RoomEdge]) -> list[int]:
    return [e.index for e in sorted(edges, key=lambda e: -max((t - s for s, t in e.free_spans()), default=0))]


def _bedroom(placer: Placer, room, edges, prog, cands, res, tier):
    bed_cat = "kids_bed" if room.type == "kids" else "bed"
    bed_c = _pick(cands, bed_cat)
    # headboard against the longest solid wall that is not the window wall
    window_edges = {e.index for e in edges if e.blocked and any(o.type == "window" for o in placer.scene.openings if o.wall_id == e.wall_id)}
    prefer = [i for i in _longest_edges(edges) if i not in window_edges] + list(window_edges)
    bed = None
    if bed_c:
        bed = placer.new_obj(room, bed_c, bed_cat, bed_c.w, bed_c.d, bed_c.h)
        align = "start" if room.type == "kids" else "center"
        if placer.against_wall(room, bed, edges, align=align, front_need=600, prefer=prefer):
            placer.scene.objects.append(bed)
        else:
            res.unplaced.append({"room_id": room.id, "category": bed_cat, "reason": "Кровать не помещается"})
            bed = None
    if bed and room.type == "bedroom":
        ns = _pick(cands, "nightstand")
        if ns:
            fp = footprint(bed)
            fx, fy = (math.isclose(abs(math.sin(math.radians(bed.rotation))), 1, abs_tol=1e-3), None)
            for side in (-1, 1):
                o = placer.new_obj(room, ns, "nightstand", ns.w, ns.d, ns.h)
                if fx:  # bed runs along X (rotated 90/270) → nightstands above/below
                    y = (fp.y0 - ns.w / 2 - 20) if side < 0 else (fp.y1 + ns.w / 2 + 20)
                    back_x = fp.x0 if bed.rotation == 270 else fp.x1
                    x = back_x + (ns.d / 2) * (1 if bed.rotation == 270 else -1)
                else:
                    x = (fp.x0 - ns.w / 2 - 20) if side < 0 else (fp.x1 + ns.w / 2 + 20)
                    back_y = fp.y0 if bed.rotation == 0 else fp.y1
                    y = back_y + (ns.d / 2) * (1 if bed.rotation == 0 else -1)
                if placer.at_point(room, o, x, y, bed.rotation):
                    placer.scene.objects.append(o)
    rest = [(c, q, r) for c, q, r in prog if c not in (bed_cat, "nightstand", "rug")]
    for cat, _qty, req in rest:
        cand = _pick(cands, cat)
        if cat == "desk_chair":
            desk = next((o for o in placer.scene.objects if o.room_id == room.id and o.category == "desk"), None)
            if desk and cand:
                fx, fy = (-math.sin(math.radians(desk.rotation)), math.cos(math.radians(desk.rotation)))
                o = placer.new_obj(room, cand, cat, cand.w, cand.d, cand.h)
                if placer.at_point(room, o, desk.x + fx * (desk.d / 2 + 50), desk.y + fy * (desk.d / 2 + 50), (desk.rotation + 180) % 360):
                    placer.scene.objects.append(o)
            continue
        if cat == "desk":
            # desks prefer the window wall (daylight)
            _place_simple(placer, room, edges, cat, cand, res, prefer=list(window_edges) + _longest_edges(edges), front=700)
            continue
        _place_simple(placer, room, edges, cat, cand, res, align="end" if cat == "wardrobe" else "center", required=req)
    _rug(placer, room, _pick(cands, "rug"), anchor=bed, res=res)


def _rug(placer: Placer, room, cand, anchor: SceneObject | None, res, scale: float = 1.0):
    if not cand:
        return
    x0, y0, x1, y1 = bbox(room.polygon)
    w, d = min(cand.w, (x1 - x0) - 600), min(cand.d, (y1 - y0) - 600)
    if w < 800 or d < 800:
        return
    o = placer.new_obj(room, cand, "rug", w, d, 10)
    cx, cy = (anchor.x, anchor.y) if anchor else label_point(room.polygon)
    if anchor:
        fx, fy = (-math.sin(math.radians(anchor.rotation)), math.cos(math.radians(anchor.rotation)))
        cx, cy = anchor.x + fx * anchor.d * 0.35, anchor.y + fy * anchor.d * 0.35
        if int(anchor.rotation) % 180 == 90:
            o.w, o.d = d, w
    if placer.at_point(room, o, cx, cy, 0):
        placer.scene.objects.append(o)


def _kitchen_living(placer: Placer, room, edges, prog, cands, res, tier):
    sc = placer.scene
    water = next((f for f in sc.fixtures if f.room_id == room.id and f.type in ("water_cold", "drain")), None)
    run_c = _pick(cands, "kitchen_run")
    fridge_c = _pick(cands, "fridge")
    run = fridge = None
    # 1) kitchen run on the edge nearest to the water point
    if run_c:
        def edge_dist(e: RoomEdge) -> float:
            if not water:
                return 0
            from .geometry import dist_point_segment
            return dist_point_segment(water.position, e.a, e.b)
        order = sorted(edges, key=edge_dist)
        target_len = {"economy": 2800, "comfort": 3400, "business": 3800, "premium": 4200}.get(tier, 3400)
        for e in order:
            spans = e.free_spans(min_len=2000)
            if not spans:
                continue
            s, t = max(spans, key=lambda st: st[1] - st[0])
            fridge_w = (fridge_c.w + 20) if fridge_c else 0
            L = min(target_len, (t - s) - fridge_w - 40)
            if L < 1800:
                continue
            run = placer.new_obj(room, run_c, "kitchen_run", L, 600, 2400)
            run.name = f"{run_c.name} · L={int(L)}"  # drawing units are mm; no language-specific unit in product data
            run.custom_product = {"made_to_measure": True, "length_mm": int(L), "modules": max(3, int(L // 600)), "base_height": 900,
                                  "upper_height": 720, "price_per_m": (run_c.parametric or {}).get("price_per_m")}
            ok = placer.against_wall(room, run, [e], align="end", front_need=1000) or placer.against_wall(room, run, [e], align="start", front_need=900)
            if ok:
                sc.objects.append(run)
                ux, uy = unit(e.a, e.b)
                fx, fy = e.inward
                sink_t = None
                if water:
                    sink_t = (water.position[0] - e.a[0]) * ux + (water.position[1] - e.a[1]) * uy
                center_t = (run.x - e.a[0]) * ux + (run.y - e.a[1]) * uy
                lo, hi = center_t - L / 2 + 400, center_t + L / 2 - 400
                st = min(max(sink_t if sink_t is not None else lo, lo), hi)
                ht = hi if abs(st - hi) > abs(st - lo) else lo
                if abs(ht - st) < 900:
                    ht = st + 1200 if st + 1200 <= hi else st - 1200
                back = lambda tt, e=e, ux=ux, uy=uy, fx=fx, fy=fy: (e.a[0] + ux * tt + fx * 300, e.a[1] + uy * tt + fy * 300)  # noqa: E731
                run.custom_product["sink_xy"] = [round(v) for v in back(st)]
                run.custom_product["hob_xy"] = [round(v) for v in back(ht)]
                # fridge at the far end from the hob
                if fridge_c:
                    fridge = placer.new_obj(room, fridge_c, "fridge", fridge_c.w, fridge_c.d, fridge_c.h)
                    for end_t in (center_t - L / 2 - fridge_c.w / 2 - 20, center_t + L / 2 + fridge_c.w / 2 + 20):
                        px = e.a[0] + ux * end_t + fx * (fridge_c.d / 2 + 10)
                        py = e.a[1] + uy * end_t + fy * (fridge_c.d / 2 + 10)
                        if placer.at_point(room, fridge, px, py, run.rotation):
                            sc.objects.append(fridge)
                            break
                    else:
                        res.unplaced.append({"room_id": room.id, "category": "fridge", "reason": "Нет места рядом с гарнитуром"})
                        fridge = None
                break
            placer.counter -= 1
            run = None
        if not run:
            res.unplaced.append({"room_id": room.id, "category": "kitchen_run", "reason": "Нет свободной стены ≥ 1.8 м"})
    # 2) dining table in front of the run
    table_c = _pick(cands, "dining_table")
    table = None
    if table_c:
        table = placer.new_obj(room, table_c, "dining_table", table_c.w, table_c.d, table_c.h)
        placed = False
        if run:
            fx, fy = (-math.sin(math.radians(run.rotation)), math.cos(math.radians(run.rotation)))
            for dist_front in (1100 + table_c.d / 2 + 600, 1000 + table_c.d / 2 + 550, 1500 + table_c.d / 2 + 600):
                for shift in (0, 400, -400, 800, -800, 1200, -1200):
                    px = run.x + fx * (300 + dist_front) + (fy * shift)
                    py = run.y + fy * (300 + dist_front) + (-fx * shift)
                    if placer.at_point(room, table, px, py, run.rotation):
                        placed = True
                        break
                if placed:
                    break
        if placed:
            sc.objects.append(table)
        elif placer.against_wall(room, table, edges, front_need=0):
            # fallback: table against a wall (chairs on the three free sides)
            sc.objects.append(table)
        else:
            res.unplaced.append({"room_id": room.id, "category": "dining_table", "reason": "Нет места для обеденной зоны"})
            table = None
    chair_c = _pick(cands, "dining_chair")
    if table and chair_c:
        tp = footprint(table)
        long_x = tp.w >= tp.h
        n_side = 2 if (tp.w if long_x else tp.h) >= 1400 else 1
        spots = []
        for k in range(n_side):
            t = (k + 0.5) / n_side
            if long_x:
                xx = tp.x0 + tp.w * t
                spots += [(xx, tp.y0 - chair_c.d / 2 + 150, 180), (xx, tp.y1 + chair_c.d / 2 - 150, 0)]
            else:
                yy = tp.y0 + tp.h * t
                spots += [(tp.x0 - chair_c.d / 2 + 150, yy, 90), (tp.x1 + chair_c.d / 2 - 150, yy, 270)]
        for x, y, r in spots:
            o = placer.new_obj(room, chair_c, "dining_chair", chair_c.w, chair_c.d, chair_c.h)
            if placer.at_point(room, o, x, y, (r + 180) % 360):
                sc.objects.append(o)
    # 3) living zone: sofa on the edge farthest from the kitchen run
    _living_zone(placer, room, edges, cands, res, avoid=run)


def _living_zone(placer: Placer, room, edges, cands, res, avoid: SceneObject | None = None):
    sc = placer.scene
    sofa_c = _pick(cands, "sofa")
    sofa = None
    if sofa_c:
        ref = (avoid.x, avoid.y) if avoid else label_point(room.polygon)
        order = sorted(edges, key=lambda e: -dist(lerp(e.a, e.b, 0.5), ref)) if avoid else sorted(edges, key=lambda e: -e.length)
        sofa = placer.new_obj(room, sofa_c, "sofa", sofa_c.w, sofa_c.d, sofa_c.h)
        if not placer.against_wall(room, sofa, order, front_need=1400, prefer=[e.index for e in order]):
            if not placer.against_wall(room, sofa, order, front_need=600, prefer=[e.index for e in order]):
                res.unplaced.append({"room_id": room.id, "category": "sofa", "reason": "Диван не помещается"})
                sofa = None
        if sofa:
            sc.objects.append(sofa)
    if sofa:
        fx, fy = (-math.sin(math.radians(sofa.rotation)), math.cos(math.radians(sofa.rotation)))
        ct = _pick(cands, "coffee_table")
        if ct:
            o = placer.new_obj(room, ct, "coffee_table", ct.w, ct.d, ct.h)
            ux, uy = fy, -fx  # along the sofa
            done = False
            for gap in (420, 380, 340):
                for shift in (0, 250, -250, 500, -500):
                    cx = sofa.x + fx * (sofa.d / 2 + gap + ct.d / 2) + ux * shift
                    cy = sofa.y + fy * (sofa.d / 2 + gap + ct.d / 2) + uy * shift
                    if placer.at_point(room, o, cx, cy, sofa.rotation):
                        sc.objects.append(o)
                        done = True
                        break
                if done:
                    break
        tv = _pick(cands, "tv_unit")
        if tv:
            # opposite edge whose inward is antiparallel to the sofa front
            opp = [e for e in edges if e.inward[0] * fx + e.inward[1] * fy < -0.9]
            if opp:
                o = placer.new_obj(room, tv, "tv_unit", tv.w, tv.d, tv.h)
                e = min(opp, key=lambda e: abs(((sofa.x - e.a[0]) * unit(e.a, e.b)[0] + (sofa.y - e.a[1]) * unit(e.a, e.b)[1])))
                ux, uy = unit(e.a, e.b)
                t = (sofa.x - e.a[0]) * ux + (sofa.y - e.a[1]) * uy
                if placer.against_wall(room, o, [e], offset_t=t - tv.w / 2, front_need=0) or placer.against_wall(room, o, [e], front_need=0):
                    sc.objects.append(o)
        arm = _pick(cands, "armchair")
        if arm:
            o = placer.new_obj(room, arm, "armchair", arm.w, arm.d, arm.h)
            sp = footprint(sofa)
            side_pts = [(sp.x1 + arm.w / 2 + 250, sofa.y + fy * 500), (sp.x0 - arm.w / 2 - 250, sofa.y + fy * 500)] if abs(fy) > 0.5 else \
                       [(sofa.x + fx * 500, sp.y1 + arm.w / 2 + 250), (sofa.x + fx * 500, sp.y0 - arm.w / 2 - 250)]
            for x, y in side_pts:
                if placer.at_point(room, o, x, y, sofa.rotation):
                    sc.objects.append(o)
                    break
        fl = _pick(cands, "floor_lamp")
        if fl:
            o = placer.new_obj(room, fl, "floor_lamp", fl.w, fl.d, fl.h)
            sp = footprint(sofa)
            for x, y in ((sp.x0 - fl.w / 2 - 50, sp.y0 + fl.d / 2 + 30), (sp.x1 + fl.w / 2 + 50, sp.y0 + fl.d / 2 + 30),
                         (sp.x0 + fl.w / 2 + 30, sp.y0 - fl.d / 2 - 50), (sp.x0 + fl.w / 2 + 30, sp.y1 + fl.d / 2 + 50)):
                if placer.at_point(room, o, x, y, 0):
                    sc.objects.append(o)
                    break
    _rug(placer, room, _pick(cands, "rug"), anchor=sofa, res=res)


def _living(placer, room, edges, prog, cands, res, tier):
    _living_zone(placer, room, edges, cands, res)


def _bathroom(placer: Placer, room, edges, prog, cands, res, tier):
    sc = placer.scene
    riser = next((f for f in sc.fixtures if f.room_id == room.id and f.type.startswith("riser")), None)
    from .geometry import dist_point_segment

    by_riser = sorted(edges, key=lambda e: dist_point_segment(riser.position, e.a, e.b) if riser else 0)
    x0, y0, x1, y1 = bbox(room.polygon)
    short = min(x1 - x0, y1 - y0)
    tub_c = _pick(cands, "bathtub")
    shower_c = _pick(cands, "shower")
    if tub_c and short >= tub_c.w + 20:
        short_edges = sorted(edges, key=lambda e: abs(e.length - short))[:2]
        far = sorted(short_edges, key=lambda e: -(dist_point_segment(riser.position, e.a, e.b) if riser else 0))
        o = _place_simple(placer, room, far + edges, "bathtub", tub_c, res, align="start", front=700)
        if not o and shower_c:
            _place_simple(placer, room, edges, "shower", shower_c, res, align="start", front=700)
    elif shower_c:
        _place_simple(placer, room, edges, "shower", shower_c, res, align="start", front=700)
    _place_simple(placer, room, by_riser, "toilet", _pick(cands, "toilet"), res, align="start", front=600, prefer=[e.index for e in by_riser], required=True)
    _place_simple(placer, room, by_riser, "vanity", _pick(cands, "vanity"), res, front=700, prefer=[e.index for e in by_riser], required=True)
    _place_simple(placer, room, edges, "washer", _pick(cands, "washer"), res, align="end", front=700)


def _hallway(placer: Placer, room, edges, prog, cands, res, tier):
    sc = placer.scene
    entry = next((o for o in sc.openings if o.type == "entrance_door"), None)
    from .geometry import dist_point_segment, opening_world

    pref = edges
    if entry:
        p0, p1 = opening_world(sc, entry)
        mid = lerp(p0, p1, 0.5)
        pref = sorted(edges, key=lambda e: dist_point_segment(mid, e.a, e.b))
    wardrobe_c = _pick(cands, "hallway_wardrobe")
    if wardrobe_c:
        # hallways are narrow: try the full module, then a shallower 450 mm version
        for depth in (wardrobe_c.d, 450, 400):
            o = placer.new_obj(room, wardrobe_c, "hallway_wardrobe", wardrobe_c.w, depth, wardrobe_c.h)
            o.custom_product = {"made_to_measure": True, "depth_mm": depth}
            if placer.against_wall(room, o, pref[1:] + pref[:1], front_need=800, prefer=[e.index for e in pref[1:]]):
                sc.objects.append(o)
                break
            placer.counter -= 1
    for cat in ("shoe_cabinet", "bench"):
        _place_simple(placer, room, pref, cat, _pick(cands, cat), res, front=700)
    m_c = _pick(cands, "mirror")
    if m_c:
        o = placer.new_obj(room, m_c, "mirror", m_c.w, 40, m_c.h, elevation=300)
        if placer.against_wall(room, o, pref, front_need=0):
            sc.objects.append(o)


def _wardrobe_room(placer: Placer, room, edges, prog, cands, res, tier):
    c = _pick(cands, "storage_system")
    if not c:
        return
    for e in sorted(edges, key=lambda e: -e.length):
        spans = e.free_spans(min_len=600)
        for s, t in spans:
            L = min(t - s - 20, 2400)
            if L < 600:
                continue
            o = placer.new_obj(room, c, "storage_system", L, 450, 2400)
            o.custom_product = {"made_to_measure": True, "length_mm": int(L)}
            if placer.against_wall(room, o, [e], front_need=600):
                placer.scene.objects.append(o)
            else:
                placer.counter -= 1


ROOM_HANDLERS = {
    "bedroom": _bedroom, "kids": _bedroom, "kitchen_living": _kitchen_living, "living": _living, "kitchen": _kitchen_living,
    "bathroom": _bathroom, "wc": _bathroom, "hallway": _hallway, "wardrobe": _wardrobe_room, "office": _bedroom,
}


# ---------------------------------------------------------------- engineering derivation
def _wall_point_behind(o: SceneObject, along: float = 0.0) -> tuple[float, float]:
    fp = footprint(o)
    fx, fy = (-math.sin(math.radians(o.rotation)), math.cos(math.radians(o.rotation)))
    if abs(fy) > 0.5:
        y = fp.y0 + 40 if fy > 0 else fp.y1 - 40
        return (o.x + along, y)
    x = fp.x0 + 40 if fx > 0 else fp.x1 - 40
    return (x, o.y + along)


def _door_switch_point(sc: Scene, room: Room) -> tuple[float, float] | None:
    from .geometry import along as wall_along

    for op in sc.openings:
        if op.type not in ("door", "opening", "sliding_door", "entrance_door"):
            continue
        w = sc.wall(op.wall_id)
        if not w:
            continue
        for t in (op.offset - 150, op.offset + op.width + 150):
            p = wall_along(w, t)
            nx, ny = (unit(w.a, w.b)[1], -unit(w.a, w.b)[0])
            for side in (1, -1):
                q = (p[0] + nx * (w.thickness / 2 + 30) * side, p[1] + ny * (w.thickness / 2 + 30) * side)
                if point_in_polygon(q, room.polygon):
                    # latch side: away from hinge
                    return q
    return None


# System-generated socket notes: stored as a stable key + Russian text (documents translate by key).
ELEC_NOTES = {
    "at_entry": "У входа",
    "by_bed": "У кровати",
    "pass_switch": "Проходной выключатель",
    "workplace": "Рабочее место",
    "lan": "LAN",
    "tv_zone": "ТВ-зона",
    "tv_wall": "ТВ на стене",
    "by_sofa": "У дивана",
    "above_counter": "Над столешницей",
    "cooktop_line": "Варочная панель 7 кВт, кабель 3×6",
    "oven": "Духовой шкаф",
    "dishwasher": "ПММ",
    "hood": "Вытяжка",
    "fridge": "Холодильник",
    "under_table": "Под столом — уточнить",
    "washer_ip44": "Влагозащищённая IP44, УЗО",
    "hairdryer": "Фен/бритва IP44",
    "vacuum": "Пылесос",
    "shoe_dryer": "Сушилка для обуви",
    "cleaning": "Уборка",
}


def _electrical(sc: Scene) -> None:
    pts: list[Electrical] = []
    n = 0

    def add(t, p, h, room, note_key="", group=""):
        nonlocal n
        n += 1
        pts.append(Electrical(id=f"E{n:02d}", code=f"E-{n:02d}", type=t, position=(round(p[0]), round(p[1])), height=h, room_id=room.id,
                              note=ELEC_NOTES.get(note_key, ""), note_key=note_key, group=group, source="ai", confidence=0.9))

    for room in sc.rooms:
        if room.type == "balcony":
            continue
        objs = [o for o in sc.objects if o.room_id == room.id]
        sw = _door_switch_point(sc, room)
        if sw:
            add("switch_double" if room.type in ("kitchen_living", "living", "bedroom") else "switch", sw, 900, room, "at_entry")
        for o in objs:
            if o.category in ("bed",):
                add("socket_double", _wall_point_behind(o, -o.w / 2 - 250), 600, room, "by_bed")
                add("socket_double", _wall_point_behind(o, o.w / 2 + 250), 600, room, "by_bed")
                add("switch_pass", _wall_point_behind(o, -o.w / 2 - 250), 900, room, "pass_switch")
            elif o.category == "kids_bed":
                add("socket_double", _wall_point_behind(o, o.w / 2 - 200), 600, room)
            elif o.category == "desk":
                add("socket_triple", _wall_point_behind(o), 900, room, "workplace")
                add("data", _wall_point_behind(o, 200), 900, room, "lan")
            elif o.category == "tv_unit":
                add("socket_triple", _wall_point_behind(o, -200), 300, room, "tv_zone")
                add("tv", _wall_point_behind(o, 100), 1100, room, "tv_wall")
                add("data", _wall_point_behind(o, 250), 300, room, "lan")
            elif o.category == "sofa":
                add("socket_double", _wall_point_behind(o, -o.w / 2 - 150), 300, room, "by_sofa")
                add("socket", _wall_point_behind(o, o.w / 2 + 150), 300, room)
            elif o.category == "kitchen_run":
                L = o.w
                for k in (-0.35, 0.0, 0.35):
                    add("socket_double", _wall_point_behind(o, L * k), 1100, room, "above_counter")
                add("cooktop", _wall_point_behind(o, 0.2 * L), 150, room, "cooktop_line")
                add("oven", _wall_point_behind(o, 0.2 * L + 300), 150, room, "oven")
                add("dishwasher", _wall_point_behind(o, -0.3 * L), 150, room, "dishwasher")
                add("hood", _wall_point_behind(o, 0.2 * L), 2200, room, "hood")
            elif o.category == "fridge":
                add("fridge", _wall_point_behind(o), 300, room, "fridge")
            elif o.category == "dining_table":
                add("socket", (o.x, o.y), 300, room, "under_table", group="floor")
            elif o.category == "washer":
                add("washer", _wall_point_behind(o), 1000, room, "washer_ip44")
            elif o.category == "vanity":
                add("socket_waterproof", _wall_point_behind(o, o.w / 2 + 100), 1100, room, "hairdryer")
            elif o.category == "hallway_wardrobe":
                add("socket", _wall_point_behind(o, o.w / 2 + 150), 300, room, "vacuum")
            elif o.category == "shoe_cabinet":
                add("socket", _wall_point_behind(o), 900, room, "shoe_dryer")
            elif o.category == "storage_system":
                pass
        if room.type in ("bedroom", "kids", "living", "kitchen_living", "office"):
            # extra cleaning socket near the door
            if sw:
                add("socket", (sw[0], sw[1]), 300, room, "cleaning")
    sc.electrical = pts


def _grid(room: Room, spacing: float, margin: float) -> list[tuple[float, float]]:
    x0, y0, x1, y1 = bbox(room.polygon)
    nx = max(1, int((x1 - x0 - 2 * margin) // spacing) + 1)
    ny = max(1, int((y1 - y0 - 2 * margin) // spacing) + 1)
    pts = []
    for i in range(nx):
        for j in range(ny):
            x = x0 + margin + (x1 - x0 - 2 * margin) * (i / (nx - 1) if nx > 1 else 0.5)
            y = y0 + margin + (y1 - y0 - 2 * margin) * (j / (ny - 1) if ny > 1 else 0.5)
            if point_in_polygon((x, y), room.polygon):
                pts.append((round(x), round(y)))
    return pts


def _lighting(sc: Scene) -> None:
    lights: list[Light] = []
    n = 0

    def add(t, p, room, scen, grp, w=8.0, end=None):
        nonlocal n
        n += 1
        lights.append(Light(id=f"L{n:02d}", code=f"L-{n:02d}", type=t, position=(round(p[0]), round(p[1])), end=end, room_id=room.id, scenario=scen, switch_group=grp, power_w=w, source="ai", confidence=0.9))

    for room in sc.rooms:
        objs = {o.category: o for o in sc.objects if o.room_id == room.id}
        area = polygon_area(room.polygon) / 1e6
        if room.type in ("hallway", "bathroom", "wc", "wardrobe"):
            for p in _grid(room, 1100, 450):
                add("spot", p, room, "general", "a", 7)
        elif room.type == "balcony":
            add("wall", label_point(room.polygon), room, "general", "a", 10)
        elif room.type in ("kitchen_living", "kitchen", "living"):
            run = objs.get("kitchen_run")
            table = objs.get("dining_table")
            sofa = objs.get("sofa")
            if run:
                L = run.w
                fx, fy = (-math.sin(math.radians(run.rotation)), math.cos(math.radians(run.rotation)))
                bx, by = run.x - fx * 150, run.y - fy * 150
                ux, uy = (fy, -fx)
                add("led_strip", (bx - ux * L / 2, by - uy * L / 2), room, "work", "c", 14, end=(round(bx + ux * L / 2), round(by + uy * L / 2)))
                for k in (-0.33, 0, 0.33):
                    add("spot", (run.x + fx * 700 + ux * L * k, run.y + fy * 700 + uy * L * k), room, "work", "b", 7)
            if table:
                count = 3 if max(table.w, table.d) >= 1600 else 2
                long_x = footprint(table).w >= footprint(table).h
                for k in range(count):
                    t = (k - (count - 1) / 2) * 450
                    add("pendant", (table.x + (t if long_x else 0), table.y + (0 if long_x else t)), room, "accent", "d", 12)
            if sofa:
                fx, fy = (-math.sin(math.radians(sofa.rotation)), math.cos(math.radians(sofa.rotation)))
                cx, cy = sofa.x + fx * 1300, sofa.y + fy * 1300
                ux, uy = (fy, -fx)
                add("track", (cx - ux * 1200, cy - uy * 1200), room, "general", "a", 36, end=(round(cx + ux * 1200), round(cy + uy * 1200)))
            # perimeter cove for multi-level ceiling
            ceil = next((c for c in sc.ceilings if c.room_id == room.id), None)
            if ceil and ceil.type in ("gkl_multilevel", "cove", "shadow_gap"):
                poly = room.polygon
                for i in range(len(poly)):
                    a, b = poly[i], poly[(i + 1) % len(poly)]
                    add("led_strip", a, room, "night", "e", 10 * dist(a, b) / 1000, end=b)
        else:  # bedrooms, kids, office
            bed = objs.get("bed") or objs.get("kids_bed")
            add("ceiling" if area < 12 else "pendant", label_point(room.polygon), room, "general", "a", 24)
            if bed:
                for side in (-1, 1):
                    p = _wall_point_behind(bed, side * (bed.w / 2 + 250))
                    add("wall", p, room, "night", "b", 6)
            ceil = next((c for c in sc.ceilings if c.room_id == room.id), None)
            if ceil and ceil.curtain_niche:
                poly = room.polygon
                win_edge = max(range(len(poly)), key=lambda i: -min(poly[i][1], poly[(i + 1) % len(poly)][1]))
                a, b = poly[win_edge], poly[(win_edge + 1) % len(poly)]
                add("led_strip", a, room, "night", "c", 8, end=b)
    sc.lights = lights


def _cameras(sc: Scene) -> None:
    """Up to three viewpoints per room: from free floor near the corners towards the
    room centre, never inside furniture."""
    cams = []
    for room in sc.rooms:
        if room.type in ("balcony",):
            continue
        c = label_point(room.polygon)
        blockers = [footprint(o).inflate(250) for o in sc.objects if o.room_id == room.id and o.h > 500]
        corners = sorted(room.polygon, key=lambda p: -dist(p, c))
        used: list[tuple[float, float]] = []
        for p in corners:
            if len(used) == 3:
                break
            for tt in (0.12, 0.2, 0.3, 0.42, 0.55):
                pos = lerp(p, c, tt)
                if not point_in_polygon(pos, room.polygon):
                    continue
                if any(b.x0 <= pos[0] <= b.x1 and b.y0 <= pos[1] <= b.y1 for b in blockers):
                    continue
                if any(dist(pos, u) < 900 for u in used):
                    break
                used.append(pos)
                # look across the room: aim past the centre so the far walls are in view
                tgt = lerp(pos, c, 2.0)
                if not point_in_polygon(tgt, room.polygon):
                    tgt = c
                cams.append(Camera(id=f"C-{room.id}-{len(used)}", room_id=room.id, position=(round(pos[0]), round(pos[1])), target=(round(tgt[0]), round(tgt[1]))))
                break
    sc.cameras = cams


def apply_finishes(sc: Scene, chosen: dict[str, dict[str, list[Candidate]]]) -> None:
    fin: list[SurfaceFinish] = []
    glob = chosen.get("_", {})
    for room in sc.rooms:
        cands = chosen.get(room.id, {})

        def first(*cats, cands=cands):
            for c in cats:
                lst = cands.get(c) or glob.get(c)
                if lst:
                    return lst[0]
            return None

        wet = room.type in ("bathroom", "wc", "balcony")
        floor = first("floor_tile") if wet or room.type == "hallway" else first("floor_parquet", "floor_laminate")
        if floor:
            fin.append(SurfaceFinish(room_id=room.id, surface="floor", product_variant_id=floor.ref, name=floor.name, color_hex=floor.color_hex,
                                     pattern="large_tile" if floor.category == "floor_tile" else ("herringbone" if floor.tier == "premium" else "plank")))
        paint = first("wall_paint")
        if paint and room.type != "balcony":
            fin.append(SurfaceFinish(room_id=room.id, surface="walls", product_variant_id=paint.ref, name=paint.name, color_hex=paint.color_hex, pattern="paint"))
        if wet and room.type != "balcony":
            t = first("wall_tile")
            if t:
                fin.append(SurfaceFinish(room_id=room.id, surface="wet_walls", product_variant_id=t.ref, name=t.name, color_hex=t.color_hex, pattern="tile_grid"))
        if room.type in ("kitchen_living", "kitchen"):
            t = first("wall_tile")
            if t:
                fin.append(SurfaceFinish(room_id=room.id, surface="apron", product_variant_id=t.ref, name=t.name, color_hex=t.color_hex, pattern="tile_grid"))
        if room.type in ("bedroom", "kitchen_living", "living"):
            p = first("wall_panel")
            if p:
                fin.append(SurfaceFinish(room_id=room.id, surface="accent_wall", product_variant_id=p.ref, name=p.name, color_hex=p.color_hex, pattern="plain"))
    for i, f in enumerate(fin, 1):
        f.material_code = f"M-{i:02d}"
    sc.finishes = fin
