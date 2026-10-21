"""Shared domain operations used by several routers."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as m
from .catalog.candidates import Candidate, resolve
from .design.engine import _concept_candidate, metrics_for, supplier_info
from .errors import ApiError
from .estimate.estimator import estimate
from .scene.model import Scene
from .scene.rules import run_rules


def candidates_for_scene(db: Session, scene: Scene, selection: dict | None = None) -> dict[str, Candidate]:
    refs = {o.product_variant_id for o in scene.objects if o.product_variant_id}
    refs |= {f.product_variant_id for f in scene.finishes if f.product_variant_id}
    refs |= {o.product_variant_id for o in scene.openings if o.product_variant_id}
    refs |= {li.product_variant_id for li in scene.lights if li.product_variant_id}
    for cats in (selection or {}).values():
        for lst in cats.values():
            refs |= set(lst[:1])
    out: dict[str, Candidate] = {}
    for ref in refs:
        c = _concept_candidate(ref.split(":", 1)[1]) if ref.startswith("concept:") else resolve(db, ref)
        if c:
            out[ref] = c
    return out


def recompute(db: Session, project: m.Project, scene: Scene, selection: dict | None) -> tuple[list[dict], dict, dict]:
    cands = candidates_for_scene(db, scene, selection)
    for cat in ("putty", "tile_adhesive", "drywall", "led_strip"):
        ref = ((selection or {}).get("_", {}).get(cat) or [None])[0]
        if ref and ref not in cands:
            c = resolve(db, ref)
            if c:
                cands[ref] = c
    issues = run_rules(scene, {"accuracy_level": project.accuracy_level})
    est = estimate(scene, cands, supplier_info(db), budget_amd=(project.brief or {}).get("budget_amd"), accuracy_level=project.accuracy_level)
    metrics = metrics_for(scene, est, issues, project.confidence or 0.8)
    return issues, est, metrics


def new_version(db: Session, project: m.Project, variant: m.DesignVariant, scene: Scene, *, selection: dict, extras: dict | None, source: str,
                note: str, user_id: str | None, diff: dict | None = None, estimate_override: dict | None = None, issues_override=None) -> m.DesignVersion:
    cur = db.get(m.DesignVersion, variant.current_version_id) if variant.current_version_id else None
    if variant.status == "approved":
        raise ApiError(409, "variant.approved_immutable")
    if estimate_override is not None:
        est, issues = estimate_override, issues_override or []
        metrics = metrics_for(scene, est, issues, project.confidence or 0.8)
    else:
        issues, est, metrics = recompute(db, project, scene, selection)
    num = (db.scalar(select(func.max(m.DesignVersion.number)).where(m.DesignVersion.variant_id == variant.id)) or 0) + 1
    ver = m.DesignVersion(variant_id=variant.id, number=num, parent_id=cur.id if cur else None, scene=scene.model_dump(mode="json"), estimate=est, issues=issues,
                          change_summary={"selection": selection, "extras": extras or {}, "note": note, "diff": diff or {}}, source=source, created_by=user_id)
    db.add(ver)
    db.flush()
    variant.current_version_id = ver.id
    variant.metrics = {**(variant.metrics or {}), **metrics}
    project.updated_at = datetime.now(timezone.utc)
    return ver


def variant_dict(v: m.DesignVariant, include_version: m.DesignVersion | None = None) -> dict:
    d = {"id": v.id, "key": v.key, "title": v.title, "subtitle": v.subtitle, "description": v.description, "style": v.style, "tier": v.tier, "mode": v.mode,
         "status": v.status, "palette": v.palette, "metrics": v.metrics, "current_version_id": v.current_version_id, "created_at": v.created_at.isoformat()}
    if include_version:
        d["version"] = version_dict(include_version)
    return d


def version_dict(ver: m.DesignVersion, full: bool = True) -> dict:
    d = {"id": ver.id, "number": ver.number, "parent_id": ver.parent_id, "source": ver.source, "frozen": ver.frozen, "created_at": ver.created_at.isoformat(),
         "note": (ver.change_summary or {}).get("note"), "diff": (ver.change_summary or {}).get("diff"), "total": (ver.estimate or {}).get("totals", {}).get("known")}
    if full:
        d.update({"scene": ver.scene, "estimate": ver.estimate, "issues": ver.issues, "selection": (ver.change_summary or {}).get("selection", {})})
    return d


def project_dict(p: m.Project) -> dict:
    return {"id": p.id, "title": p.title, "address": p.address, "city": p.city, "property_type": p.property_type, "area_m2": p.area_m2,
            "renovation_stage": p.renovation_stage, "accuracy_level": p.accuracy_level, "confidence": p.confidence, "status": p.status,
            "preferences": p.preferences, "brief": p.brief, "product_source": p.product_source, "external_settings": p.external_settings,
            "client_name": p.client_name, "designer_name": p.designer_name, "doc_lang": p.doc_lang, "share_token": p.share_token,
            "org_id": p.org_id, "created_at": p.created_at.isoformat(), "updated_at": p.updated_at.isoformat() if p.updated_at else None}
