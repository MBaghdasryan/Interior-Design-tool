"""Projects: intake, geometry review, AI generation, variants, versions,
AI change commands, manual refinement, approvals."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from .. import models as m
from ..ai.budget import QuotaExceeded
from ..ai.orchestrator import get_orchestrator
from ..ai.providers import ProviderError
from ..ai.schemas import ChangePlan
from ..catalog.candidates import resolve
from ..db import SessionLocal, get_db
from ..design.changes import _latest_snapshot, apply_plan, scene_diff
from ..design.engine import candidate_pools, rank
from ..errors import ApiError
from ..jobs.pipeline import latest_base
from ..jobs.runner import enqueue, job_dict
from ..pagination import page
from ..ratelimit import check as rate_check
from ..scene.geometry import footprint, room_area_m2, scale_scene, wall_length
from ..scene.model import ControlDimension, Scene, SceneObject
from ..scene.recognize import confidence_mask, overall_confidence
from ..scene.rules import run_rules, summarize
from ..scene.svg import render_svg
from ..security import Principal, audit, current_principal, project_access
from ..services import new_version, project_dict, variant_dict, version_dict
from ..storage import MAX_UPLOAD_BYTES, ScanUnavailable, detect_kind, get_storage, scan_upload

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class ProjectIn(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    address: str = ""
    city: str = "Ереван"
    property_type: str = "apartment"
    area_m2: float | None = None
    renovation_stage: str = "shell"
    client_name: str = ""
    doc_lang: str = "hy"


class ProjectPatch(BaseModel):
    title: str | None = None
    address: str | None = None
    client_name: str | None = None
    preferences: dict | None = None
    product_source: str | None = None
    external_settings: dict | None = None
    doc_lang: str | None = None
    accuracy_level: str | None = None


def _cover(db: Session, pid: str) -> str | None:
    """Card image: the latest photoreal render, else the first uploaded room photo."""
    key = db.scalar(select(m.Document.storage_key).where(m.Document.project_id == pid, m.Document.kind == "render").order_by(m.Document.created_at.desc()).limit(1))
    if not key:
        key = db.scalar(select(m.SourceAsset.storage_key).where(m.SourceAsset.project_id == pid, m.SourceAsset.mime.like("image/%"),
                                                                m.SourceAsset.scan_status != "purged").order_by(m.SourceAsset.created_at).limit(1))
    return get_storage().signed_url(key) if key else None


@router.get("")
def list_projects(response: Response, cursor: str | None = None, limit: int = Query(200, ge=1, le=500),
                  p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    q = select(m.Project)
    if not p.is_platform_admin:  # the catalogue operator does not see client projects
        q = q.where(m.Project.org_id.in_(p.org_ids))
    rows, _ = page(db, q, m.Project.updated_at, m.Project.id, cursor=cursor, limit=limit, response=response)
    out = []
    for proj in rows:
        d = project_dict(proj)
        vs = db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == proj.id, m.DesignVariant.status != "archived")).all()
        d["variants"] = len(vs)
        d["total"] = next((v.metrics.get("total") for v in vs if v.status in ("selected", "approved")), None)
        d["cover"] = _cover(db, proj.id)
        out.append(d)
    return out


@router.post("")
def create_project(body: ProjectIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org_id = next((oid for oid, roles in p.roles.items() if roles & {"designer", "bureau_admin", "platform_admin"}), None)
    if not org_id:
        raise ApiError(403, "auth.no_org")
    from ..commerce.tariffs import check_project_quota

    check_project_quota(db, org_id)
    proj = m.Project(org_id=org_id, owner_id=p.user.id, designer_name=p.user.name if "designer" in p.all_roles() else "", **body.model_dump())
    db.add(proj)
    db.flush()
    audit(db, p, "project.create", "project", proj.id, project_id=proj.id, org_id=org_id)
    db.commit()
    return project_dict(proj)


@router.get("/{pid}")
def get_project(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:read", p, db)
    d = project_dict(proj)
    d["assets"] = [asset_dict(a) for a in db.scalars(select(m.SourceAsset).where(m.SourceAsset.project_id == pid).order_by(m.SourceAsset.created_at))]
    base = latest_base(db, pid)
    d["base_scene"] = {"version": base.version, "confirmed": base.confirmed} if base else None
    d["variants"] = [variant_dict(v) for v in db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == pid, m.DesignVariant.status != "archived").order_by(m.DesignVariant.created_at))]
    last_job = db.scalar(select(m.GenerationJob).where(m.GenerationJob.project_id == pid, m.GenerationJob.kind == "pipeline").order_by(m.GenerationJob.created_at.desc()).limit(1))
    d["last_pipeline_job"] = job_dict(last_job) if last_job else None
    return d


@router.patch("/{pid}")
def patch_project(pid: str, body: ProjectPatch, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    data = body.model_dump(exclude_none=True)
    if "product_source" in data and data["product_source"] not in ("external", "own", "concept"):
        raise ApiError(422, "validation", fields=["product_source"])
    if "accuracy_level" in data:
        if data["accuracy_level"] == "production" and not p.can("project:verify", proj.org_id):
            raise ApiError(403, "auth.production_level_requires_verifier")
    for k, v in data.items():
        setattr(proj, k, v)
    audit(db, p, "project.update", "project", pid, project_id=pid, data={"fields": list(data)})
    db.commit()
    return project_dict(proj)


@router.delete("/{pid}")
def delete_project(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Deletes a project with its files. Refused once an order left the cart: orders and the ledger keep their history."""
    proj = project_access(pid, "project:write", p, db)
    if db.scalar(select(m.Order.id).where(m.Order.project_id == pid, m.Order.status != "cart").limit(1)):
        raise ApiError(409, "project.has_orders")
    st = get_storage()
    for key, _ in st.list(f"projects/{pid}/"):
        st.delete(key)
    audit(db, p, "project.delete", "project", pid, org_id=proj.org_id, data={"title": proj.title})
    db.delete(proj)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ intake
