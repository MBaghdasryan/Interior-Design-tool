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
    files: dict = pilot.get("files", {})
    manifest = [{"code": c, "auto": a, "ok": bool(auto.get(c)) if a else bool(manual.get(c)), "files": len(files.get(c, []))} for c, a in MANIFEST]
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


def attach(project: m.Project, code: str, asset_id: str) -> None:
    prefs = dict(project.preferences or {})
    pilot = dict(prefs.get("pilot") or {"code": PILOT_CODE})
    files = {k: list(v) for k, v in (pilot.get("files") or {}).items()}
    if asset_id not in files.setdefault(code, []):
        files[code].append(asset_id)
    pilot["files"] = files
    pilot["updated_at"] = datetime.now(timezone.utc).isoformat()
    prefs["pilot"] = pilot
    project.preferences = prefs


def report(db: Session, project: m.Project) -> dict:
    """Everything a reviewer needs to judge the pilot — built from stored facts only."""
    st = status(db, project)
    pilot = (project.preferences or {}).get("pilot") or {}
    assets = {a.id: a for a in db.scalars(select(m.SourceAsset).where(m.SourceAsset.project_id == project.id))}
    for item in st["manifest"]:
        item["file_names"] = [assets[i].filename for i in pilot.get("files", {}).get(item["code"], []) if i in assets]
    base = db.scalar(select(m.BaseScene).where(m.BaseScene.project_id == project.id).order_by(m.BaseScene.version.desc()).limit(1))
    scene = Scene.model_validate(base.data) if base else None
    variants = db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == project.id)).all()
    issues: list[dict] = []
    for v in variants:
        ver = db.get(m.DesignVersion, v.current_version_id) if v.current_version_id else None
        issues += [{"variant": v.title, **i} for i in (ver.issues if ver else []) if i.get("severity") in ("block", "warning")]
    history = db.scalars(select(m.AuditEvent).where(m.AuditEvent.project_id == project.id, m.AuditEvent.action.like("pilot.%"))
                         .order_by(m.AuditEvent.created_at)).all()
    approvals = db.scalars(select(m.Approval).where(m.Approval.project_id == project.id).order_by(m.Approval.created_at)).all()
    return {
        "pilot": st["code"], "project": {"id": project.id, "title": project.title, "address": project.address, "accuracy_level": project.accuracy_level},
        "generated_at": datetime.now(timezone.utc).isoformat(), "validated": st["validated"], "progress": st["progress"],
        "manifest": st["manifest"], "flow": st["flow"],
        "assumptions": [{"key": a.key, "severity": a.severity, "text": a.text} for a in (scene.assumptions if scene else [])],
        "risks": issues[:50],
        "approvals": [{"at": a.created_at.isoformat(), "name": a.actor_name, "role": a.actor_role, "decision": a.decision} for a in approvals],
        "history": [{"at": h.created_at.isoformat(), "action": h.action, "data": h.data} for h in history],
        "statement": "validated" if st["validated"] else "real_world_validation_pending",
    }


def report_pdf(data: dict, lang: str) -> bytes:
    """A4 report rendered with the album's embedded Unicode font (Armenian/Cyrillic)."""
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas

    from .album import draw as _draw
    from .album.i18n import shared

    def T(key: str, **kw) -> str:
        return shared(key, lang, **kw)

    _draw.ensure_fonts()
    buf = io.BytesIO()
    c = Canvas(buf, pagesize=A4, initialFontName=_draw.FONT)
    c.setTitle(f"{data['pilot']} — {T('pilot.report_title')}")
    w, h = A4
    y = h - 20 * mm

    def line(text: str, size: float = 9.5, bold: bool = False, indent: float = 0) -> None:
        nonlocal y
        for part in _draw.wrap(text, w - 36 * mm - indent, size) or [""]:
            if y < 20 * mm:
                c.showPage()
                y = h - 20 * mm
            c.setFont(_draw.FONT_B if bold else _draw.FONT, size)
            c.drawString(18 * mm + indent, y, part)
            y -= size * 0.5 * mm + 2.2 * mm

    mark = lambda ok: "✔" if ok else "○"  # noqa: E731
    line(f"{data['pilot']} — {T('pilot.report_title')}", 15, True)
    line(f"{data['project']['title']} · {data['generated_at'][:16].replace('T', ' ')} UTC", 9)
    line(T("pilot.validated") if data["validated"] else T("pilot.not_validated"), 11, True)
    line(T("pilot.progress", pct=round(data["progress"] * 100)), 9)
    y -= 3 * mm
    line(T("pilot.manifest"), 11, True)
    for i in data["manifest"]:
        files = f" — {', '.join(i['file_names'][:3])}" if i.get("file_names") else ""
        line(f"{mark(i['ok'])}  {T('pilot.item.' + i['code'])}{' (' + T('pilot.auto') + ')' if i['auto'] else ''}{files}", indent=3 * mm)
    y -= 3 * mm
    line(T("pilot.flow"), 11, True)
    for s in data["flow"]:
        line(f"{mark(s['ok'])}  {T('pilot.stage.' + s['code'])}", indent=3 * mm)
    y -= 3 * mm
    line(T("pilot.assumptions"), 11, True)
    for a in data["assumptions"][:30]:
        line(f"[{a['severity']}] {a['text']}", 8.5, indent=3 * mm)
    for r in data["risks"][:20]:
        line(f"[{r.get('severity')}] {r.get('variant', '')}: {r.get('message', '')}", 8.5, indent=3 * mm)
    if not data["assumptions"] and not data["risks"]:
        line("—", 8.5, indent=3 * mm)
    y -= 3 * mm
    line(T("pilot.approvals"), 11, True)
    for a in data["approvals"]:
        line(f"{a['at'][:16].replace('T', ' ')} {a['name']} ({a['role']}) — {a['decision']}", 8.5, indent=3 * mm)
    if not data["approvals"]:
        line("—", 8.5, indent=3 * mm)
    y -= 4 * mm
    line(T("pilot.report_disclaimer"), 8)
    c.save()
    return buf.getvalue()


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
