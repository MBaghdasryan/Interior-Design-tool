"""Geometry recognition job: DXF parsing, AI vision for plan images/PDF pages,
APS for DWG/RVT/IFC. Produces a new unconfirmed BaseScene version."""
from __future__ import annotations

from sqlalchemy import select

from .. import models as m
from ..ai.orchestrator import get_orchestrator
from ..ai.providers import ImageInput, ProviderError
from ..scene.model import Assumption, Scene
from ..scene.recognize import from_dxf, from_recognition, overall_confidence
from ..storage import get_storage
from .runner import JobContext, handler


@handler("recognize")
def recognize(ctx: JobContext) -> dict:
    ctx.define_steps([("pick", "Выбор исходных материалов", "intake"), ("quality", "Проверка качества файлов", "intake"),
                      ("parse", "Распознавание стен, проёмов и помещений", "intake"), ("scale", "Масштаб и контрольные размеры", "intake"),
                      ("save", "Сохранение черновика геометрии", "intake")])
    db = ctx.db
    project = db.get(m.Project, ctx.job.project_id)
    assets = db.scalars(select(m.SourceAsset).where(m.SourceAsset.project_id == project.id)).all()
    ctx.start("pick")
    order = {"dxf": 0, "ifc": 1, "rvt": 1, "dwg": 1, "plan_image": 2, "plan_pdf": 3, "photo": 4}
    ranked = sorted(assets, key=lambda a: order.get(a.kind, 9))
    src = ranked[0] if ranked else None
    ctx.done("pick", f"Файлов: {len(assets)}; основной источник: {src.filename if src else 'нет'}", status="done" if src else "warning")
    ctx.start("quality")
    issues = [f"{a.filename}: {', '.join(a.quality.get('warnings', []))}" for a in assets if a.quality.get("warnings")]
    ctx.done("quality", "; ".join(issues) or "Замечаний нет", status="warning" if issues else "done")
    ctx.start("parse")
    scene: Scene | None = None
    provider = None
    if src and src.kind == "dxf":
        scene = from_dxf(get_storage().get(src.storage_key))
        provider = "dxf"
    elif src and src.kind in ("ifc", "rvt", "dwg"):
        rooms = (src.aps or {}).get("rooms") or []
        scene = Scene(name="Импорт BIM/CAD (APS)", assumptions=[Assumption(key="aps", severity="critical",
                      text=f"Из модели получено помещений: {len(rooms)}. Геометрия стен строится вручную по подложке APS Viewer или из DXF-экспорта")])
        provider = "aps"
    elif src and src.kind == "photo":
        # photos only: room survey, never metric geometry (see app.perception.photos)
        from ..perception.photos import scene_from_survey, survey

        photos = [(a.id, get_storage().get(a.storage_key), a.mime) for a in assets if a.kind == "photo"]
        s = survey(db, project.id, photos)
        for p in s["photos"]:
            a = db.get(m.SourceAsset, p["asset_id"])
            a.quality = {**(a.quality or {}), "survey": {k: v for k, v in p.items() if k != "asset_id"}}
        project.preferences = {**(project.preferences or {}), "photo_survey": {k: v for k, v in s.items() if k != "photos"}}
        scene = scene_from_survey(s)
        provider = "photos:" + s["steps"]["classification"]["provider"]
    elif src and src.kind in ("plan_image", "plan_pdf"):
        data = get_storage().get(src.storage_key)
        img = None
        if src.kind == "plan_pdf":
            try:
                import pymupdf  # optional dependency (dev image) for PDF rasterisation

                page = pymupdf.open(stream=data, filetype="pdf")[0]
                img = ImageInput(page.get_pixmap(dpi=110).tobytes("png"), "image/png")
            except Exception:  # noqa: BLE001
                img = None
        else:
            img = ImageInput(data, src.mime)
        control = (project.preferences or {}).get("control_dimension")
        try:
            rec, provider = get_orchestrator().run("floorplan_vision", {"control_dimension": control, "filename": src.filename}, db=db, project_id=project.id,
                                                   images=[img] if img else [])
            scene = from_recognition(rec.model_dump(), control)
        except (ProviderError, ValueError) as e:
            scene = Scene(name="Требуется ручное построение", assumptions=[Assumption(key="vision", text=str(e)[:300], severity="critical")])
    if scene is None:
        scene = Scene(name="Пустой план", assumptions=[Assumption(key="nosrc", text="Нет исходных файлов — постройте план вручную", severity="critical")])
    ctx.done("parse", f"Стен: {len(scene.walls)}, проёмов: {len(scene.openings)}, помещений: {len(scene.rooms)} (метод: {provider or '—'})",
             status="done" if scene.walls else "warning")
    ctx.start("scale")
    cd = (project.preferences or {}).get("control_dimension")
    ctx.done("scale", f"Контрольный размер: {cd['measured_mm']} мм" if cd else "Контрольный размер не задан — точность «Concept Estimate»", status="done" if cd else "warning")
    ctx.start("save")
    last = db.scalar(select(m.BaseScene).where(m.BaseScene.project_id == project.id).order_by(m.BaseScene.version.desc()).limit(1))
    row = m.BaseScene(project_id=project.id, version=(last.version + 1) if last else 1, data=scene.model_dump(mode="json"), confirmed=False)
    db.add(row)
    project.confidence = overall_confidence(scene)
    project.status = "intake"
    db.commit()
    ctx.done("save", f"Черновик геометрии v{row.version}, уверенность {project.confidence * 100:.0f}% — требуется подтверждение")
    return {"base_scene_id": row.id, "version": row.version}
