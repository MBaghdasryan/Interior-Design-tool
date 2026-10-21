"""N99 pilot: intake manifest + end-to-end validation checklist.

Stages are derived from real project state (assets, confirmed geometry, versions,
approvals, album documents, specialist sign-off). Inputs that cannot be detected
automatically (family scenarios, kept items, Variant 4 materials…) are ticked by
the team. The pilot counts as validated only when every item is green — nothing
here marks Phase 7 as done by itself."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models as m
from .scene.model import Scene
from .trust import provenance

PILOT_CODE = "N99"
# (code, auto) — auto items are computed from data, the rest are confirmed by the team
MANIFEST = [
    ("plan_and_dims", True), ("photos_video", True), ("ceiling_height", False), ("openings", False), ("engineering", False),
    ("family_scenarios", False), ("styles_budget", True), ("room_list", True), ("kept_items", False), ("variant4_materials", False),
]
FLOW = ["upload", "recognition", "confidence_review", "variants", "manual_edit", "real_products", "estimate", "client_approval", "album", "specialist_qa"]


def _count(db: Session, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def status(db: Session, project: m.Project) -> dict:
    pilot = (project.preferences or {}).get("pilot") or {}
    manual: dict = pilot.get("manual", {})
    base = db.scalar(select(m.BaseScene).where(m.BaseScene.project_id == project.id).order_by(m.BaseScene.version.desc()).limit(1))
    scene = Scene.model_validate(base.data) if base else None
    prov = provenance(db, project, scene)
    variants = db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == project.id)).all()
    vids = [v.id for v in variants]
    versions = db.scalars(select(m.DesignVersion).where(m.DesignVersion.variant_id.in_(vids))).all() if vids else []
    auto = {
        "plan_and_dims": prov["plans"] > 0 and prov["control_dimensions"] > 0,
        "photos_video": prov["photos"] > 0,
        "styles_budget": bool((project.preferences or {}).get("styles")) and bool((project.preferences or {}).get("budget_amd") or (project.preferences or {}).get("budget_tier")),
        "room_list": bool(scene and scene.rooms),
    }
    manifest = [{"code": c, "auto": a, "ok": bool(auto.get(c)) if a else bool(manual.get(c))} for c, a in MANIFEST]
    # at least one product line with a confirmed, non-DEMO store price
    real = any(ln.get("price_status") == "confirmed" and not ln.get("is_demo") for ver in versions for ln in (ver.estimate or {}).get("lines", []) if ln.get("ref"))
    flow_ok = {
        "upload": prov["plans"] + prov["photos"] > 0,
        "recognition": scene is not None and bool(scene.walls),
        "confidence_review": bool(base and base.confirmed),
        "variants": bool(variants),
        "manual_edit": any(v.source in ("manual", "command") for v in versions),
        "real_products": real,
        "estimate": any(v.estimate for v in versions),
        "client_approval": _count(db, m.Approval, m.Approval.project_id == project.id, m.Approval.actor_role == "client", m.Approval.decision == "approved") > 0,
        "album": _count(db, m.Document, m.Document.project_id == project.id, m.Document.kind == "album_pdf") > 0,
        "specialist_qa": _count(db, m.AuditEvent, m.AuditEvent.project_id == project.id, m.AuditEvent.action == "trust.specialist_verified") > 0,
    }
    flow = [{"code": c, "ok": flow_ok[c]} for c in FLOW]
    done = all(i["ok"] for i in manifest) and all(s["ok"] for s in flow)
    return {"code": pilot.get("code", PILOT_CODE), "manifest": manifest, "flow": flow, "validated": done,
            "progress": round((sum(i["ok"] for i in manifest) + sum(s["ok"] for s in flow)) / (len(manifest) + len(flow)), 2),
            "updated_at": pilot.get("updated_at")}


def mark(project: m.Project, code: str, ok: bool) -> None:
    prefs = dict(project.preferences or {})
    pilot = dict(prefs.get("pilot") or {"code": PILOT_CODE})
    pilot["manual"] = {**pilot.get("manual", {}), code: ok}
    pilot["updated_at"] = datetime.now(timezone.utc).isoformat()
    prefs["pilot"] = pilot
    project.preferences = prefs  # reassign so the JSON column is flagged dirty


def ensure_workspace(db: Session) -> tuple[m.Project, bool]:
    """Idempotently create the empty N99 pilot project in the demo bureau (no fake inputs)."""
    existing = next((p for p in db.scalars(select(m.Project)) if ((p.preferences or {}).get("pilot") or {}).get("code") == PILOT_CODE), None)
    if existing:
        return existing, False
    designer = db.scalar(select(m.User).where(m.User.email == "designer@forma.local"))
    member = db.scalar(select(m.Membership).where(m.Membership.user_id == designer.id)) if designer else None
    if not designer or not member:
        raise SystemExit("seed the demo bureau first (SEED_DEMO=true)")
    proj = m.Project(org_id=member.org_id, owner_id=designer.id, title=PILOT_CODE, address="", accuracy_level="concept", status="draft",
                     designer_name=designer.name, doc_lang="hy", preferences={"pilot": {"code": PILOT_CODE, "manual": {}}})
    db.add(proj)
    db.commit()
    return proj, True
