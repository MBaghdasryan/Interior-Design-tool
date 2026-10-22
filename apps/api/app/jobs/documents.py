"""Document jobs: A3 album, CAD/BIM/XLSX exports and Autodesk APS flows."""
from __future__ import annotations

import json
import time

from .. import models as m
from ..album.builder import build_album
from ..aps.client import ApsDisabled, extract_rooms, get_aps
from ..exports.files import estimate_csv, estimate_xlsx, to_dxf, to_glb
from ..scene.model import Scene
from ..storage import get_storage, media_type
from .runner import JobContext, handler


def _ctx_entities(ctx: JobContext):
    db = ctx.db
    project = db.get(m.Project, ctx.job.project_id)
    variant = db.get(m.DesignVariant, ctx.params["variant_id"])
    version = db.get(m.DesignVersion, ctx.params.get("version_id") or variant.current_version_id)
    return db, project, variant, version


def _store(db, project, variant, version, kind: str, filename: str, data: bytes, lang: str = "ru", meta: dict | None = None) -> m.Document:
    key = f"projects/{project.id}/documents/{version.id}/{filename}"
    get_storage().put(key, data, media_type(filename))
    doc = m.Document(project_id=project.id, variant_id=variant.id, version_id=version.id, kind=kind, lang=lang, filename=filename,
                     storage_key=key, size=len(data), status="ready", meta=meta or {})
    db.add(doc)
    db.commit()
    return doc


@handler("album")
def album(ctx: JobContext) -> dict:
    ctx.define_steps([("scene", "Загрузка версии проекта", "docs"), ("sheets", "Формирование листов A3", "docs"), ("exports", "DXF, XLSX, CSV, GLB, JSON", "docs"),
                      ("store", "Сохранение комплекта", "docs")])
    db, project, variant, version = _ctx_entities(ctx)
    lang = ctx.params.get("lang", project.doc_lang or "hy")
    sections = set(ctx.params.get("sections") or []) or None
    ctx.start("scene")
    scene = Scene.model_validate(version.scene)
    ctx.done("scene", f"{variant.title}, версия {version.number}: {len(scene.objects)} предметов, {len(scene.rooms)} помещений", version=version.number, items=len(scene.objects), rooms=len(scene.rooms))
    ctx.start("sheets")
    from ..album.i18n import set_overrides
    from ..routers.glossary import approved_overrides

    set_overrides(approved_overrides(db))  # approved Armenian terminology corrections
    pdf, sheets = build_album(db, project, variant, version, lang=lang, sections=sections)
    ctx.done("sheets", f"{len(sheets) + 2} листов A3", n=len(sheets) + 2)
    ctx.start("exports")
    base = f"{project.title}".replace("/", "-").replace(" ", "_")[:40]
    files = [
        ("dxf", f"{base}_v{version.number}.dxf", to_dxf(scene, project.title)),
        ("xlsx", f"{base}_v{version.number}_smeta.xlsx", estimate_xlsx(version.estimate or {}, f"{project.title} — {variant.title} v{version.number}", lang)),
        ("csv", f"{base}_v{version.number}_smeta.csv", estimate_csv(version.estimate or {})),
        ("glb", f"{base}_v{version.number}.glb", to_glb(scene)),
        ("json", f"{base}_v{version.number}.forma.json", json.dumps({"format": "forma-project", "version": 1, "project": {"id": project.id, "title": project.title},
                                                                      "variant": {"id": variant.id, "title": variant.title, "style": variant.style, "tier": variant.tier},
                                                                      "scene": version.scene, "estimate": version.estimate}, ensure_ascii=False).encode()),
    ]
    ctx.done("exports", ", ".join(f"{k.upper()} {len(d) // 1024} КБ" for k, _, d in files))
    ctx.start("store")
    doc = _store(db, project, variant, version, "album_pdf", f"{base}_v{version.number}_album_{lang}.pdf", pdf, lang, {"sheets": sheets})
    ids = [doc.id] + [_store(db, project, variant, version, k, fn, d).id for k, fn, d in files]
    ctx.done("store", f"Документов: {len(ids)}", n=len(ids))
    return {"document_ids": ids, "album_id": doc.id}


