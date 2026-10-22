"""Photoreal render jobs (Gemini image models): room render and zone regeneration."""
from __future__ import annotations

from .. import models as m
from ..render.service import regenerate_zone, render_room
from .runner import JobContext, handler


@handler("render")
def render(ctx: JobContext) -> dict:
    ctx.define_steps([("manifest", "Геометрия камеры и SKU-манифест", "render"), ("generate", "Фотореалистичная визуализация", "render"),
                      ("grounding", "Проверка соответствия товарам", "render"), ("store", "Сохранение", "render")])
    db = ctx.db
    project = db.get(m.Project, ctx.job.project_id)
    variant = db.get(m.DesignVariant, ctx.params["variant_id"])
    version = db.get(m.DesignVersion, ctx.params.get("version_id") or variant.current_version_id)
    ctx.start("manifest")

    def progress(step: str, params: dict) -> None:
        detail = {"manifest": "Предметов в кадре: {items} (реальных SKU: {real})", "generate": "Модель {model}, размер {size}",
                  "grounding": "Соответствие {score}; визуальных аналогов: {analogs}"}[step].format(**params)
        ctx.done(step, detail, **params)
        nxt = {"manifest": "generate", "generate": "grounding", "grounding": "store"}[step]
        ctx.start(nxt)

    doc = render_room(db, project, variant, version, ctx.params["room_id"], ctx.params.get("camera_id"), progress=progress)
    ctx.done("store", f"{doc.meta['width']}×{doc.meta['height']}", width=doc.meta["width"], height=doc.meta["height"])
    return {"document_id": doc.id, "grounding": doc.meta["grounding"].get("score")}


@handler("render_edit")
def render_edit(ctx: JobContext) -> dict:
    ctx.define_steps([("generate", "Перегенерация выбранной зоны", "render"), ("store", "Сохранение", "render")])
    db = ctx.db
    project = db.get(m.Project, ctx.job.project_id)
    doc = db.get(m.Document, ctx.params["document_id"])
    ctx.start("generate")
    new = regenerate_zone(db, project, doc, set(ctx.params["object_ids"]), ctx.params.get("instruction", ""))
    ctx.done("generate", f"Объектов в зоне: {len(ctx.params['object_ids'])}", n=len(ctx.params["object_ids"]))
    ctx.done("store", f"{new.meta['width']}×{new.meta['height']}", width=new.meta["width"], height=new.meta["height"])
    return {"document_id": new.id, "grounding": new.meta["grounding"].get("score")}
