"""Variant generation: grounded selection → layout → rules → deterministic estimate."""
from __future__ import annotations

import colorsys
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.candidates import TIER_TARGET, TYPICAL_DIMS, Candidate, score
from ..catalog.demo_seed import BASE
from ..catalog.discovery import build_needs, internal_candidates, snapshot_candidates
from ..catalog.taxonomy import STYLES
from ..estimate.estimator import estimate
from ..scene.layout import apply_finishes, furnish
from ..scene.model import Scene, SceneObject
from ..scene.rules import run_rules, summarize

LIGHT_CAT = {"spot": "spot_light", "pendant": "pendant_light", "track": "track_light", "wall": "wall_light", "ceiling": "pendant_light"}
DOOR_CAT = {"door": "door_interior", "sliding_door": "door_sliding", "entrance_door": "door_entrance"}
TIER_TITLES = {"economy": "Эконом", "comfort": "Комфорт", "business": "Бизнес", "premium": "Премиум"}


@dataclass
class VariantPlan:
    key: str
    style: str
    tier: str
    title: str
    subtitle: str


@dataclass
class VariantResult:
    plan: VariantPlan
    scene: Scene
    selection: dict[str, dict[str, list[str]]]
    estimate: dict
    issues: list[dict]
    metrics: dict
    unplaced: list[dict] = field(default_factory=list)
    sourcing: dict = field(default_factory=dict)


def variant_plans(brief: dict) -> list[VariantPlan]:
    styles = [s for s in brief.get("styles", []) if s in STYLES]
    tier = brief.get("budget_tier") or "comfort"
    if styles and len(styles) == 1:
        s = styles[0]
        st = STYLES[s]
        return [
            VariantPlan("economy", s, "economy", f"{st['ru']} · Эконом", "Разумный бюджет, те же решения"),
            VariantPlan("optimal", s, tier if tier != "economy" else "comfort", f"{st['ru']} · Оптимальный", st["subtitle"]),
            VariantPlan("premium", s, "premium", f"{st['ru']} · Премиум", "Материалы и изделия высокого класса"),
        ]
    picked = (styles + [s for s in ("warm_minimal", "modern_loft", "soft_scandi") if s not in styles])[:3]
    return [VariantPlan(s, s, tier, STYLES[s]["ru"], STYLES[s]["subtitle"]) for s in picked]


def _concept_candidate(cat: str) -> Candidate:
    w, d, h = TYPICAL_DIMS.get(cat, (600, 600, 800))
    return Candidate(ref=f"concept:{cat}", category=cat, name=f"Концепт: {cat}", supplier_name="—", supplier_key="concept", price_amd=None,
                     price_status="concept", w=w, d=d, h=h, dims_known=False, confidence=0.4, warnings=["Concept Mode: объект не связан с товаром"])


def candidate_pools(db: Session, project: m.Project, snap: m.ProjectCatalogSnapshot | None) -> tuple[dict[str, list[Candidate]], dict[str, list[Candidate]]]:
    """Returns (primary pools, fallback pools). External mode → snapshot first, DEMO fallback."""
    internal = internal_candidates(db, include_demo=True)
    if project.product_source == "external":
        return snapshot_candidates(db, snap), internal
    if project.product_source == "own":
        return internal, {}
    return {}, {}


def _luma(hex_: str) -> float:
    h = hex_.lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return 0.5
    return colorsys.rgb_to_hls(r, g, b)[1]


def rank(pool: list[Candidate], *, cat: str, style: str, tier: str, max_width: float | None, prefer_light: bool | None = None) -> list[Candidate]:
    base_price = BASE.get(cat, (None, None, None))[2]
    target = base_price * TIER_TARGET.get(tier, 1.0) if base_price else None
    scored = []
    for c in pool:
        if c.category != cat:
            continue
        s, _ = score(c, category=cat, style=style, tier=tier, target_price=target, max_width=max_width)
        if c.tier == tier:
            s += 0.08
        if prefer_light is not None:
            s += (_luma(c.color_hex) - 0.5) * (0.4 if prefer_light else -0.4)
        scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored]


