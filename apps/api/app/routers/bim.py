"""CAD/BIM interchange (P2-6): IFC4 export of the project geometry, editable IFC import
(walls, openings, spaces) and Apple RoomPlan (LiDAR) import. Imports create a draft base scene that
the designer reviews and confirms like any recognised plan."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models as m
from ..bim import ifc_io, roomplan
from ..db import get_db
from ..errors import ApiError
from ..jobs.pipeline import latest_base
from ..scene.geometry import room_area_m2
from ..scene.model import Scene
from ..scene.recognize import overall_confidence
from ..security import Principal, audit, current_principal, project_access
from ..storage import get_storage

router = APIRouter(prefix="/api/v1/projects/{pid}", tags=["bim"])


def _draft(db: Session, proj: m.Project, sc: Scene, source: str) -> int:
    last = latest_base(db, proj.id)
    version = (last.version + 1) if last else 1
    db.add(m.BaseScene(project_id=proj.id, version=version, data=sc.model_dump(mode="json"), confirmed=False))
    proj.confidence = overall_confidence(sc)
    proj.area_m2 = round(sum(room_area_m2(r) for r in sc.rooms if r.type != "balcony"), 1) or proj.area_m2
    proj.status = "intake"
    return version


@router.get("/geometry.ifc")
def export_ifc(pid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:read", p, db)
    base = latest_base(db, pid)
    if not base:
        raise ApiError(404, "geometry.missing")
    data = ifc_io.to_ifc(Scene.model_validate(base.data), proj.title)
    audit(db, p, "geometry.export_ifc", "base_scene", base.id, project_id=pid)
    db.commit()
    return Response(data, media_type="application/x-step", headers={"Content-Disposition": f'attachment; filename="{pid[:8]}_v{base.version}.ifc"'})


@router.post("/assets/{aid}/import-ifc")
def import_ifc(pid: str, aid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    a = db.get(m.SourceAsset, aid)
    if not a or a.project_id != pid:
        raise ApiError(404, "not_found")
    if a.kind != "ifc":
        raise ApiError(422, "file.unsupported")
    try:
        sc, stats = ifc_io.from_ifc(get_storage().get(a.storage_key))
    except Exception:  # noqa: BLE001 - malformed IFC → user-facing error, never a 500
        raise ApiError(422, "bim.ifc_unreadable") from None
    if not sc.walls:
        raise ApiError(422, "bim.no_walls")
    version = _draft(db, proj, sc, "ifc")
    audit(db, p, "geometry.import_ifc", "source_asset", aid, project_id=pid, data=stats)
    db.commit()
    return {"version": version, **stats}


@router.post("/import/roomplan")
async def import_roomplan(pid: str, file: UploadFile = File(...), p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    proj = project_access(pid, "project:write", p, db)
    data = await file.read()
    if len(data) > 20 << 20:
        raise ApiError(422, "file.too_large")
    try:
        sc, stats = roomplan.parse(data)
    except roomplan.RoomPlanError as e:
        raise ApiError(422, str(e)) from None
    import hashlib

    key = f"projects/{pid}/scans/{hashlib.sha256(data).hexdigest()[:16]}_roomplan.json"
    get_storage().put(key, data, "application/json")
    db.add(m.SourceAsset(project_id=pid, kind="scan", filename=(file.filename or "roomplan.json")[:200], mime="application/json", size=len(data),
                         sha256=hashlib.sha256(data).hexdigest(), storage_key=key))
    version = _draft(db, proj, sc, "roomplan")
    audit(db, p, "geometry.import_roomplan", "project", pid, project_id=pid, data=stats)
    db.commit()
    return {"version": version, **stats}
