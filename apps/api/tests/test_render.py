"""P1-5: photoreal render pipeline with a fake image provider (no network) — control image,
SKU manifest, stored render, honest grounding without a vision provider, masked zone
regeneration that never touches pixels outside the mask, API endpoints."""
import io

import pytest
from PIL import Image, ImageChops

from app import models as m
from app.db import SessionLocal
from app.render import control
from app.render.providers import RenderProvider, RenderResult
from app.render.service import regenerate_zone, render_room
from app.scene.model import Scene
from app.storage import get_storage


@pytest.fixture(scope="module", autouse=True)
def _variants(client, designer):
    """The demo project needs generated variants (the flow test creates them when the whole suite runs)."""
    pid = next(p for p in client.get("/api/v1/projects", headers=designer).json() if p["title"].startswith("Демо"))["id"]
    if not client.get(f"/api/v1/projects/{pid}/variants", headers=designer).json():
        client.post(f"/api/v1/projects/{pid}/geometry/control-dimension", headers=designer, json={"wall_id": "W1", "measured_mm": 9600})
        client.post(f"/api/v1/projects/{pid}/geometry/confirm", headers=designer)
        r = client.post(f"/api/v1/projects/{pid}/generate", headers=designer, json={"product_source": "external", "external_settings": {"sources": ["domus"]}})
        assert r.status_code == 200, r.text


class FakeImage(RenderProvider):
    """Returns the geometry guide recoloured — enough to exercise storage, masks and compositing."""
    name = "fake"
    model = "fake-image-1"
    calls: list[str] = []

    def available(self):
        return True

    def generate(self, prompt, images, *, size=None, aspect="16:9"):
        FakeImage.calls.append(prompt)
        img = Image.open(io.BytesIO(images[0][0])).convert("RGB")
        img = ImageChops.invert(img) if "Edit the attached" in prompt else img.point(lambda v: min(255, v + 10))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return RenderResult(buf.getvalue(), "image/png", self.model, 5, images=1)


def _variant(db):
    proj = db.query(m.Project).filter(m.Project.title.like("Демо%")).first()
    v = db.query(m.DesignVariant).filter_by(project_id=proj.id).first()
    assert v is not None
    return proj, v, db.get(m.DesignVersion, v.current_version_id)


def test_control_segmentation_and_visible_objects():
    with SessionLocal() as db:
        _, _, ver = _variant(db)
        scene = Scene.model_validate(ver.scene)
    room = next(r for r in scene.rooms if any(o.room_id == r.id for o in scene.objects) and any(c.room_id == r.id for c in scene.cameras))
    cam = next(c for c in scene.cameras if c.room_id == room.id)
    items = control.project(scene, room.id, cam)
    ctrl = control.control_image(items)
    seg, legend = control.segmentation(items, scene)
    assert Image.open(io.BytesIO(ctrl)).size == control.SIZE and legend
    vis = control.visible_objects(seg, legend)
    assert vis and all(v["position"] in ("left", "center", "right") for v in vis.values())
    assert all(scene.objects[[o.id for o in scene.objects].index(oid)].room_id == room.id for oid in vis)


def test_render_room_manifest_storage_and_honest_grounding():
    FakeImage.calls.clear()
    with SessionLocal() as db:
        proj, v, ver = _variant(db)
        scene = Scene.model_validate(ver.scene)
        room = next(r for r in scene.rooms if any(c.room_id == r.id for c in scene.cameras) and any(o.room_id == r.id for o in scene.objects))
        doc = render_room(db, proj, v, ver, room.id, provider=FakeImage(), fetcher=None)
        meta = doc.meta
    prompt = FakeImage.calls[0]
    assert "STRICT CONSTRAINTS" in prompt and all(it["code"] in prompt for it in meta["manifest"])  # every visible SKU is in the prompt
    assert meta["manifest"] and {"code", "sku", "supplier", "mode", "position"} <= set(meta["manifest"][0])
    st = get_storage()
    assert st.exists(doc.storage_key) and st.exists(meta["png_key"]) and st.exists(meta["seg_key"]) and doc.filename.endswith(".jpg")
    g = meta["grounding"]
    # tests run with the stub AI: without a vision provider nothing is claimed as matching
    assert g["verified"] is False and g["score"] is None and set(g["visual_analogs"]) == {it["code"] for it in meta["manifest"]}
    with SessionLocal() as db:
        u = db.query(m.AIUsage).filter_by(task="render_room", provider="fake").order_by(m.AIUsage.created_at.desc()).first()
        assert u.ok and u.org_id == proj.org_id