@handler("aps_dwg")
def aps_dwg(ctx: JobContext) -> dict:
    """DXF → DWG with Autodesk Design Automation for AutoCAD, then SVF2 for the APS Viewer."""
    ctx.define_steps([("dxf", "Экспорт DXF из модели проекта", "aps"), ("upload", "Загрузка в Autodesk OSS", "aps"), ("workitem", "Design Automation: AutoCAD DXF → DWG", "aps"),
                      ("translate", "Model Derivative: DWG → SVF2 (просмотр)", "aps"), ("store", "Сохранение DWG", "aps")])
    db, project, variant, version = _ctx_entities(ctx)
    aps = get_aps()
    ctx.start("dxf")
    dxf = to_dxf(Scene.model_validate(version.scene), project.title)
    ctx.done("dxf", f"{len(dxf) // 1024} КБ, слои AIA (A-WALL, A-DOOR, I-FURN, E-POWR…)")
    ctx.start("upload")
    if not aps.enabled:
        raise ApsDisabled("APS не настроен: задайте APS_CLIENT_ID / APS_CLIENT_SECRET и выполните scripts/aps_setup.py")
    key_base = f"{project.id}-{version.id}"
    up = aps.upload(f"{key_base}.dxf", dxf)
    in_url = aps.signed_download(f"{key_base}.dxf")
    out_url, out_key = aps.signed_upload(f"{key_base}.dwg")
    ctx.done("upload", f"OSS: {up['bucketKey']}/{up['objectKey']}")
    ctx.start("workitem")
    wi = aps.workitem_dxf_to_dwg(in_url, out_url)
    status = wi
    for _ in range(120):
        status = aps.workitem_status(wi["id"])
        if status.get("status") not in ("pending", "inprogress"):
            break
        time.sleep(5)
    if status.get("status") != "success":
        raise RuntimeError(f"Design Automation: {status.get('status')} — отчёт: {status.get('reportUrl')}")
    obj = aps.complete_upload(f"{key_base}.dwg", out_key)
    ctx.done("workitem", f"WorkItem {wi['id']}: success")
    ctx.start("translate")
    from ..aps.client import urn_of

    urn = urn_of(obj["objectId"])
    aps.translate(urn, views=("2d",))
    man = aps.wait_translation(urn, timeout_s=600)
    ctx.done("translate", f"Manifest: {man.get('status')} {man.get('progress')}", status="done" if man.get("status") == "success" else "warning")
    ctx.start("store")
    dwg_bytes = aps.http.get(aps.signed_download(f"{key_base}.dwg")).content
    doc = _store(db, project, variant, version, "dwg", f"{project.title[:40].replace(' ', '_')}_v{version.number}.dwg", dwg_bytes,
                 meta={"aps": {"objectId": obj["objectId"], "urn": urn, "workitem": wi["id"], "manifest": man.get("status")}})
    ctx.done("store", f"DWG {len(dwg_bytes) // 1024} КБ")
    return {"document_id": doc.id, "urn": urn}


@handler("aps_translate")
def aps_translate(ctx: JobContext) -> dict:
    """Uploaded DWG/RVT/IFC → OSS → SVF2 → properties → rooms to seed the BuildingGraph."""
    ctx.define_steps([("upload", "Загрузка исходного файла в Autodesk OSS", "aps"), ("translate", "Model Derivative: перевод в SVF2", "aps"),
                      ("properties", "Извлечение помещений и площадей", "aps")])
    db = ctx.db
    asset = db.get(m.SourceAsset, ctx.params["asset_id"])
    aps = get_aps()
    ctx.start("upload")
    if not aps.enabled:
        raise ApsDisabled("APS не настроен: задайте APS_CLIENT_ID / APS_CLIENT_SECRET")
    data = get_storage().get(asset.storage_key)
    up = aps.upload(f"{asset.project_id}-{asset.id}-{asset.filename}".replace(" ", "_")[:200], data)
    asset.aps = {**up, "status": "uploaded"}
    db.commit()
    ctx.done("upload", f"{up['objectKey']}")
    ctx.start("translate")
    aps.translate(up["urn"])
    man = aps.wait_translation(up["urn"], on_progress=lambda p: None)
    asset.aps = {**asset.aps, "status": man.get("status"), "progress": man.get("progress")}
    db.commit()
    ctx.done("translate", f"{man.get('status')} {man.get('progress')}", status="done" if man.get("status") == "success" else "failed")
    ctx.start("properties")
    rooms: list[dict] = []
    for md in aps.metadata(up["urn"]):
        if md.get("role") == "3d" or len(rooms) == 0:
            rooms += extract_rooms(aps.properties(up["urn"], md["guid"]))
    asset.aps = {**asset.aps, "rooms": rooms}
    db.commit()
    ctx.done("properties", f"Найдено помещений: {len(rooms)}" + ("" if rooms else " — проверьте категории Rooms/IfcSpace в модели"),
             status="done" if rooms else "warning")
    return {"urn": up["urn"], "rooms": rooms}
