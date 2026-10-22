"""Product embedding index (P2-4). Vectors live in `product_embeddings` (JSON; dimension per
provider) and are searched in memory with numpy — enough for tens of thousands of items. The
migration enables pgvector when the database has it, for an ANN index once the catalogue outgrows
memory (docs/DECISIONS/ADR-009.md)."""
from __future__ import annotations

import hashlib
import threading

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.candidates import Candidate, candidate_from_record, load_internal
from ..catalog.taxonomy import CATEGORIES
from . import embeddings, visual

_cache: dict[tuple, tuple] = {}
_lock = threading.Lock()


def doc_text(c: Candidate) -> str:
    cat = CATEGORIES.get(c.category, ("", "", "", ""))
    return " ".join(x for x in (c.name, c.supplier_name, cat[1], cat[2], cat[3], c.category.replace("_", " "), c.color, c.material, " ".join(c.styles), c.tier) if x)


def candidates(db: Session) -> list[Candidate]:
    out = load_internal(db)
    for rec in db.scalars(select(m.ExternalProductRecord).where(m.ExternalProductRecord.review_status != "rejected", m.ExternalProductRecord.normalized_category.isnot(None))):
        src = db.get(m.ExternalSource, rec.source_id)
        if src and src.enabled:
            out.append(candidate_from_record(rec, src))
    return out


def build(db: Session, *, limit: int | None = None) -> dict:
    """Incremental: only items whose text changed (sha1 of the document) are re-embedded."""
    items = candidates(db)[:limit]
    prov = embeddings.text_provider()
    if prov is None:
        return {"status": "off"}
    have = {(e.item_ref): e for e in db.scalars(select(m.ProductEmbedding).where(m.ProductEmbedding.modality == "text", m.ProductEmbedding.provider == prov.name,
                                                                                 m.ProductEmbedding.model == prov.model))}
    todo = []
    for c in items:
        txt = doc_text(c)
        h = hashlib.sha1(txt.encode()).hexdigest()
        if c.ref not in have or have[c.ref].text_hash != h:
            todo.append((c, txt, h))
    used = prov
    for i in range(0, len(todo), 200):
        chunk = todo[i:i + 200]
        used, vecs = embeddings.embed_texts([t for _, t, _ in chunk])
        for (c, _, h), vec in zip(chunk, vecs, strict=True):
            row = have.get(c.ref) if used.name == prov.name else None
            if row is None:
                row = m.ProductEmbedding(item_ref=c.ref, modality="text", provider=used.name, model=used.model, dim=len(vec))
                db.add(row)
            row.vector, row.text_hash = [round(x, 5) for x in vec], h
        db.flush()
    images = _index_images(db)
    db.commit()
    with _lock:
        _cache.clear()
    return {"status": "ok", "provider": used.name, "model": used.model, "items": len(items), "embedded": len(todo), "images": images}


def _index_images(db: Session) -> int:
    """Image vectors for products that have a picture in our own storage (supplier textures/photos linked to a SKU)."""
    from ..storage import get_storage

    n = 0
    st = get_storage()
    for a in db.scalars(select(m.SupplierAsset).where(m.SupplierAsset.kind == "texture", m.SupplierAsset.variant_id.isnot(None))):
        ref = f"pv:{a.variant_id}"
        row = db.scalar(select(m.ProductEmbedding).where(m.ProductEmbedding.item_ref == ref, m.ProductEmbedding.modality == "image"))
        if row and row.text_hash == a.sha256:
            continue
        try:
            vec = visual.describe(st.get(a.storage_key))
        except Exception:  # noqa: BLE001 - an unreadable image is skipped, never fatal
            continue
        row = row or m.ProductEmbedding(item_ref=ref, modality="image", provider="local", model="local-visual-v1", dim=len(vec))
        row.vector, row.text_hash = [round(x, 5) for x in vec], a.sha256
        db.add(row)
        n += 1
    return n


def _matrix(db: Session, modality: str, provider: str, model: str):
    stamp = db.scalar(select(func.count(m.ProductEmbedding.id)).where(m.ProductEmbedding.modality == modality, m.ProductEmbedding.provider == provider, m.ProductEmbedding.model == model))
    key = (modality, provider, model)
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == stamp:
            return hit[1], hit[2]
    rows = db.execute(select(m.ProductEmbedding.item_ref, m.ProductEmbedding.vector).where(m.ProductEmbedding.modality == modality, m.ProductEmbedding.provider == provider,
                                                                                            m.ProductEmbedding.model == model)).all()
    refs = [r for r, _ in rows]
    mat = np.array([v for _, v in rows], dtype=np.float32) if rows else np.zeros((0, 1), dtype=np.float32)
    with _lock:
        _cache[key] = (stamp, refs, mat)
    return refs, mat


def search_text(db: Session, query: str, k: int = 30) -> tuple[list[tuple[str, float]], dict]:
    prov, vecs = embeddings.embed_texts([query])
    refs, mat = _matrix(db, "text", prov.name, prov.model)
    if not refs:
        return [], {"provider": prov.name, "indexed": 0}
    sims = mat @ np.array(vecs[0], dtype=np.float32)
    top = np.argsort(-sims)[:k]
    return [(refs[i], float(sims[i])) for i in top if sims[i] > 0.05], {"provider": prov.name, "model": prov.model, "indexed": len(refs)}


def search_image(db: Session, data: bytes, k: int = 20) -> tuple[list[tuple[str, float]], dict]:
    refs, mat = _matrix(db, "image", "local", "local-visual-v1")
    if not refs:
        return [], {"provider": "local-visual-v1", "indexed": 0}
    sims = mat @ np.array(visual.describe(data), dtype=np.float32)
    top = np.argsort(-sims)[:k]
    return [(refs[i], float(sims[i])) for i in top], {"provider": "local-visual-v1", "indexed": len(refs)}


def text_similarity(db: Session, ref: str, others: list[str]) -> dict[str, float]:
    prov = embeddings.text_provider()
    if prov is None:
        return {}
    refs, mat = _matrix(db, "text", prov.name, prov.model)
    pos = {r: i for i, r in enumerate(refs)}
    if ref not in pos:
        return {}
    base = mat[pos[ref]]
    return {o: float(mat[pos[o]] @ base) for o in others if o in pos}