def test_zone_regeneration_changes_only_masked_pixels():
    with SessionLocal() as db:
        proj, v, ver = _variant(db)
        scene = Scene.model_validate(ver.scene)
        room = next(r for r in scene.rooms if any(c.room_id == r.id for c in scene.cameras) and any(o.room_id == r.id for o in scene.objects))
        doc = render_room(db, proj, v, ver, room.id, provider=FakeImage())
        target = {doc.meta["manifest"][0]["object_id"]}
        new = regenerate_zone(db, proj, doc, target, "make it darker", provider=FakeImage())
        st = get_storage()
        before = Image.open(io.BytesIO(st.get(doc.meta["png_key"]))).convert("RGB")
        after = Image.open(io.BytesIO(st.get(new.meta["png_key"]))).convert("RGB")
        mask = Image.open(io.BytesIO(control.mask_for(st.get(doc.meta["seg_key"]), doc.meta["legend"], target, grow_px=24 + 3 * 6 + 2))).convert("L")  # mask growth + Gaussian feather (≈3σ)
    diff = ImageChops.difference(before, after).convert("L")
    outside = ImageChops.multiply(diff, ImageChops.invert(mask))  # changes outside the (feathered) mask
    assert diff.getbbox() is not None, "the zone changed"
    assert outside.getbbox() is None, "nothing outside the mask changed"
    assert new.meta["parent_id"] == doc.id and new.meta["edited_objects"] == sorted(target)


def test_render_endpoints(client, designer, monkeypatch):
    import app.render.service as svc
    from app.render import providers

    monkeypatch.setattr(providers, "get_render_provider", lambda: FakeImage())
    monkeypatch.setattr(svc, "get_render_provider", lambda: FakeImage())
    pid = next(p for p in client.get("/api/v1/projects", headers=designer).json() if p["title"].startswith("Демо"))["id"]
    variants = client.get(f"/api/v1/projects/{pid}/variants", headers=designer).json()
    vid = variants[0]["id"]
    scene = client.get(f"/api/v1/projects/{pid}/variants/{vid}", headers=designer).json()["version"]["scene"]
    room = next(c["room_id"] for c in scene["cameras"] if any(o["room_id"] == c["room_id"] for o in scene["objects"]))
    job = client.post(f"/api/v1/projects/{pid}/variants/{vid}/renders", headers=designer, json={"room_id": room}).json()
    assert job["status"] == "succeeded", job
    renders = client.get(f"/api/v1/projects/{pid}/variants/{vid}/renders", headers=designer).json()
    assert renders and renders[0]["room_id"] == room and renders[0]["url"] and renders[0]["manifest"]
    obj = renders[0]["manifest"][0]["object_id"]
    bad = client.post(f"/api/v1/projects/{pid}/renders/{renders[0]['id']}/regenerate", headers=designer, json={"object_ids": ["nope"]})
    assert bad.status_code == 422
    ok = client.post(f"/api/v1/projects/{pid}/renders/{renders[0]['id']}/regenerate", headers=designer, json={"object_ids": [obj], "instruction": "lighter fabric"}).json()
    assert ok["status"] == "succeeded", ok


def test_color_score_is_a_pixel_measurement():
    from app.render.service import color_score

    assert color_score((200, 160, 120), "#c8a078") == 1.0  # same colour
    assert color_score((210, 168, 126), "#c8a078") >= 0.9  # lighting shift
    assert color_score((40, 60, 160), "#c8a078") == 0.0  # blue instead of oak
    assert color_score(None, "#ffffff") == 0.0


def test_album_and_client_use_the_photoreal_render(client, designer):
    """ДН4 shows the stored render with an honest caption; the client viewer lists it."""
    import pymupdf

    from app.album.builder import build_album

    with SessionLocal() as db:
        proj, v, ver = _variant(db)
        scene = Scene.model_validate(ver.scene)
        room = next(r for r in scene.rooms if any(c.room_id == r.id for c in scene.cameras) and any(o.room_id == r.id for o in scene.objects))
        render_room(db, proj, v, ver, room.id, provider=FakeImage())
        pdf, sheets = build_album(db, proj, v, ver, lang="en")
        share = proj.share_token
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    pages = [p for p in doc if "AI visualisation" in p.get_text()]
    assert pages and pages[0].get_images(), "render embedded as an image on the visual sheet"
    assert "product match not verified" in pages[0].get_text()  # stub grounding: no claim
    cv = client.get(f"/api/v1/client/{share}").json()
    assert any(r["room_id"] == room.id and r["url"] for vv in cv["variants"] for r in vv.get("renders", []))
