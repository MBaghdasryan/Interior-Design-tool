"""Catalogue maintenance jobs: background index crawl (VLV), TTL refresh of stale records, supplier feed sync."""
from __future__ import annotations

from .. import models as m
from ..catalog.indexer import crawl_batch
from ..catalog.maintenance import evaluate_run, refresh_records, sync_feed
from .runner import JobContext, handler


@handler("source_index")
def source_index(ctx: JobContext) -> dict:
    ctx.define_steps([("crawl", "Индексация карточек источника", "catalog")])
    src = ctx.db.get(m.ExternalSource, ctx.params["source_id"])
    ctx.start("crawl")
    r = crawl_batch(ctx.db, src, batch=int(ctx.params.get("batch", 60)), deadline_s=ctx.params.get("deadline_s"))
    ctx.done("crawl", f"Пройдено карточек: {r.get('fetched', 0)}; в индекс: {r.get('indexed', 0)}; не для интерьера: {r.get('irrelevant', 0)}",
             status="done" if r.get("status") in ("ok", "empty") else "warning", **{k: r.get(k, 0) for k in ("fetched", "indexed", "irrelevant", "accessories", "blocked")},
             cursor=r.get("cursor", 0), total=r.get("total", 0))
    run = ctx.db.query(m.ExternalConnectorRun).filter_by(source_id=src.id, kind="index").order_by(m.ExternalConnectorRun.created_at.desc()).first()
    if run and r.get("status") != "live_disabled":
        evaluate_run(ctx.db, src, run, r)
        ctx.db.commit()
    return {k: v for k, v in r.items() if k != "errors"}


@handler("source_refresh")
def source_refresh(ctx: JobContext) -> dict:
    ctx.define_steps([("refresh", "Перепроверка устаревших цен", "catalog")])
    src = ctx.db.get(m.ExternalSource, ctx.params["source_id"])
    ctx.start("refresh")
    r = refresh_records(ctx.db, src, ctx.params.get("record_ids", []))
    ctx.done("refresh", f"Проверено: {r['fetched']}; обновлено: {r['refreshed']}", status="done" if r["status"] == "ok" else "warning", **r)
    return r


@handler("supplier_feed")
def supplier_feed(ctx: JobContext) -> dict:
    ctx.define_steps([("sync", "Синхронизация фида поставщика", "catalog")])
    sup = ctx.db.get(m.Supplier, ctx.params["supplier_id"])
    ctx.start("sync")
    r = sync_feed(ctx.db, sup)
    ctx.done("sync", r["status"], status="done" if r["status"] == "ok" else "warning", **{k: v for k, v in r.items() if k != "errors"})
    return {k: v for k, v in r.items() if k != "errors"}


@handler("search_index")
def search_index(ctx: JobContext) -> dict:
    from ..search import index

    ctx.define_steps([("embed", "Индекс семантического поиска", "catalog")])
    ctx.start("embed")
    r = index.build(ctx.db)
    ctx.done("embed", f"{r.get('provider')}: {r.get('embedded', 0)} из {r.get('items', 0)}; изображений {r.get('images', 0)}", **{k: v for k, v in r.items() if isinstance(v, int | str)})
    return r