def asset_dict(a: m.SourceAsset) -> dict:
    return {"id": a.id, "kind": a.kind, "filename": a.filename, "mime": a.mime, "size": a.size, "room_hint": a.room_hint, "quality": a.quality,
            "aps": {k: v for k, v in (a.aps or {}).items() if k in ("status", "progress", "urn", "rooms")},
            "url": get_storage().signed_url(a.storage_key) if a.scan_status != "purged" else None, "scan_status": a.scan_status,
            "created_at": a.created_at.isoformat()}


def assess_quality(kind: str, data: bytes) -> dict:
    warnings = []
    info: dict = {}
    if kind in ("photo", "plan_image"):
        try:
            import io

            from PIL import Image

            im = Image.open(io.BytesIO(data))
            info["width"], info["height"] = im.size
            if min(im.size) < 900:
                warnings.append("Низкое разрешение (<900 px) — распознавание может быть неточным")
            gray = im.convert("L").resize((64, 64))
            px = list(gray.getdata())
            mean = sum(px) / len(px)
            info["brightness"] = round(mean)
            if mean < 60:
                warnings.append("Слишком тёмное изображение")
        except Exception:  # noqa: BLE001
            warnings.append("Не удалось прочитать изображение")
    if kind == "video" and len(data) < 200_000:
        warnings.append("Очень короткое видео — снимите медленный обход всех стен")
    return {"warnings": warnings, **info}


