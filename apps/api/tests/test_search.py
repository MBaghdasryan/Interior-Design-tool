"""P2-4: semantic search over the catalogue (local multilingual lexical vectors by default,
Gemini behind the same interface with honest fallback), «similar by photo», analog ranking."""
import io

import httpx
import pytest
from PIL import Image

from app import models as m
from app.db import SessionLocal
from app.search import analogs, embeddings, index

pytestmark = pytest.mark.usefixtures("client")


def _png(color) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", (96, 96), color)
    for x in range(0, 96, 12):  # a few stripes so texture features are non-trivial
        for y in range(96):
            im.putpixel((x, y), (20, 20, 20))
    im.save(buf, "PNG")
    return buf.getvalue()


def test_local_vectors_are_cross_lingual_through_the_taxonomy():
    e = embeddings.LocalLexical()
    sofa_doc, bed_doc = e.embed(["Диван угловой Milano серый Диван Բազմոց Sofa sofa"])[0], e.embed(["Кровать Luna 160 Кровать Մահճակալ Bed bed"])[0]
    for q in ("բազմոց", "диван", "sofa"):
        qv = e.embed([q])[0]
        dot = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))  # noqa: E731
        assert dot(qv, sofa_doc) > dot(qv, bed_doc), q


def test_index_search_and_analogs(client, designer, admin):
    with SessionLocal() as db:
        r = index.build(db)
        assert r["status"] == "ok" and r["provider"] == "local" and r["items"] > 50
        assert index.build(db)["embedded"] == 0  # incremental: nothing changed
    st = client.get("/api/v1/catalog/search/status", headers=designer).json()
    assert st["text_provider"] == "local" and st["neural"] is False and st["indexed"]["text"] > 50
    for q, cat in (("բազմոց", "sofa"), ("холодильник", "fridge"), ("bed", "bed")):
        res = client.get("/api/v1/catalog/search/semantic", headers=designer, params={"q": q}).json()
        assert res["items"] and res["items"][0]["category"] == cat, (q, [i["category"] for i in res["items"][:5]])
    ref = client.get("/api/v1/catalog/search/semantic", headers=designer, params={"q": "диван"}).json()["items"][0]["ref"]
    a = client.get("/api/v1/catalog/analogs", headers=designer, params={"ref": ref}).json()
    assert a["base"]["category"] == "sofa" and a["items"] and all(set(i["components"]) == set(analogs.WEIGHTS) for i in a["items"])
    assert a["items"] == sorted(a["items"], key=lambda i: -i["score"])
    assert client.get("/api/v1/catalog/analogs", headers=designer, params={"ref": "pv:" + "0" * 32}).status_code == 404
    assert client.post("/api/v1/admin/search/reindex", headers=designer).status_code == 403


def test_similar_by_photo_ranks_matching_colour_first(client, designer):
    with SessionLocal() as db:
        sup = db.query(m.Supplier).first()
        pvs = db.query(m.ProductVariant).limit(2).all()
        from app.storage import get_storage

        for pv, color in zip(pvs, ((200, 40, 40), (40, 60, 200)), strict=True):
            data = _png(color)
            key = f"suppliers/{sup.id}/texture/test_{pv.id}.png"
            get_storage().put(key, data, "image/png")
            db.add(m.SupplierAsset(supplier_id=sup.id, variant_id=pv.id, kind="texture", filename="t.png", mime="image/png", size=len(data), sha256=pv.id, storage_key=key))
        db.commit()
        assert index.build(db)["images"] == 2
        red = pvs[0].id
    r = client.post("/api/v1/catalog/search/image", headers=designer, files={"file": ("q.png", _png((210, 50, 45)), "image/png")}).json()
    assert r["provider"] == "local-visual-v1" and r["items"][0]["ref"] == f"pv:{red}"
    assert client.post("/api/v1/catalog/search/image", headers=designer, files={"file": ("q.png", b"nope", "image/png")}).json()["code"] == "asset.not_image"


def test_gemini_failure_falls_back_to_local_and_is_reported(monkeypatch):
    def boom(*a, **k):
        raise embeddings.EmbeddingError("gemini 402")

    g = embeddings.GeminiEmbeddings(client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(402))))
    monkeypatch.setattr(embeddings, "text_provider", lambda: g)
    prov, vecs = embeddings.embed_texts(["диван"])
    assert prov.name == "local" and len(vecs[0]) == embeddings.DIM_LOCAL
    assert "gemini" in embeddings._last_error