def select_products(needs: list[dict], primary: dict, fallback: dict, *, style: str, tier: str, concept: bool,
                    overrides: dict | None = None) -> tuple[dict[str, dict[str, list[Candidate]]], dict]:
    chosen: dict[str, dict[str, list[Candidate]]] = {}
    sourcing = {"external": 0, "internal": 0, "demo_fallback": 0, "concept": 0, "missing": []}
    for n in needs:
        room = n["room_id"] or "_"
        cat = n["category"]
        if concept:
            lst = [_concept_candidate(cat)]
            sourcing["concept"] += 1
        else:
            lst = rank(primary.get(cat, []), cat=cat, style=style, tier=tier, max_width=n["max_width_mm"])
            if lst:
                sourcing["external" if lst[0].ref.startswith("ext:") else "internal"] += 1
            else:
                lst = rank(fallback.get(cat, []), cat=cat, style=style, tier=tier, max_width=n["max_width_mm"])
                if lst:
                    sourcing["demo_fallback" if lst[0].is_demo else "internal"] += 1
                else:
                    sourcing["missing"].append(cat)
        chosen.setdefault(room, {})[cat] = lst[:4]
    for room, cats in (overrides or {}).items():
        for cat, lst in cats.items():
            chosen.setdefault(room, {})[cat] = lst
    return chosen, sourcing


def ground_engineering(scene: Scene, chosen: dict) -> None:
    glob = chosen.get("_", {})
    for li in scene.lights:
        cat = LIGHT_CAT.get(li.type)
        lst = (chosen.get(li.room_id or "", {}).get(cat) if cat else None) or (glob.get(cat) if cat else None)
        if lst:
            li.product_variant_id = lst[0].ref
    for op in scene.openings:
        cat = DOOR_CAT.get(op.type)
        lst = glob.get(cat) if cat else None
        if lst:
            op.product_variant_id = lst[0].ref


def all_candidates(chosen: dict) -> dict[str, Candidate]:
    out: dict[str, Candidate] = {}
    for cats in chosen.values():
        for lst in cats.values():
            for c in lst:
                out[c.ref] = c
    return out


def supplier_info(db: Session) -> dict[str, dict]:
    return {s.slug: {"delivery": s.delivery, "installation": s.installation, "is_demo": s.is_demo, "name": s.name} for s in db.scalars(select(m.Supplier))}


def metrics_for(scene: Scene, est: dict, issues: list[dict], base_confidence: float) -> dict:
    objs = scene.objects
    conf = sum(o.confidence for o in objs) / len(objs) if objs else 0
    s = summarize(issues)
    lead = max((ln.get("lead_days") or 0 for ln in est["lines"]), default=0)
    goods = [ln for ln in est["lines"] if ln.get("ref")]
    avail = sum(1 for ln in goods if ln.get("stock") == "in_stock") / len(goods) if goods else 0
    feas = max(0.0, 1 - s["block"] * 0.12 - s["warning"] * 0.025)
    return {
        "total": est["totals"]["known"], "range_low": est["totals"]["range_low"], "range_high": est["totals"]["range_high"],
        "quote_required": est["totals"]["quote_required_lines"], "confidence": round(conf * 0.5 + base_confidence * 0.5, 2),
        "feasibility": round(feas, 2), "lead_days_max": lead, "availability_share": round(avail, 2), "items": len(objs),
        "issues": s, "budget": est.get("budget"),
    }


def build_variant(db: Session, project: m.Project, base: Scene, needs: list[dict], plan: VariantPlan, pools, *,
                  overrides=None, extras=None, locked: list[SceneObject] | None = None, base_confidence: float = 0.8) -> VariantResult:
    primary, fallback = pools
    chosen, sourcing = select_products(needs, primary, fallback, style=plan.style, tier=plan.tier, concept=project.product_source == "concept", overrides=overrides)
    res = furnish(base, chosen, tier=plan.tier, extras=extras, locked=locked)
    scene = res.scene
    apply_finishes(scene, chosen)
    ground_engineering(scene, chosen)
    issues = run_rules(scene, {"accuracy_level": project.accuracy_level})
    cands = all_candidates(chosen)
    budget = (project.brief or {}).get("budget_amd")
    est = estimate(scene, cands, supplier_info(db), budget_amd=budget, accuracy_level=project.accuracy_level)
    selection = {room: {cat: [c.ref for c in lst] for cat, lst in cats.items()} for room, cats in chosen.items()}
    metrics = metrics_for(scene, est, issues, base_confidence)
    metrics["sourcing"] = sourcing
    metrics["unplaced"] = res.unplaced
    return VariantResult(plan, scene, selection, est, issues, metrics, res.unplaced, sourcing)


def generate_variants(db: Session, project: m.Project, base: Scene, brief: dict, snap: m.ProjectCatalogSnapshot | None) -> list[VariantResult]:
    needs = build_needs(base, brief)
    pools = candidate_pools(db, project, snap)
    return [build_variant(db, project, base, needs, plan, pools, base_confidence=project.confidence or 0.8) for plan in variant_plans(brief)]
