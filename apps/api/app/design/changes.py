"""Executes a structured ChangePlan (from the AI or the UI) against the real
catalogue, producing a preview or a new immutable version. Unmentioned rooms are
not touched: the layout engine is deterministic, so identical inputs give
identical placements."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import models as m
from ..ai.schemas import ChangePlan
from ..catalog.candidates import Candidate, resolve
from ..catalog.discovery import build_needs
from ..scene.model import Scene, SceneObject
from .engine import VariantPlan, _concept_candidate, _luma, build_variant, candidate_pools, rank

ROOM_ALIASES = {"kitchen": ["kitchen", "kitchen_living"], "living": ["living", "kitchen_living"], "kitchen_living": ["kitchen_living"]}


def _rooms_for(scene: Scene, room_type: str | None, room_id: str | None) -> list[str]:
    if room_id:
        return [room_id]
    if not room_type:
        return [r.id for r in scene.rooms]
    types = ROOM_ALIASES.get(room_type, [room_type])
    return [r.id for r in scene.rooms if r.type in types]


def _load_selection(db: Session, selection: dict) -> dict[str, dict[str, list[Candidate]]]:
    out: dict[str, dict[str, list[Candidate]]] = {}
    cache: dict[str, Candidate | None] = {}
    for room, cats in selection.items():
        for cat, refs in cats.items():
            lst = []
            for ref in refs:
                if ref not in cache:
                    cache[ref] = _concept_candidate(ref.split(":", 1)[1]) if ref.startswith("concept:") else resolve(db, ref)
                if cache[ref]:
                    lst.append(cache[ref])
            out.setdefault(room, {})[cat] = lst
    return out


def _pool(primary, fallback, cat):
    return (primary.get(cat) or []) + [c for c in (fallback.get(cat) or []) if c.ref not in {x.ref for x in primary.get(cat) or []}]


def apply_plan(db: Session, project: m.Project, variant: m.DesignVariant, version: m.DesignVersion, base: Scene, plan: ChangePlan) -> dict:
    """Returns {"result": VariantResult, "applied": [...], "skipped": [...], "diff": {...}}"""
    old_scene = Scene.model_validate(version.scene)
    summary = dict(version.change_summary or {})
    selection = summary.get("selection") or {}
    extras: dict[str, list[str]] = {k: list(v) for k, v in (summary.get("extras") or {}).items()}
    chosen = _load_selection(db, selection)
    pools = candidate_pools(db, project, _latest_snapshot(db, project))
    primary, fallback = pools
    style, tier = variant.style, variant.tier
    applied, skipped = [], []
    locked = [o for o in old_scene.objects if o.locked]

    for op in plan.operations:
        rooms = _rooms_for(old_scene, op.room_type, op.room_id)
        cat = op.category
        if op.op in ("replace_product", "make_compact", "cheaper", "premium", "remove_object", "change_color") and not cat:
            skipped.append({"op": op.op, "reason": "Не указана категория предмета"})
            continue
        if op.op == "replace_product":
            for r in rooms:
                lst = chosen.get(r, {}).get(cat)
                if lst and len(lst) > 1:
                    chosen[r][cat] = lst[1:] + lst[:1]
                    applied.append({"op": op.op, "room_id": r, "category": cat, "to": chosen[r][cat][0].name})
        elif op.op == "make_compact":
            for r in rooms:
                cur = (chosen.get(r, {}).get(cat) or [None])[0]
                if not cur:
                    continue
                limit = op.params.max_width_mm or cur.w - 1
                pool = [c for c in _pool(primary, fallback, cat) if c.w and c.w < min(limit + 1, cur.w)]
                ranked = rank(pool, cat=cat, style=style, tier=tier, max_width=limit)
                if ranked:
                    chosen[r][cat] = ranked[:4]
                    applied.append({"op": op.op, "room_id": r, "category": cat, "to": ranked[0].name, "width_mm": ranked[0].w})
                else:
                    skipped.append({"op": op.op, "room_id": r, "reason": f"Нет более компактных аналогов категории {cat} в каталоге"})
        elif op.op in ("cheaper", "premium"):
            cats = [cat] if cat else None
            for r in rooms:
                for c_key in cats or list(chosen.get(r, {}).keys()):
                    cur = (chosen.get(r, {}).get(c_key) or [None])[0]
                    if not cur or cur.price_amd is None:
                        continue
                    pool = [c for c in _pool(primary, fallback, c_key) if c.price_amd is not None and ((c.price_amd < cur.price_amd) if op.op == "cheaper" else (c.price_amd > cur.price_amd))]
                    if pool:
                        pool.sort(key=lambda c: -c.price_amd if op.op == "cheaper" else c.price_amd)
                        chosen[r][c_key] = pool[:1] + [x for x in chosen[r][c_key] if x.ref != pool[0].ref][:3]
                        applied.append({"op": op.op, "room_id": r, "category": c_key, "to": pool[0].name})
        elif op.op in ("lighter", "darker"):
            light = op.op == "lighter"
            for r in rooms:
                for c_key, lst in list(chosen.get(r, {}).items()):
                    if not lst:
                        continue
                    pool = [c for c in _pool(primary, fallback, c_key) if c.tier == lst[0].tier] or lst
                    best = max(pool, key=lambda c: _luma(c.color_hex) if light else -_luma(c.color_hex))
                    if best.ref != lst[0].ref and ((_luma(best.color_hex) > _luma(lst[0].color_hex)) == light):
                        chosen[r][c_key] = [best] + [x for x in lst if x.ref != best.ref][:3]
                        applied.append({"op": op.op, "room_id": r, "category": c_key, "to": best.name})
                # finishes are global → create room-level overrides
                for f_cat in ("wall_paint", "floor_parquet", "floor_tile"):
                    glob = chosen.get("_", {}).get(f_cat)
                    if not glob:
                        continue
                    pool = [c for c in _pool(primary, fallback, f_cat) if c.tier == glob[0].tier] or glob
                    best = max(pool, key=lambda c: _luma(c.color_hex) if light else -_luma(c.color_hex))
                    chosen.setdefault(r, {})[f_cat] = [best]
                    applied.append({"op": op.op, "room_id": r, "category": f_cat, "to": best.name})
        elif op.op == "add_object":
            for r in rooms[:1]:
                pool = _pool(primary, fallback, cat)
                if op.params.closed_storage:
                    pool = [c for c in pool if c.category in ("wardrobe", "hallway_wardrobe", "storage_system")]
                ranked = rank(pool, cat=cat, style=style, tier=tier, max_width=None)
                if ranked:
                    chosen.setdefault(r, {})[cat] = ranked[:4]
                    extras.setdefault(r, [])
                    if cat not in extras[r]:
                        extras[r].append(cat)
                    applied.append({"op": op.op, "room_id": r, "category": cat, "to": ranked[0].name})
                else:
                    skipped.append({"op": op.op, "room_id": r, "reason": f"В каталоге нет товаров категории {cat}"})
        elif op.op == "remove_object":
            for r in rooms:
                if chosen.get(r, {}).get(cat):
                    chosen[r][cat] = []
                    extras.get(r, []) and cat in extras[r] and extras[r].remove(cat)
                    applied.append({"op": op.op, "room_id": r, "category": cat})
        elif op.op == "change_style" and op.params.style:
            style = op.params.style
            applied.append({"op": op.op, "style": style})
        elif op.op == "budget_delta":
            pass  # handled after the other operations
        else:
            skipped.append({"op": op.op, "reason": "Операция не поддерживается"})

    needs = build_needs(base, project.brief or {})
    vplan = VariantPlan(variant.key, style, tier, variant.title, variant.subtitle)
    result = build_variant(db, project, base, needs, vplan, pools, overrides=chosen, extras=extras, locked=locked)

    budget_op = next((o for o in plan.operations if o.op == "budget_delta" and o.params.delta_amd), None)
    if budget_op:
        target = result.estimate["totals"]["known"] + budget_op.params.delta_amd
        tried: set[tuple[str, str]] = set()
        for _ in range(25):
            if result.estimate["totals"]["known"] <= target:
                break
            # most expensive downgradable line first
            lines = sorted((ln for ln in result.estimate["lines"] if ln.get("ref") and ln["total"]), key=lambda ln: -ln["total"])
            moved = False
            for ln in lines:
                for r in ln.get("rooms") or ["_"]:
                    key = (r, ln["category"])
                    if key in tried:
                        continue
                    tried.add(key)
                    room_key = r if ln["category"] in chosen.get(r, {}) else "_"
                    cur = (chosen.get(room_key, {}).get(ln["category"]) or [None])[0]
                    if not cur or cur.price_amd is None:
                        continue
                    pool = [c for c in _pool(primary, fallback, ln["category"]) if c.price_amd is not None and c.price_amd < cur.price_amd]
                    if not pool:
                        continue
                    pool.sort(key=lambda c: -c.price_amd)  # the closest cheaper option first
                    chosen[room_key][ln["category"]] = [pool[0]]
                    applied.append({"op": "budget_delta", "room_id": room_key, "category": ln["category"], "to": pool[0].name,
                                    "saving": round((cur.price_amd - pool[0].price_amd) * ln["qty"])})
                    moved = True
                    break
                if moved:
                    break
            if not moved:
                skipped.append({"op": "budget_delta", "reason": "Дальнейшее снижение невозможно без отказа от позиций"})
                break
            result = build_variant(db, project, base, needs, vplan, pools, overrides=chosen, extras=extras, locked=locked)

    diff = scene_diff(old_scene, result.scene, version.estimate or {}, result.estimate)
    return {"result": result, "applied": applied, "skipped": skipped + [{"op": "unsupported", "reason": u} for u in plan.unsupported],
            "diff": diff, "extras": extras, "style": style}


def _latest_snapshot(db: Session, project: m.Project) -> m.ProjectCatalogSnapshot | None:
    return (db.query(m.ProjectCatalogSnapshot).filter(m.ProjectCatalogSnapshot.project_id == project.id)
            .order_by(m.ProjectCatalogSnapshot.created_at.desc()).first())


def scene_diff(a: Scene, b: Scene, est_a: dict, est_b: dict) -> dict:
    def key(o: SceneObject):
        return (o.room_id, o.category)

    am = {}
    for o in a.objects:
        am.setdefault(key(o), []).append(o)
    bm = {}
    for o in b.objects:
        bm.setdefault(key(o), []).append(o)
    added, removed, changed, moved = [], [], [], []
    for k in set(am) | set(bm):
        oa, ob = am.get(k, []), bm.get(k, [])
        if not oa:
            added += [{"room_id": k[0], "category": k[1], "name": o.name} for o in ob]
        elif not ob:
            removed += [{"room_id": k[0], "category": k[1], "name": o.name} for o in oa]
        else:
            if oa[0].product_variant_id != ob[0].product_variant_id:
                changed.append({"room_id": k[0], "category": k[1], "from": oa[0].name, "to": ob[0].name})
            elif (oa[0].x, oa[0].y, oa[0].rotation) != (ob[0].x, ob[0].y, ob[0].rotation):
                moved.append({"room_id": k[0], "category": k[1], "name": ob[0].name})
            if len(oa) != len(ob):
                (added if len(ob) > len(oa) else removed).append({"room_id": k[0], "category": k[1], "name": ob[0].name, "count": abs(len(ob) - len(oa))})
    ta = (est_a.get("totals") or {}).get("known", 0)
    tb = (est_b.get("totals") or {}).get("known", 0)
    rooms = sorted({x["room_id"] for x in added + removed + changed + moved})
    return {"added": added, "removed": removed, "changed": changed, "moved": moved, "rooms_affected": rooms,
            "total_before": ta, "total_after": tb, "total_delta": tb - ta}
