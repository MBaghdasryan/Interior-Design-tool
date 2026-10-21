"""Three levels of project reliability (Concept Estimate → Verified Design →
Production Ready): requirements, checklist, allowed exports, provenance."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .scene.model import Scene

LEVELS = ["concept", "verified", "production"]

# Exports per level. Production drawings / made-to-measure orders need production.
EXPORTS = {
    "concept": {"album_pdf": "preview", "xlsx": "allowed", "csv": "allowed", "glb": "allowed", "json": "allowed", "dxf": "blocked", "dwg": "blocked", "order_made_to_measure": "blocked"},
    "verified": {"album_pdf": "allowed", "xlsx": "allowed", "csv": "allowed", "glb": "allowed", "json": "allowed", "dxf": "allowed", "dwg": "allowed", "order_made_to_measure": "blocked"},
    "production": {"album_pdf": "allowed", "xlsx": "allowed", "csv": "allowed", "glb": "allowed", "json": "allowed", "dxf": "allowed", "dwg": "allowed", "order_made_to_measure": "allowed"},
}
LIMITATIONS = {
    "concept": ["geometry_approximate", "estimate_indicative", "no_production_drawings", "engineering_preliminary"],
    "verified": ["specialist_review_required", "engineering_preliminary", "no_made_to_measure_orders"],
    "production": ["engineering_requires_licensed_design"],
}


def provenance(db: Session, project: m.Project, scene: Scene | None) -> dict:
    assets = db.scalars(select(m.SourceAsset).where(m.SourceAsset.project_id == project.id)).all()
    kinds = {a.kind for a in assets}
    meas = db.scalars(select(m.Measurement).where(m.Measurement.project_id == project.id)).all()
    src_counts: dict[str, int] = {}
    for el in [*(scene.walls if scene else []), *(scene.rooms if scene else [])]:
        src_counts[el.source] = src_counts.get(el.source, 0) + 1
    return {"photos": sum(1 for a in assets if a.kind in ("photo", "video")), "plans": sum(1 for a in assets if a.kind in ("plan_pdf", "plan_image", "dxf", "dwg", "ifc", "rvt")),
            "lidar": "lidar" in kinds, "control_dimensions": len(scene.control_dimensions) if scene else 0, "measurements": len(meas),
            "element_sources": src_counts}


def requirements(db: Session, project: m.Project, scene: Scene | None, base_confirmed: bool) -> dict:
    prov = provenance(db, project, scene)
    approvals = db.scalars(select(m.AuditEvent).where(m.AuditEvent.project_id == project.id, m.AuditEvent.action == "trust.specialist_verified")).all()
    crit = [a.key for a in (scene.assumptions if scene else []) if a.severity == "critical"]
    checks = {
        "verified": [
            {"code": "plan_or_survey", "ok": prov["plans"] > 0 or prov["lidar"] or (scene is not None and any(w.source in ("imported", "measured") for w in scene.walls))},
            {"code": "control_dimension", "ok": prov["control_dimensions"] > 0},
            {"code": "geometry_confirmed", "ok": base_confirmed},
        ],
        "production": [
            {"code": "verified_level", "ok": project.accuracy_level in ("verified", "production")},
            {"code": "professional_measurements", "ok": prov["measurements"] >= 3 or prov["lidar"]},
            {"code": "no_critical_assumptions", "ok": not crit, "params": {"keys": crit}},
            {"code": "specialist_signoff", "ok": bool(approvals)},
        ],
    }
    cur = project.accuracy_level
    nxt = LEVELS[LEVELS.index(cur) + 1] if cur in LEVELS and cur != "production" else None
    return {"level": cur, "next": nxt, "checklist": checks.get(nxt, []) if nxt else [], "all_checks": checks,
            "exports": EXPORTS.get(cur, EXPORTS["concept"]), "limitations": LIMITATIONS.get(cur, []), "provenance": prov,
            "signoffs": [{"user_id": a.user_id, "created_at": a.created_at.isoformat(), "data": a.data} for a in approvals]}
