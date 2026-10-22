"""Catalogue maintenance jobs: background index crawl of a source (VLV)."""
from __future__ import annotations

from .. import models as m
from ..catalog.indexer import crawl_batch
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
    return {k: v for k, v in r.items() if k != "errors"}
