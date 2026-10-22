"""Documents (album PDF + exports), Autodesk APS endpoints, signed file download."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..album.builder import RENDERER_VERSION
from ..aps.client import ApsError, get_aps
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..jobs.runner import enqueue, job_dict
from ..ratelimit import check as rate_check
from ..security import Principal, audit, current_principal, project_access, require
from ..storage import INLINE_EXT, LocalStorage, get_storage, media_type

router = APIRouter(tags=["documents"])
MEDIA = {"album_pdf": "application/pdf", "dxf": "application/dxf", "dwg": "image/vnd.dwg", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
         "csv": "text/csv", "glb": "model/gltf-binary", "json": "application/json"}


def doc_dict(d: m.Document) -> dict:
    return {"id": d.id, "kind": d.kind, "filename": d.filename, "size": d.size, "lang": d.lang, "status": d.status, "variant_id": d.variant_id,
            "version_id": d.version_id, "meta": d.meta, "created_at": d.created_at.isoformat(),
            "url": get_storage().signed_url(d.storage_key) if d.storage_key else None}


class AlbumIn(BaseModel):
    variant_id: str
    lang: str = Field(default="hy", pattern="^(hy|ru|en)$")
    sections: list[int] = Field(default_factory=list)


@router.post("/api/v1/projects/{pid}/documents/album")
def make_album(pid: str, body: AlbumIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rate_check(f"album:{p.user.id}", 30, 3600)
    project_access(pid, "project:read", p, db)
    v = db.get(m.DesignVariant, body.variant_id)
    if not v or v.project_id != pid:
        raise ApiError(404, "not_found")
    job = enqueue(db, "album", project_id=pid, params={"variant_id": v.id, "version_id": v.current_version_id, "lang": body.lang, "sections": body.sections},
                  idempotency_key=f"album:{RENDERER_VERSION}:{v.current_version_id}:{body.lang}:{','.join(map(str, sorted(body.sections)))}")
    audit(db, p, "document.album", "job", job.id, project_id=pid)
    db.commit()
    return job_dict(job)


@router.post("/api/v1/projects/{pid}/documents/dwg")
def make_dwg(pid: str, body: AlbumIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:read", p, db)
    from ..trust import EXPORTS

    if EXPORTS.get(proj.accuracy_level, {}).get("dwg") == "blocked":
        raise ApiError(409, "trust.requirements_missing", level="verified", export="dwg")
    if not get_settings().aps_enabled:
        raise ApiError(409, "aps.disabled")
    v = db.get(m.DesignVariant, body.variant_id)
    if not v or v.project_id != pid:
        raise ApiError(404, "not_found")
    job = enqueue(db, "aps_dwg", project_id=pid, params={"variant_id": v.id, "version_id": v.current_version_id}, idempotency_key=f"dwg:{v.current_version_id}")
    return job_dict(job)


@router.get("/api/v1/projects/{pid}/documents")
def list_documents(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    return [doc_dict(d) for d in db.scalars(select(m.Document).where(m.Document.project_id == pid).order_by(m.Document.created_at.desc()))]


@router.get("/api/v1/projects/{pid}/jobs")
def list_project_jobs(pid: str, kind: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    q = select(m.GenerationJob).where(m.GenerationJob.project_id == pid).order_by(m.GenerationJob.created_at.desc()).limit(30)
    if kind:
        q = q.where(m.GenerationJob.kind == kind)
    return [job_dict(j) for j in db.scalars(q)]


@router.get("/api/v1/files/{key:path}")
def download(key: str, exp: int, sig: str):
    if not LocalStorage.verify(key, exp, sig):
        raise ApiError(403, "file.link_expired")
    st = get_storage()
    if not st.exists(key):
        raise ApiError(404, "not_found")
    name = key.rsplit("/", 1)[-1]
    inline = name.rsplit(".", 1)[-1].lower() in INLINE_EXT
    presigned = st.presigned_get(key, name, inline)
    if presigned:  # S3/MinIO: our signature was checked; hand out a 5-minute object URL
        return RedirectResponse(presigned, status_code=302)
    return FileResponse(st.path(key), media_type=media_type(name), filename=name, content_disposition_type="inline" if inline else "attachment")


# ------------------------------------------------------------------ Autodesk APS
@router.get("/api/v1/aps/status")
def aps_status(p: Principal = Depends(current_principal)):
    s = get_settings()
    out = {"enabled": s.aps_enabled, "bucket": s.aps_bucket if s.aps_enabled else None, "region": s.aps_region,
           "design_automation_activity": get_aps().da_activity_id if s.aps_enabled else None,
           "features": {"oss_upload": s.aps_enabled, "model_derivative": s.aps_enabled, "viewer": s.aps_enabled, "design_automation_dwg": s.aps_enabled},
           "capabilities": aps_capabilities(s.aps_enabled)}
    return out


def aps_capabilities(enabled: bool) -> list[dict]:
    """Honest capability labels for RVT/IFC/DWG files shown in the import and documents UI.
    `live_verified` stays false until a real bureau RVT/IFC has been run through (P1-10)."""
    ready = "supported" if enabled else "needs_keys"
    return [
        {"key": "view", "status": ready, "formats": ["rvt", "ifc", "dwg"], "live_verified": False},
        {"key": "metadata", "status": ready, "formats": ["rvt", "ifc"], "live_verified": False},
        {"key": "editable_import", "status": "in_development", "formats": ["rvt", "ifc"], "live_verified": False},
        {"key": "ifc_export", "status": "in_development", "formats": ["ifc"], "live_verified": False},
        {"key": "dwg_export", "status": ready, "formats": ["dwg"], "live_verified": enabled},  # DXF→DWG via Design Automation, run live 2026-10-21
    ]


@router.get("/api/v1/aps/viewer-token")
def aps_viewer_token(p: Principal = Depends(current_principal)):
    try:
        return get_aps().viewer_token()
    except ApsError as e:
        raise ApiError(409, "aps.error", info=str(e)[:300]) from e


@router.post("/api/v1/aps/test")
def aps_test(p: Principal = Depends(require("sources:manage"))):
    aps = get_aps()
    try:
        aps.token()
        bucket = aps.ensure_bucket()
        return {"ok": True, "bucket": bucket}
    except ApsError as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/v1/aps/setup-design-automation")
def aps_setup(p: Principal = Depends(require("sources:manage"))):
    try:
        return get_aps().setup_design_automation()
    except ApsError as e:
        raise ApiError(502, "aps.error", info=str(e)[:300]) from e


@router.post("/api/v1/projects/{pid}/assets/{aid}/aps-translate")
def aps_translate_asset(pid: str, aid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:write", p, db)
    if not get_settings().aps_enabled:
        raise ApiError(409, "aps.disabled")
    a = db.get(m.SourceAsset, aid)
    if not a or a.project_id != pid:
        raise ApiError(404, "not_found")
    job = enqueue(db, "aps_translate", project_id=pid, params={"asset_id": aid}, idempotency_key=f"aps_translate:{aid}")
    return job_dict(job)


# ------------------------------------------------------------------ photoreal renders
class RenderIn(BaseModel):
    room_id: str
    camera_id: str | None = None


def render_dict(d: m.Document) -> dict:
    g = d.meta.get("grounding", {})
    return {"id": d.id, "room_id": d.meta.get("room_id"), "camera_id": d.meta.get("camera_id"), "url": get_storage().signed_url(d.storage_key),
            "width": d.meta.get("width"), "height": d.meta.get("height"), "model": d.meta.get("model"), "created_at": d.created_at.isoformat(),
            "parent_id": d.meta.get("parent_id"), "grounding": {"score": g.get("score"), "verified": g.get("verified"), "visual_analogs": g.get("visual_analogs", []),
                                                                "items": g.get("items", {}), "extra_objects": g.get("extra_objects", [])},
            "manifest": [{k: it.get(k) for k in ("code", "object_id", "type", "name", "sku", "supplier", "url", "color_hex", "mode")} for it in d.meta.get("manifest", [])]}


@router.post("/api/v1/projects/{pid}/variants/{vid}/renders")
def start_render(pid: str, vid: str, body: RenderIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..ai.budget import QuotaExceeded, check
    from ..render.providers import get_render_provider

    proj = project_access(pid, "project:write", p, db)
    rate_check(f"render:{p.user.id}", 30, 3600)
    v = db.get(m.DesignVariant, vid)
    if not v or v.project_id != pid:
        raise ApiError(404, "variant.not_found")
    if get_render_provider() is None:
        raise ApiError(409, "ai.unavailable", info="image provider")
    try:
        check(db, proj.org_id)
    except QuotaExceeded as e:
        raise ApiError(429, "ai.quota_exceeded", period=e.period, spent=round(e.spent, 2), limit=e.limit) from e
    job = enqueue(db, "render", project_id=pid, params={"variant_id": vid, "version_id": v.current_version_id, "room_id": body.room_id, "camera_id": body.camera_id})
    audit(db, p, "render.start", "variant", vid, project_id=pid, data={"room_id": body.room_id})
    db.commit()
    return job_dict(job)


@router.get("/api/v1/projects/{pid}/variants/{vid}/renders")
def list_renders(pid: str, vid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    v = db.get(m.DesignVariant, vid)
    if not v or v.project_id != pid:
        raise ApiError(404, "variant.not_found")
    rows = db.scalars(select(m.Document).where(m.Document.variant_id == vid, m.Document.version_id == v.current_version_id, m.Document.kind == "render")
                      .order_by(m.Document.created_at.desc()))
    return [render_dict(d) for d in rows]


class RegenIn(BaseModel):
    object_ids: list[str] = Field(min_length=1, max_length=20)
    instruction: str = Field(default="", max_length=500)


@router.post("/api/v1/projects/{pid}/renders/{did}/regenerate")
def regenerate_render(pid: str, did: str, body: RegenIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..ai.budget import QuotaExceeded, check

    proj = project_access(pid, "project:write", p, db)
    rate_check(f"render:{p.user.id}", 30, 3600)
    d = db.get(m.Document, did)
    if not d or d.project_id != pid or d.kind != "render":
        raise ApiError(404, "not_found")
    known = {it["object_id"] for it in d.meta.get("manifest", [])}
    if not set(body.object_ids) <= known:
        raise ApiError(422, "validation", fields=["object_ids"])
    try:
        check(db, proj.org_id)
    except QuotaExceeded as e:
        raise ApiError(429, "ai.quota_exceeded", period=e.period, spent=round(e.spent, 2), limit=e.limit) from e
    job = enqueue(db, "render_edit", project_id=pid, params={"document_id": did, "object_ids": body.object_ids, "instruction": body.instruction})
    audit(db, p, "render.regenerate", "document", did, project_id=pid, data={"objects": body.object_ids})
    db.commit()
    return job_dict(job)