@router.post("/{pid}/assets")
async def upload_asset(pid: str, file: UploadFile = File(...), room_hint: str | None = Form(None), manifest_item: str | None = Form(None),
                       p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    data = await file.read()
    return _ingest(db, p, proj, data, file.filename or "file", file.content_type or "", room_hint, manifest_item)


def _ingest(db: Session, p: Principal, proj: m.Project, data: bytes, filename: str, content_type: str, room_hint: str | None,
            manifest_item: str | None, incoming_key: str | None = None) -> dict:
    """Validates and stores an upload (multipart or a completed presigned upload): size,
    extension vs. magic bytes, malware scan, de-duplication by SHA-256."""
    st = get_storage()
    try:
        if len(data) > MAX_UPLOAD_BYTES:
            raise ApiError(413, "file.too_large")
        if not data:
            raise ApiError(422, "file.empty")
        kind = detect_kind(filename, content_type, data[:16])
        if not kind:
            raise ApiError(415, "file.unsupported")
        try:
            scan, signature = scan_upload(data)
        except ScanUnavailable:
            raise ApiError(503, "file.scan_unavailable") from None
        if scan == "infected":
            # quarantine: kept out of the project, never served, removed by retention; reviewed by platform admins
            qkey = f"quarantine/{proj.id}/{hashlib.sha256(data).hexdigest()[:16]}_{filename.replace('/', '_')[-80:]}"
            st.put(qkey, data)
            audit(db, p, "asset.quarantined", "asset", None, project_id=proj.id,
                  data={"filename": filename, "sha256": hashlib.sha256(data).hexdigest(), "signature": signature, "key": qkey})
            db.commit()
            raise ApiError(422, "file.malware", signature=signature)
    except ApiError:
        if incoming_key:
            st.delete(incoming_key)  # rejected presigned uploads never leave quarantine
        raise
    sha = hashlib.sha256(data).hexdigest()
    dup = db.scalar(select(m.SourceAsset).where(m.SourceAsset.project_id == proj.id, m.SourceAsset.sha256 == sha))
    if dup:
        if incoming_key:
            st.delete(incoming_key)
        _attach_to_pilot(proj, manifest_item, dup.id)
        db.commit()
        return asset_dict(dup)
    key = f"projects/{proj.id}/assets/{sha[:16]}_{filename.replace('/', '_')[-80:]}"
    if incoming_key:
        st.move(incoming_key, key)
    else:
        st.put(key, data, content_type or "application/octet-stream")
    a = m.SourceAsset(project_id=proj.id, kind=kind, filename=filename, mime=content_type or "application/octet-stream", size=len(data), sha256=sha,
                      storage_key=key, room_hint=room_hint, quality=assess_quality(kind, data), scan_status=scan)
    db.add(a)
    db.flush()
    _attach_to_pilot(proj, manifest_item, a.id)
    if proj.status == "draft":
        proj.status = "intake"
    audit(db, p, "asset.upload", "asset", None, project_id=proj.id, data={"filename": a.filename, "kind": kind, "size": len(data), "via": "presigned" if incoming_key else "api"})
    db.commit()
    if kind in ("dwg", "rvt", "ifc"):
        from ..config import get_settings

        if get_settings().aps_enabled:
            enqueue(db, "aps_translate", project_id=proj.id, params={"asset_id": a.id}, idempotency_key=f"aps_translate:{a.id}")
    return asset_dict(a)


class PresignIn(BaseModel):
    filename: str = Field(min_length=1, max_length=300)
    size: int = Field(gt=0)
    content_type: str = Field(default="application/octet-stream", max_length=100)


@router.post("/{pid}/assets/presign")
def presign_upload(pid: str, body: PresignIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Direct-to-storage upload (S3/MinIO): returns a 15-minute PUT URL into a per-project
    quarantine prefix. With local storage the client falls back to multipart upload."""
    from ..storage import EXT_KIND

    project_access(pid, "project:write", p, db)
    if body.size > MAX_UPLOAD_BYTES:
        raise ApiError(413, "file.too_large")
    ext = "." + body.filename.rsplit(".", 1)[-1].lower() if "." in body.filename else ""
    if ext not in EXT_KIND:
        raise ApiError(415, "file.unsupported")
    key = f"incoming/{pid}/{secrets.token_hex(8)}_{body.filename.replace('/', '_')[-80:]}"
    url = get_storage().presigned_put(key, body.content_type)
    if not url:
        return {"mode": "multipart"}
    return {"mode": "presigned", "url": url, "key": key, "headers": {"Content-Type": body.content_type,
                                                                      **({"x-amz-server-side-encryption": get_storage().sse} if getattr(get_storage(), "sse", None) else {})}}


class CompleteIn(BaseModel):
    key: str = Field(max_length=400)
    filename: str = Field(min_length=1, max_length=300)
    content_type: str = Field(default="application/octet-stream", max_length=100)
    room_hint: str | None = None
    manifest_item: str | None = None


@router.post("/{pid}/assets/complete")
def complete_upload(pid: str, body: CompleteIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    if not body.key.startswith(f"incoming/{pid}/") or ".." in body.key:
        raise ApiError(422, "validation", fields=["key"])  # only this project's quarantine
    st = get_storage()
    if not st.exists(body.key):
        raise ApiError(404, "not_found")
    return _ingest(db, p, proj, st.get(body.key), body.filename, body.content_type, body.room_hint, body.manifest_item, incoming_key=body.key)


def _attach_to_pilot(proj: m.Project, manifest_item: str | None, asset_id: str) -> None:
    """Pilot projects (N99) file uploads under a manifest item; ordinary projects ignore the field."""
    if not manifest_item or not (proj.preferences or {}).get("pilot"):
        return
    from ..pilot import MANIFEST, attach

    if manifest_item not in {c for c, _ in MANIFEST}:
        raise ApiError(422, "validation", fields=["manifest_item"])
    attach(proj, manifest_item, asset_id)


@router.delete("/{pid}/assets/{aid}")
def delete_asset(pid: str, aid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:write", p, db)
    a = db.get(m.SourceAsset, aid)
    if not a or a.project_id != pid:
        raise ApiError(404, "not_found")
    db.delete(a)
    audit(db, p, "asset.delete", "asset", aid, project_id=pid)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ geometry
@router.post("/{pid}/recognize")
def start_recognition(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rate_check(f"recognize:{p.user.id}", 20, 3600)
    project_access(pid, "project:write", p, db)
    job = enqueue(db, "recognize", project_id=pid, params={})
    return job_dict(job)


@router.post("/{pid}/use-demo-geometry")
def use_demo_geometry(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Development helper: seeds the synthetic demo apartment as a draft geometry."""
    proj = project_access(pid, "project:write", p, db)
    from ..scene.demo import demo_base_scene

    last = latest_base(db, pid)
    sc = demo_base_scene()
    db.add(m.BaseScene(project_id=pid, version=(last.version + 1) if last else 1, data=sc.model_dump(mode="json"), confirmed=False))
    proj.confidence = overall_confidence(sc)
    proj.area_m2 = round(sum(room_area_m2(r) for r in sc.rooms if r.type != "balcony"), 1)
    db.commit()
    return {"ok": True}


@router.get("/{pid}/geometry")
def get_geometry(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:read", p, db)
    base = latest_base(db, pid)
    if not base:
        return {"scene": None}
    sc = Scene.model_validate(base.data)
    return {"version": base.version, "confirmed": base.confirmed, "scene": base.data, "mask": confidence_mask(sc), "confidence": proj.confidence,
            "accuracy_level": proj.accuracy_level, "rooms": [{"id": r.id, "area_m2": room_area_m2(r)} for r in sc.rooms],
            "checks": [i for i in run_rules(sc, {}, only=["structure"]) if i["severity"] != "pass"]}


class GeometryIn(BaseModel):
    scene: dict


@router.put("/{pid}/geometry")
def save_geometry(pid: str, body: GeometryIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    sc = Scene.model_validate(body.scene)
    last = latest_base(db, pid)
    row = m.BaseScene(project_id=pid, version=(last.version + 1) if last else 1, data=sc.model_dump(mode="json"), confirmed=False)
    db.add(row)
    proj.confidence = overall_confidence(sc)
    audit(db, p, "geometry.edit", "base_scene", None, project_id=pid)
    db.commit()
    return {"version": row.version, "confidence": proj.confidence, "mask": confidence_mask(sc)}


class ControlDimIn(BaseModel):
    wall_id: str
    measured_mm: float = Field(gt=300, lt=50000)
    rescale: bool = True


@router.post("/{pid}/geometry/control-dimension")
def control_dimension(pid: str, body: ControlDimIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Sets a verified dimension; optionally rescales the whole plan so that the wall matches."""
    proj = project_access(pid, "project:write", p, db)
    base = latest_base(db, pid)
    if not base:
        raise ApiError(409, "geometry.missing")
    sc = Scene.model_validate(base.data)
    w = sc.wall(body.wall_id)
    if not w:
        raise ApiError(404, "wall.not_found")
    factor = body.measured_mm / wall_length(w)
    if body.rescale and abs(factor - 1) > 0.002:
        sc = scale_scene(sc, factor)
    sc.control_dimensions = [cd for cd in sc.control_dimensions if cd.wall_id != body.wall_id] + [ControlDimension(wall_id=body.wall_id, measured_mm=body.measured_mm)]
    for x in sc.walls:
        if x.id == body.wall_id:
            x.source, x.confidence = "measured", 1.0
    sc.assumptions = [a for a in sc.assumptions if a.key != "scale"]
    row = m.BaseScene(project_id=pid, version=base.version + 1, data=sc.model_dump(mode="json"), confirmed=False)
    db.add(row)
    db.add(m.Measurement(project_id=pid, wall_id=body.wall_id, measured_mm=body.measured_mm, confirmed_by=p.user.id, note=f"scale factor {factor:.4f}"))
    proj.confidence = overall_confidence(sc)
    prefs = dict(proj.preferences or {})
    prefs["control_dimension"] = {"wall_id": body.wall_id, "measured_mm": body.measured_mm}
    proj.preferences = prefs
    db.commit()
    return {"factor": round(factor, 4), "version": row.version, "confidence": proj.confidence}


@router.post("/{pid}/geometry/confirm")
def confirm_geometry(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    base = latest_base(db, pid)
    if not base:
        raise ApiError(409, "geometry.missing")
    sc = Scene.model_validate(base.data)
    if not sc.rooms:
        raise ApiError(422, "geometry.no_rooms")
    base.confirmed = True
    proj.status = "recognized"
    proj.area_m2 = round(sum(room_area_m2(r) for r in sc.rooms if r.type != "balcony"), 1)
    if proj.accuracy_level == "concept" and sc.control_dimensions:
        proj.accuracy_level = "verified"
    audit(db, p, "geometry.confirm", "base_scene", base.id, project_id=pid, data={"version": base.version})
    db.commit()
    return {"ok": True, "accuracy_level": proj.accuracy_level, "area_m2": proj.area_m2}


@router.get("/{pid}/plan.svg")
def plan_svg(pid: str, variant_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    if variant_id:
        v = db.get(m.DesignVariant, variant_id)
        if not v or v.project_id != pid:
            raise ApiError(404, "not_found")
        ver = db.get(m.DesignVersion, v.current_version_id)
        svg = render_svg(Scene.model_validate(ver.scene), show_issues=ver.issues)
    else:
        base = latest_base(db, pid)
        if not base:
            raise ApiError(404, "not_found")
        svg = render_svg(Scene.model_validate(base.data), show_objects=False, layers={"rooms", "walls", "openings", "labels", "fixtures", "demolition"})
    return Response(svg, media_type="image/svg+xml")


# ------------------------------------------------------------------ preferences & generation
class GenerateIn(BaseModel):
    preferences: dict = Field(default_factory=dict)
    product_source: str = "external"
    external_settings: dict = Field(default_factory=dict)
    idempotency_key: str | None = None


@router.post("/{pid}/generate")
def generate(pid: str, body: GenerateIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rate_check(f"generate:{p.user.id}", 20, 3600)
    proj = project_access(pid, "project:write", p, db)
    base = latest_base(db, pid)
    if not base:
        raise ApiError(409, "geometry.required_for_generation")
    if body.product_source not in ("external", "own", "concept"):
        raise ApiError(422, "validation", fields=["product_source"])
    if body.product_source == "own":
        has_own = db.scalar(select(m.Product.id).where(m.Product.is_demo.is_(False)).limit(1))
        if not has_own:
            raise ApiError(409, "catalog.own_empty")
    proj.preferences = {**(proj.preferences or {}), **body.preferences}
    proj.product_source = body.product_source
    proj.external_settings = body.external_settings or proj.external_settings
    proj.status = "generating"
    db.commit()
    job = enqueue(db, "pipeline", project_id=pid, params={"base_version": base.version}, idempotency_key=body.idempotency_key)
    audit(db, p, "pipeline.start", "job", job.id, project_id=pid, data={"source": body.product_source})
    db.commit()
    return job_dict(job)


@router.get("/{pid}/jobs/{jid}")
def get_job(pid: str, jid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    job = db.get(m.GenerationJob, jid)
    if not job or job.project_id != pid:
        raise ApiError(404, "not_found")
    return job_dict(job)


@router.get("/{pid}/jobs/{jid}/events")
async def job_events(pid: str, jid: str, request: Request, authorization: str | None = Header(default=None)):
    """SSE progress stream. The browser's EventSource sends the HttpOnly session cookie;
    API clients may use `Authorization: Bearer`. Tokens are never put in the URL."""
    from ..security import SESSION_COOKIE, principal_from_token

    bearer = authorization.split(" ", 1)[1] if authorization and authorization.lower().startswith("bearer ") else None
    db = SessionLocal()
    try:
        project_access(pid, "project:read", principal_from_token(bearer or request.cookies.get(SESSION_COOKIE), db), db)
        job = db.get(m.GenerationJob, jid)
        if not job or job.project_id != pid:  # a job of another project is never streamed
            raise ApiError(404, "not_found")
    finally:
        db.close()

    async def gen():
        # resumable stream: every event carries an id (hash of the job state); after a reconnect the
        # browser sends Last-Event-ID and an unchanged state is not re-sent
        last = request.headers.get("last-event-id")
        yield {"event": "hello", "data": "", "retry": 3000}  # reconnect delay hint for EventSource
        while True:
            if await request.is_disconnected():
                break
            s = SessionLocal()
            try:
                job = s.get(m.GenerationJob, jid)
                payload = json.dumps(job_dict(job), ensure_ascii=False) if job else None
                status = job.status if job else "missing"
            finally:
                s.close()
            eid = hashlib.sha1((payload or "").encode()).hexdigest()[:16]
            if eid != last:
                last = eid
                yield {"event": "progress", "data": payload or "{}", "id": eid}
            if status in ("succeeded", "failed", "missing"):
                yield {"event": "end", "data": status}
                break
            await asyncio.sleep(0.7)

    return EventSourceResponse(gen())


@router.post("/{pid}/jobs/{jid}/retry")
def retry_job(pid: str, jid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:write", p, db)
    job = db.get(m.GenerationJob, jid)
    if not job or job.project_id != pid or job.status != "failed":
        raise ApiError(409, "job.retry_only_failed")
    job.status, job.error = "queued", None
    for s in job.steps:
        if s.status in ("failed", "running", "pending"):
            s.status, s.detail = "pending", ""
    db.commit()
    from ..jobs.runner import submit

    submit(job.id)
    return job_dict(job)


# ------------------------------------------------------------------ variants & versions
def _variant(db: Session, pid: str, vid: str) -> m.DesignVariant:
    v = db.get(m.DesignVariant, vid)
    if not v or v.project_id != pid:
        raise ApiError(404, "variant.not_found")
    return v


@router.get("/{pid}/variants")
def list_variants(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    return [variant_dict(v) for v in db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == pid, m.DesignVariant.status != "archived").order_by(m.DesignVariant.created_at))]


@router.get("/{pid}/variants/{vid}")
def get_variant(pid: str, vid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    v = _variant(db, pid, vid)
    return variant_dict(v, db.get(m.DesignVersion, v.current_version_id))


@router.post("/{pid}/variants/{vid}/select")
def select_variant(pid: str, vid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:write", p, db)
    for v in db.scalars(select(m.DesignVariant).where(m.DesignVariant.project_id == pid, m.DesignVariant.status == "selected")):
        v.status = "draft"
    v = _variant(db, pid, vid)
    if v.status != "approved":
        v.status = "selected"
    db.commit()
    return variant_dict(v)


@router.get("/{pid}/variants/{vid}/versions")
def list_versions(pid: str, vid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    _variant(db, pid, vid)
    return [version_dict(x, full=False) for x in db.scalars(select(m.DesignVersion).where(m.DesignVersion.variant_id == vid).order_by(m.DesignVersion.number.desc()))]


@router.get("/{pid}/variants/{vid}/versions/{ver_id}")
def get_version(pid: str, vid: str, ver_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    _variant(db, pid, vid)  # the variant must belong to this project (tenant isolation)
    ver = db.get(m.DesignVersion, ver_id)
    if not ver or ver.variant_id != vid:
        raise ApiError(404, "not_found")
    return version_dict(ver)


@router.get("/{pid}/variants/{vid}/compare")
def compare_versions(pid: str, vid: str, a: str, b: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    _variant(db, pid, vid)
    va, vb = db.get(m.DesignVersion, a), db.get(m.DesignVersion, b)
    if not va or not vb or va.variant_id != vid or vb.variant_id != vid:
        raise ApiError(404, "not_found")
    return scene_diff(Scene.model_validate(va.scene), Scene.model_validate(vb.scene), va.estimate or {}, vb.estimate or {})


@router.post("/{pid}/variants/{vid}/versions/{ver_id}/restore")
def restore_version(pid: str, vid: str, ver_id: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    v = _variant(db, pid, vid)
    old = db.get(m.DesignVersion, ver_id)
    if not old or old.variant_id != vid:
        raise ApiError(404, "not_found")
    sc = Scene.model_validate(old.scene)
    cs = old.change_summary or {}
    ver = new_version(db, proj, v, sc, selection=cs.get("selection", {}), extras=cs.get("extras"), source="restore", note=f"Восстановлено из версии {old.number}", user_id=p.user.id)
    db.commit()
    return version_dict(ver)


# ------------------------------------------------------------------ AI change commands
class CommandIn(BaseModel):
    command: str = Field(min_length=3, max_length=1000)
    apply: bool = False
    plan: dict | None = None  # the previewed plan, to apply exactly what the user saw


@router.post("/{pid}/variants/{vid}/command")
def change_command(pid: str, vid: str, body: CommandIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rate_check(f"command:{p.user.id}", 60, 3600)
    proj = project_access(pid, "project:write", p, db)
    v = _variant(db, pid, vid)
    ver = db.get(m.DesignVersion, v.current_version_id)
    base_row = latest_base(db, pid)
    base = Scene.model_validate(base_row.data)
    sc = Scene.model_validate(ver.scene)
    if body.plan:
        plan = ChangePlan.model_validate(body.plan)
        provider = "preview"
    else:
        ctx = {"command": body.command, "room_types": sorted({r.type for r in sc.rooms}), "rooms": [{"id": r.id, "type": r.type, "name": r.name} for r in sc.rooms],
               "categories": sorted({o.category for o in sc.objects}), "locked": [o.id for o in sc.objects if o.locked]}
        try:
            plan, provider = get_orchestrator().run("change_command", ctx, db=db, project_id=pid)
        except QuotaExceeded as e:
            raise ApiError(429, "ai.quota_exceeded", period=e.period, spent=round(e.spent, 2), limit=e.limit) from e
        except ProviderError as e:
            raise ApiError(502, "ai.unavailable", info=str(e)[:300]) from e
    res = apply_plan(db, proj, v, ver, base, plan)
    result = res["result"]
    out = {"plan": plan.model_dump(), "provider": provider, "applied": res["applied"], "skipped": res["skipped"], "diff": res["diff"],
           "total_after": result.estimate["totals"]["known"], "issues_after": summarize(result.issues)}
    if body.apply:
        new = new_version(db, proj, v, result.scene, selection=result.selection, extras=res["extras"], source="command", note=body.command, user_id=p.user.id,
                          diff=res["diff"], estimate_override=result.estimate, issues_override=result.issues)
        if res["style"] != v.style:
            v.style = res["style"]
        audit(db, p, "variant.command", "version", new.id, project_id=pid, data={"command": body.command, "applied": len(res["applied"])})
        db.commit()
        out["version"] = version_dict(new, full=False)
    else:
        db.commit()
    return out


# ------------------------------------------------------------------ manual refinement
class ObjectsPatch(BaseModel):
    objects: list[dict]
    note: str = "Ручное редактирование"


@router.put("/{pid}/variants/{vid}/objects")
def save_objects(pid: str, vid: str, body: ObjectsPatch, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Manual edit (move/rotate/lock/remove). Every save is a new version; rules and estimate are recomputed."""
    proj = project_access(pid, "project:write", p, db)
    v = _variant(db, pid, vid)
    ver = db.get(m.DesignVersion, v.current_version_id)
    sc = Scene.model_validate(ver.scene)
    old = sc.model_copy(deep=True)
    sc.objects = [SceneObject.model_validate(o) for o in body.objects]
    for o in sc.objects:
        o.source = "manual" if o.source != "manual" else o.source
    from ..scene.layout import _electrical  # sockets follow furniture

    _electrical(sc)
    cs = ver.change_summary or {}
    new = new_version(db, proj, v, sc, selection=cs.get("selection", {}), extras=cs.get("extras"), source="manual", note=body.note, user_id=p.user.id)
    new.change_summary = {**new.change_summary, "diff": scene_diff(old, sc, ver.estimate or {}, new.estimate)}
    audit(db, p, "variant.manual_edit", "version", new.id, project_id=pid)
    db.commit()
    return version_dict(new)


@router.get("/{pid}/variants/{vid}/objects/{oid}/alternatives")
def alternatives(pid: str, vid: str, oid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:read", p, db)
    v = _variant(db, pid, vid)
    ver = db.get(m.DesignVersion, v.current_version_id)
    sc = Scene.model_validate(ver.scene)
    o = next((x for x in sc.objects if x.id == oid), None)
    if not o:
        raise ApiError(404, "not_found")
    primary, fallback = candidate_pools(db, proj, _latest_snapshot(db, proj))
    pool = (primary.get(o.category) or []) + (fallback.get(o.category) or [])
    ranked = rank(pool, cat=o.category, style=v.style, tier=v.tier, max_width=None)
    cur = resolve(db, o.product_variant_id) if o.product_variant_id else None
    out = []
    for c in ranked[:12]:
        d = c.dict()
        d["delta_amd"] = (c.price_amd - cur.price_amd) if (cur and cur.price_amd is not None and c.price_amd is not None) else None
        d["current"] = c.ref == o.product_variant_id
        d["fits"] = True
        if c.w and c.d and (c.w > o.w + 1 or c.d > o.d + 1):
            test = o.model_copy(update={"w": c.w, "d": c.d, "h": c.h or o.h})
            room = sc.room(o.room_id)
            from ..scene.geometry import rect_inside_polygon

            d["fits"] = bool(room and rect_inside_polygon(footprint(test), room.polygon)) and not any(
                footprint(test).overlaps(footprint(x)) for x in sc.objects if x.id != o.id and x.room_id == o.room_id and x.category not in ("rug",))
        out.append(d)
    return {"object": o.model_dump(), "current": cur.dict() if cur else None, "alternatives": out}


class ReplaceIn(BaseModel):
    ref: str


@router.post("/{pid}/variants/{vid}/objects/{oid}/replace")
def replace_object(pid: str, vid: str, oid: str, body: ReplaceIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    v = _variant(db, pid, vid)
    ver = db.get(m.DesignVersion, v.current_version_id)
    sc = Scene.model_validate(ver.scene)
    old = sc.model_copy(deep=True)
    c = resolve(db, body.ref)
    if not c:
        raise ApiError(404, "product.not_found")
    o = next((x for x in sc.objects if x.id == oid), None)
    if not o or c.category != o.category:
        raise ApiError(422, "catalog.same_category_only")
    o.product_variant_id, o.name, o.color_hex = c.ref, c.name, c.color_hex
    if c.w and c.d:
        o.w, o.d, o.h = c.w, c.d, c.h or o.h
    cs = dict(ver.change_summary or {})
    sel = json.loads(json.dumps(cs.get("selection", {})))
    sel.setdefault(o.room_id, {})[o.category] = [c.ref] + [r for r in sel.get(o.room_id, {}).get(o.category, []) if r != c.ref]
    new = new_version(db, proj, v, sc, selection=sel, extras=cs.get("extras"), source="manual", note=f"Замена {o.code}: {c.name}", user_id=p.user.id)
    new.change_summary = {**new.change_summary, "diff": scene_diff(old, sc, ver.estimate or {}, new.estimate)}
    db.commit()
    return version_dict(new)


# ------------------------------------------------------------------ approval
class ApproveIn(BaseModel):
    decision: str = "approved"  # approved | rejected | changes_requested
    note: str = ""


@router.post("/{pid}/variants/{vid}/approve")
def approve(pid: str, vid: str, body: ApproveIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:approve", p, db)
    v = _variant(db, pid, vid)
    ver = db.get(m.DesignVersion, v.current_version_id)
    if body.decision not in ("approved", "rejected", "changes_requested"):
        raise HTTPException(422)
    issues = summarize(ver.issues or [])
    if body.decision == "approved" and issues["block"]:
        raise ApiError(409, "variant.blocking_issues", count=issues["block"])
    snap = None
    if body.decision == "approved":
        # price snapshot so later price changes never rewrite the approved estimate
        snap = m.EstimateSnapshot(project_id=pid, variant_id=vid, version_id=ver.id, reason="approval", data=ver.estimate)
        db.add(snap)
        db.flush()
        ver.frozen = True
        v.status = "approved"
        proj.status = "approved"
    role = next(iter(p.all_roles() & {"client", "designer", "bureau_admin", "platform_admin"}), "user")
    db.add(m.Approval(project_id=pid, variant_id=vid, version_id=ver.id, actor_name=p.user.name, actor_role=role, decision=body.decision, note=body.note,
                      estimate_snapshot_id=snap.id if snap else None))
    audit(db, p, f"variant.{body.decision}", "variant", vid, project_id=pid, data={"version": ver.number})
    db.commit()
    warn = []
    if proj.accuracy_level != "production" and any((o.get("custom_product") or {}).get("made_to_measure") for o in (ver.scene or {}).get("objects", [])):
        warn.append("Есть изделия по размерам: перед заказом требуется верификация обмеров (Production Ready)")
    return {"variant": variant_dict(v), "estimate_snapshot_id": snap.id if snap else None, "warnings": warn}


@router.post("/{pid}/variants/{vid}/unapprove")
def unapprove(pid: str, vid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:approve", p, db)
    v = _variant(db, pid, vid)
    v.status = "selected"
    proj.status = "ready"
    audit(db, p, "variant.unapprove", "variant", vid, project_id=pid)
    db.commit()
    return variant_dict(v)


# ------------------------------------------------------------------ comments
class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    variant_id: str | None = None
    anchor: dict = Field(default_factory=dict)


@router.get("/{pid}/comments")
def list_comments(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    return [comment_dict(c) for c in db.scalars(select(m.Comment).where(m.Comment.project_id == pid).order_by(m.Comment.created_at))]


def comment_dict(c: m.Comment) -> dict:
    return {"id": c.id, "body": c.body, "author_name": c.author_name, "variant_id": c.variant_id, "anchor": c.anchor, "resolved": c.resolved, "created_at": c.created_at.isoformat()}


@router.post("/{pid}/comments")
def add_comment(pid: str, body: CommentIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    c = m.Comment(project_id=pid, variant_id=body.variant_id, author_id=p.user.id, author_name=p.user.name, body=body.body, anchor=body.anchor)
    db.add(c)
    db.commit()
    return comment_dict(c)


@router.post("/{pid}/comments/{cid}/resolve")
def resolve_comment(pid: str, cid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:write", p, db)
    c = db.get(m.Comment, cid)
    if not c or c.project_id != pid:
        raise ApiError(404, "not_found")
    c.resolved = True
    db.commit()
    return comment_dict(c)


@router.get("/{pid}/ai-cost")
def project_ai_cost(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..ai.budget import project_cost

    project_access(pid, "project:read", p, db)
    return project_cost(db, pid)


@router.get("/{pid}/audit")
def project_audit(pid: str, response: Response, cursor: str | None = None, limit: int = Query(200, ge=1, le=500),
                  p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    project_access(pid, "project:read", p, db)
    rows, _ = page(db, select(m.AuditEvent).where(m.AuditEvent.project_id == pid), m.AuditEvent.created_at, m.AuditEvent.id, cursor=cursor, limit=limit, response=response)
    return [{"action": a.action, "entity": a.entity, "data": a.data, "created_at": a.created_at.isoformat(), "user_id": a.user_id} for a in rows]


# ------------------------------------------------------------------ reliability levels (Concept / Verified / Production)
@router.get("/{pid}/trust")
def trust_status(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..trust import requirements

    proj = project_access(pid, "project:read", p, db)
    base = latest_base(db, pid)
    return requirements(db, proj, Scene.model_validate(base.data) if base else None, bool(base and base.confirmed))


class SignoffIn(BaseModel):
    scope: str = Field(default="geometry_and_engineering", max_length=80)
    note: str = Field(default="", max_length=1000)


@router.post("/{pid}/trust/signoff")
def trust_signoff(pid: str, body: SignoffIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Specialist (verifier / bureau admin) confirms measurements & engineering — audit record."""
    proj = project_access(pid, "project:read", p, db)
    if not (p.can("project:verify", proj.org_id) or "bureau_admin" in p.roles.get(proj.org_id, set()) or p.is_platform_admin):
        raise ApiError(403, "auth.forbidden", permission="project:verify")
    audit(db, p, "trust.specialist_verified", "project", pid, project_id=pid, org_id=proj.org_id, data={"scope": body.scope, "note": body.note, "name": p.user.name})
    db.commit()
    return {"ok": True}


@router.post("/{pid}/trust/advance")
def trust_advance(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..trust import requirements

    proj = project_access(pid, "project:write", p, db)
    base = latest_base(db, pid)
    req = requirements(db, proj, Scene.model_validate(base.data) if base else None, bool(base and base.confirmed))
    if not req["next"]:
        return req
    missing = [c["code"] for c in req["checklist"] if not c["ok"]]
    if missing:
        raise ApiError(409, "trust.requirements_missing", missing=missing, level=req["next"])
    if req["next"] == "production" and not p.can("project:verify", proj.org_id) and not p.is_platform_admin:
        raise ApiError(403, "auth.production_level_requires_verifier")
    old = proj.accuracy_level
    proj.accuracy_level = req["next"]
    audit(db, p, "trust.level_changed", "project", pid, project_id=pid, org_id=proj.org_id, data={"from": old, "to": proj.accuracy_level})
    db.commit()
    return requirements(db, proj, Scene.model_validate(base.data) if base else None, bool(base and base.confirmed))


# ------------------------------------------------------------------ N99 pilot validation
@router.get("/{pid}/pilot")
def pilot_status(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..pilot import status

    proj = project_access(pid, "project:read", p, db)
    if not (proj.preferences or {}).get("pilot"):
        raise ApiError(404, "not_found")
    return status(db, proj)


class PilotMarkIn(BaseModel):
    code: str = Field(max_length=40)
    ok: bool


@router.post("/{pid}/pilot/mark")
def pilot_mark(pid: str, body: PilotMarkIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..pilot import MANIFEST, mark, status

    proj = project_access(pid, "project:write", p, db)
    if not (proj.preferences or {}).get("pilot"):
        raise ApiError(404, "not_found")
    if body.code not in {c for c, auto in MANIFEST if not auto}:
        raise ApiError(422, "validation", fields=["code"])
    mark(proj, body.code, body.ok)
    audit(db, p, "pilot.mark", "project", pid, project_id=pid, org_id=proj.org_id, data={"code": body.code, "ok": body.ok})
    db.commit()
    return status(db, proj)


@router.get("/{pid}/pilot/report")
def pilot_report(pid: str, format: str = Query("json", pattern="^(json|pdf)$"), lang: str = Query("hy", pattern="^(hy|ru|en)$"),
                 p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Pilot validation report (status, inputs with files, flow, assumptions, risks, approvals, history) as JSON or PDF."""
    from fastapi.responses import Response

    from ..pilot import report, report_pdf

    proj = project_access(pid, "project:read", p, db)
    if not (proj.preferences or {}).get("pilot"):
        raise ApiError(404, "not_found")
    data = report(db, proj)
    audit(db, p, "pilot.report", "project", pid, project_id=pid, org_id=proj.org_id, data={"format": format})
    db.commit()
    if format == "json":
        return data
    name = f"{proj.title}_pilot_report_{lang}.pdf".replace(" ", "_")
    return Response(report_pdf(data, lang), media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})

