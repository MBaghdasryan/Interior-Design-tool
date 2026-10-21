"""Extensible ergonomics / constructability rules engine.

Each rule returns RuleResult items with severity pass | warning | block, a human
explanation and the related element ids. New rules register with @rule."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field

from .geometry import (
    Rect,
    dist,
    door_swing_rect,
    footprint,
    front_zone,
    opening_world,
    point_in_polygon,
    rect_inside_polygon,
)
from .model import Scene, SceneObject


@dataclass
class RuleResult:
    rule: str
    severity: str  # pass | warning | block
    message: str
    element_ids: list[str] = field(default_factory=list)
    room_id: str | None = None
    code: str = ""  # stable message code for client-side localisation (rules.<code>)
    params: dict = field(default_factory=dict)

    def dict(self) -> dict:
        return asdict(self)


RuleFn = Callable[[Scene, dict], list[RuleResult]]
RULES: dict[str, RuleFn] = {}

# Objects that may legally overlap others (rug under sofa, chairs tucked under a table…)
OVERLAY_CATEGORIES = {"rug", "curtains", "pendant_light", "ceiling_light", "wall_shelf", "mirror", "tv", "artwork"}
TUCK_PAIRS = {("dining_chair", "dining_table"), ("desk_chair", "desk"), ("bar_stool", "kitchen_island"), ("stool", "vanity")}
# Required free zone in front of an item (mm). Values from common ergonomics practice.
FRONT_CLEARANCE = {
    "sofa": 600, "bed": 600, "wardrobe": 700, "kitchen_run": 1000, "fridge": 900, "toilet": 600,
    "vanity": 700, "bathtub": 700, "shower": 700, "washer": 700, "desk": 700, "tv_unit": 0,
    "dresser": 700, "shoe_cabinet": 600, "hallway_wardrobe": 700, "dining_table": 0, "kids_bed": 600,
    "storage_system": 600, "bench": 500, "nightstand": 0, "coffee_table": 0, "armchair": 450,
}
# pairs allowed inside each other's service zone by design
ZONE_FRIENDS = [{"dining_chair", "dining_table"}, {"desk_chair", "desk"}, {"coffee_table", "sofa"}, {"coffee_table", "armchair"},
                {"nightstand", "bed"}, {"bench", "hallway_wardrobe"}]
MIN_SOCKETS = {"living": 6, "kitchen_living": 10, "kitchen": 6, "bedroom": 4, "kids": 4, "hallway": 2, "bathroom": 2, "office": 4}


def rule(name: str) -> Callable[[RuleFn], RuleFn]:
    def deco(fn: RuleFn) -> RuleFn:
        RULES[name] = fn
        return fn

    return deco


def _overlay(o: SceneObject) -> bool:
    return o.category in OVERLAY_CATEGORIES or o.elevation >= 1200


def _tucked(a: SceneObject, b: SceneObject) -> bool:
    return (a.category, b.category) in TUCK_PAIRS or (b.category, a.category) in TUCK_PAIRS


@rule("inside_room")
def inside_room(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for o in scene.objects:
        room = scene.room(o.room_id)
        if not room or o.category in OVERLAY_CATEGORIES:
            continue
        if not rect_inside_polygon(footprint(o), room.polygon, tol=5):
            out.append(RuleResult("inside_room", "block", f"{o.name or o.category} выходит за границы помещения «{room.name}»", [o.id], room.id, "outside_room", {"object": o.category, "code": o.code, "room": room.type}))
    return out


@rule("collisions")
def collisions(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    objs = [o for o in scene.objects if not _overlay(o)]
    for i, a in enumerate(objs):
        for b in objs[i + 1 :]:
            if a.room_id != b.room_id or _tucked(a, b):
                continue
            if footprint(a).overlaps(footprint(b), tol=5):
                out.append(RuleResult("collisions", "block", f"Пересечение: {a.name or a.category} и {b.name or b.category}", [a.id, b.id], a.room_id, "collision", {"a": a.category, "b": b.category, "a_code": a.code, "b_code": b.code}))
    return out


@rule("passages")
def passages(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for o in scene.objects:
        need = FRONT_CLEARANCE.get(o.category, 0)
        if need <= 0 or _overlay(o):
            continue
        zone = front_zone(o, need)
        room = scene.room(o.room_id)
        if room and not rect_inside_polygon(zone, room.polygon, tol=20):
            out.append(RuleResult("passages", "warning", f"Перед «{o.name or o.category}» нет {need} мм свободного прохода до стены", [o.id], o.room_id, "passage_wall", {"object": o.category, "code": o.code, "mm": need}))
            continue
        for b in scene.objects:
            if b.id == o.id or b.room_id != o.room_id or _overlay(b) or _tucked(o, b) or {o.category, b.category} in ZONE_FRIENDS:
                continue
            if zone.overlaps(footprint(b), tol=30):
                out.append(RuleResult("passages", "warning", f"Проход перед «{o.name or o.category}» менее {need} мм (мешает «{b.name or b.category}»)", [o.id, b.id], o.room_id, "passage_blocked", {"object": o.category, "code": o.code, "mm": need, "other": b.category, "other_code": b.code}))
                break
    return out


@rule("door_swing")
def door_swing(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for op in scene.openings:
        sweep = door_swing_rect(scene, op)
        if not sweep:
            continue
        for o in scene.objects:
            if _overlay(o):
                continue
            if sweep.inflate(-20).overlaps(footprint(o)):
                out.append(RuleResult("door_swing", "block", f"Дверь {op.id} при открывании задевает «{o.name or o.category}»", [op.id, o.id], o.room_id, "door_swing", {"door": op.id, "object": o.category, "code": o.code}))
    return out


@rule("window_access")
def window_access(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for op in scene.openings:
        if op.type not in ("window", "balcony_door"):
            continue
        seg = opening_world(scene, op)
        if not seg:
            continue
        p0, p1 = seg
        zone = Rect(min(p0[0], p1[0]) - 10, min(p0[1], p1[1]) - 10, max(p0[0], p1[0]) + 10, max(p0[1], p1[1]) + 10).inflate(450)
        for o in scene.objects:
            if _overlay(o) or o.h <= (op.sill or 0) - 50 and op.type == "window":
                continue
            if zone.overlaps(footprint(o), tol=50):
                sev = "block" if op.type == "balcony_door" else "warning"
                out.append(RuleResult("window_access", sev, f"«{o.name or o.category}» перекрывает доступ к {('балконной двери' if sev == 'block' else 'окну')} {op.id}", [op.id, o.id], o.room_id, "balcony_door_blocked" if sev == "block" else "window_blocked", {"opening": op.id, "object": o.category, "code": o.code}))
    return out


@rule("radiator_access")
def radiator_access(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for f in scene.fixtures:
        if f.type != "radiator" or not f.size:
            continue
        w, d = f.size
        r = Rect(f.position[0] - w / 2, f.position[1] - d / 2, f.position[0] + w / 2, f.position[1] + d / 2).inflate(150)
        for o in scene.objects:
            if _overlay(o) or o.h <= 600:
                continue
            if r.overlaps(footprint(o), tol=20):
                out.append(RuleResult("radiator_access", "warning", f"«{o.name or o.category}» закрывает радиатор {f.id} — снижение теплоотдачи", [f.id, o.id], o.room_id, "radiator_blocked", {"radiator": f.id, "object": o.category, "code": o.code}))
    return out


@rule("kitchen_triangle")
def kitchen_triangle(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for room in scene.rooms:
        if room.type not in ("kitchen", "kitchen_living"):
            continue
        objs = [o for o in scene.objects if o.room_id == room.id]
        run = next((o for o in objs if o.category == "kitchen_run"), None)
        fridge = next((o for o in objs if o.category == "fridge"), None)
        if not run:
            out.append(RuleResult("kitchen_triangle", "warning", "Кухонный гарнитур не размещён", [], room.id, "kitchen_missing", {}))
            continue
        # sink & cooktop positions are stored in the custom product definition of the run
        cp = run.custom_product or {}
        sink = tuple(cp.get("sink_xy") or (run.x, run.y))
        hob = tuple(cp.get("hob_xy") or (run.x, run.y))
        fr = (fridge.x, fridge.y) if fridge else tuple(cp.get("fridge_xy") or (run.x, run.y))
        perim = dist(sink, hob) + dist(hob, fr) + dist(fr, sink)
        if perim < 3600 or perim > 7900:
            out.append(RuleResult("kitchen_triangle", "warning", f"Рабочий треугольник {perim / 1000:.1f} м (норма 3.6–7.9 м)", [run.id], room.id, "triangle_out_of_range", {"m": round(perim / 1000, 1)}))
        else:
            out.append(RuleResult("kitchen_triangle", "pass", f"Рабочий треугольник {perim / 1000:.1f} м", [run.id], room.id, "triangle_ok", {"m": round(perim / 1000, 1)}))
        water = [f for f in scene.fixtures if f.type in ("water_cold", "drain") and f.room_id == room.id]
        if water and dist(sink, water[0].position) > 1500:
            out.append(RuleResult("kitchen_triangle", "warning", f"Мойка удалена от точки водоотведения на {dist(sink, water[0].position) / 1000:.1f} м — нужен уклон/насос", [run.id], room.id, "sink_far_from_drain", {"m": round(dist(sink, water[0].position) / 1000, 1)}))
    return out


@rule("sockets")
def sockets(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for room in scene.rooms:
        need = MIN_SOCKETS.get(room.type)
        if not need:
            continue
        n = 0
        for e in scene.electrical:
            if e.type.startswith("socket") or e.type in ("tv", "oven", "cooktop", "dishwasher", "washer", "fridge", "hood"):
                if e.room_id == room.id or point_in_polygon(e.position, room.polygon):
                    n += {"socket_double": 2, "socket_triple": 3}.get(e.type, 1)
        if n < need:
            out.append(RuleResult("sockets", "warning", f"«{room.name}»: {n} розеток при рекомендуемых {need}", [], room.id, "sockets_low", {"room": room.type, "n": n, "need": need}))
    return out


@rule("structure")
def structure(scene: Scene, ctx: dict) -> list[RuleResult]:
    out = []
    for w in scene.walls:
        if w.status == "demolish" and w.load_bearing:
            out.append(RuleResult("structure", "block", f"Демонтаж несущей стены {w.id} запрещён без проекта усиления", [w.id], None, "load_bearing_demolition", {"wall": w.id}))
        elif w.status == "demolish" and w.confidence < 0.9:
            out.append(RuleResult("structure", "warning", f"Стена {w.id}: несущая способность не подтверждена — требуется заключение до демонтажа", [w.id], None, "bearing_unconfirmed", {"wall": w.id}))
    return out


@rule("accuracy")
def accuracy(scene: Scene, ctx: dict) -> list[RuleResult]:
    level = ctx.get("accuracy_level", "concept")
    if level == "production":
        return []
    sized = [o for o in scene.objects if (o.custom_product or {}).get("made_to_measure")]
    if sized:
        return [RuleResult("accuracy", "warning", f"{len(sized)} изделий изготавливаются по размерам — заказ возможен только после верификации обмеров (уровень «Production Ready»)", [o.id for o in sized], None, "made_to_measure_needs_verification", {"n": len(sized)})]
    return []


def run_rules(scene: Scene, ctx: dict | None = None, only: list[str] | None = None) -> list[dict]:
    ctx = ctx or {}
    results: list[RuleResult] = []
    for name, fn in RULES.items():
        if only and name not in only:
            continue
        results.extend(fn(scene, ctx))
    order = {"block": 0, "warning": 1, "pass": 2}
    return [r.dict() for r in sorted(results, key=lambda r: order[r.severity])]


def summarize(issues: list[dict]) -> dict:
    return {
        "block": sum(1 for i in issues if i["severity"] == "block"),
        "warning": sum(1 for i in issues if i["severity"] == "warning"),
        "pass": sum(1 for i in issues if i["severity"] == "pass"),
        "rules": len(RULES),
    }
