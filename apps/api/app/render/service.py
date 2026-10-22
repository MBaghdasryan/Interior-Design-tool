"""Photoreal room renders: control image + SKU manifest → image model → vision grounding
check → stored Document(kind="render") with per-item scores. Items scoring below
GROUNDING_THRESHOLD are labelled "visual analog" — the picture is an illustration of that
product, not a guaranteed likeness. Zone regeneration composites the new pixels into the
previous render only inside the mask."""
from __future__ import annotations

import hashlib
import io

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..ai import budget
from ..ai.orchestrator import PROMPTS_DIR, get_orchestrator
from ..ai.providers import ImageInput
from ..catalog.taxonomy import STYLES
from ..scene.model import Scene
from ..storage import get_storage
from . import control
from .manifest import build_manifest, reference_images
from .providers import PROMPT_VERSION, RenderError, get_render_provider

GROUNDING_THRESHOLD = 0.5


def _prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.{PROMPT_VERSION}.md").read_text(encoding="utf-8")


def _manifest_lines(items: list[dict]) -> str:
    return "\n".join(f"- {it['code']} · {it['type']} · {it['name'][:80]} · {it['color_hex']} · {it['size_mm'][0]}×{it['size_mm'][1]}×{it['size_mm'][2]} · {it['position']}"
                     for it in items) or "- (no furniture in this view)"


def _log(db: Session, project: m.Project, task: str, provider, model: str, cost: float, latency: int, ok: bool, err: str | None = None, tin=0, tout=0):
    db.add(m.AIUsage(project_id=project.id, org_id=project.org_id, task=task, provider=provider.name, model=model, prompt_version=PROMPT_VERSION,
                     input_tokens=tin, output_tokens=tout, latency_ms=latency, cost_usd=cost, ok=ok, error=err))
    db.flush()


def _to_jpeg(png: bytes, quality: int = 90) -> bytes:
    img = Image.open(io.BytesIO(png)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def grounding(db: Session, project: m.Project, render_png: bytes, control_png: bytes, manifest: list[dict]) -> dict:
    """Vision check of the render against the manifest → per-item scores and a summary."""
    if not manifest:
        return {"score": None, "items": {}, "visual_analogs": [], "extra_objects": [], "provider": None}
    payload = {"manifest": [{k: it[k] for k in ("code", "type", "name", "color_hex", "size_mm", "position")} for it in manifest]}
    check, provider = get_orchestrator().run("render_grounding", payload, db=db, project_id=project.id,
                                             images=[ImageInput(render_png, "image/png"), ImageInput(control_png, "image/png")], stub_on_quota=True)
    items = {}
    for g in check.items:
        s = (0.4 * g.type_match + 0.3 * g.color_match + 0.3 * g.position_match) if g.visible else 0.0
        items[g.code] = {"score": round(s, 2), "visible": g.visible, "type": g.type_match, "color": g.color_match, "position": g.position_match, "note": g.note[:200]}
    for it in manifest:  # an item the checker skipped counts as not verified
        items.setdefault(it["code"], {"score": 0.0, "visible": False, "type": 0, "color": 0, "position": 0, "note": "not reported"})
    scores = [v["score"] for v in items.values()]
    verified = provider != "stub"
    return {"score": round(sum(scores) / len(scores), 2) if verified else None, "items": items, "verified": verified, "provider": provider,
            "visual_analogs": [c for c, v in items.items() if v["score"] < GROUNDING_THRESHOLD],
            "extra_objects": check.extra_objects[:10]}


def render_room(db: Session, project: m.Project, variant: m.DesignVariant, version: m.DesignVersion, room_id: str, camera_id: str | None = None,
                *, provider=None, fetcher=None, progress=None) -> m.Document:
    provider = provider or get_render_provider()
    if provider is None:
        raise RenderError("no image provider configured")
    scene = Scene.model_validate(version.scene)
    cams = [c for c in scene.cameras if c.room_id == room_id]
    cam = next((c for c in cams if c.id == camera_id), cams[0] if cams else None)
    if cam is None:
        raise RenderError(f"no camera in room {room_id}")
    items = control.project(scene, room_id, cam)
    ctrl = control.control_image(items)
    seg, legend = control.segmentation(items, scene)
    visible = control.visible_objects(seg, legend)
    manifest = build_manifest(db, scene, room_id, visible)
    progress and progress("manifest", {"items": len(manifest), "real": sum(1 for i in manifest if i["mode"] == "real")})
    refs = reference_images(db, manifest, fetcher=fetcher)
    st = STYLES.get(variant.style, {})
    finishes = ", ".join(f"{f.surface}: {f.name or f.material_code} {f.color_hex}" for f in scene.finishes if f.room_id == room_id)[:500]
    prompt = _prompt("render_room").format(style=variant.style, palette=", ".join(st.get("palette", [])), finishes=finishes or "as in the guide",
                                           allow_styling="false", manifest=_manifest_lines(manifest))
    if refs:
        prompt += "\n\nREFERENCE PHOTOS (after the guide image, in this order): " + ", ".join(code for code, _, _ in refs)
    budget.check(db, project.org_id)
    try:
        res = provider.generate(prompt, [(ctrl, "image/png")] + [(b, mime) for _, b, mime in refs])
    except RenderError as e:
        _log(db, project, "render_room", provider, getattr(provider, "model", provider.name), 0.0, 0, False, str(e)[:500])
        db.commit()
        raise
    _log(db, project, "render_room", provider, res.model, provider.cost(res), res.latency_ms, True, tin=res.input_tokens, tout=res.output_tokens)
    db.commit()
    progress and progress("generate", {"model": res.model, "size": res.meta.get("image_size")})
    render_png = _png(res.image)
    g = grounding(db, project, render_png, ctrl, manifest)
    progress and progress("grounding", {"score": g["score"], "analogs": len(g["visual_analogs"])})
    return _store(db, project, variant, version, room_id, cam.id, render_png, ctrl, seg, legend, manifest, g,
                  {"model": res.model, "provider": provider.name, "prompt_version": PROMPT_VERSION, "image_size": res.meta.get("image_size"),
                   "references": [c for c, _, _ in refs], "cost_usd": provider.cost(res)})


def regenerate_zone(db: Session, project: m.Project, doc: m.Document, object_ids: set[str], instruction: str, *, provider=None) -> m.Document:
    provider = provider or get_render_provider()
    if provider is None:
        raise RenderError("no image provider configured")
    st = get_storage()
    meta = doc.meta
    prev = st.get(meta["png_key"])
    seg = st.get(meta["seg_key"])
    mask = control.mask_for(seg, meta["legend"], object_ids)
    variant = db.get(m.DesignVariant, doc.variant_id)
    version = db.get(m.DesignVersion, doc.version_id)
    scene = Scene.model_validate(version.scene)
    manifest = [it for it in meta["manifest"] if it["object_id"] in object_ids]
    prompt = _prompt("render_edit").format(instruction=instruction[:500] or "re-render the products listed below", manifest=_manifest_lines(manifest))
    budget.check(db, project.org_id)
    res = provider.generate(prompt, [(prev, "image/png"), (mask, "image/png")])
    _log(db, project, "render_edit", provider, res.model, provider.cost(res), res.latency_ms, True, tin=res.input_tokens, tout=res.output_tokens)
    db.commit()
    out = control.composite(prev, _png(res.image), mask)  # outside the mask: previous pixels, guaranteed
    ctrl = st.get(meta["control_key"])
    g = grounding(db, project, out, ctrl, meta["manifest"])
    return _store(db, project, variant, version, meta["room_id"], meta["camera_id"], out, ctrl, seg, meta["legend"], meta["manifest"], g,
                  {"model": res.model, "provider": provider.name, "prompt_version": PROMPT_VERSION, "parent_id": doc.id, "edited_objects": sorted(object_ids),
                   "instruction": instruction[:500], "cost_usd": provider.cost(res)}, scene=scene)


def _png(image: bytes) -> bytes:
    img = Image.open(io.BytesIO(image)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _store(db, project, variant, version, room_id, camera_id, png, ctrl, seg, legend, manifest, g, extra, scene=None) -> m.Document:
    st = get_storage()
    h = hashlib.sha256(png).hexdigest()[:12]
    base = f"projects/{project.id}/renders/{version.id}/{room_id}_{camera_id}_{h}"
    st.put(f"{base}.png", png, "image/png")
    st.put(f"{base}.jpg", _to_jpeg(png), "image/jpeg")
    st.put(f"{base}_control.png", ctrl, "image/png")
    st.put(f"{base}_seg.png", seg, "image/png")
    w, hgt = Image.open(io.BytesIO(png)).size
    doc = m.Document(project_id=project.id, variant_id=variant.id, version_id=version.id, kind="render", lang="", filename=f"render_{room_id}_{h}.jpg",
                     storage_key=f"{base}.jpg", size=len(png), status="ready",
                     meta={"room_id": room_id, "camera_id": camera_id, "png_key": f"{base}.png", "control_key": f"{base}_control.png", "seg_key": f"{base}_seg.png",
                           "legend": legend, "manifest": manifest, "grounding": g, "width": w, "height": hgt, **extra})
    db.add(doc)
    db.commit()
    return doc


def latest_renders(db: Session, version_id: str) -> dict[str, list[m.Document]]:
    out: dict[str, list[m.Document]] = {}
    for d in db.scalars(select(m.Document).where(m.Document.version_id == version_id, m.Document.kind == "render").order_by(m.Document.created_at.desc())):
        out.setdefault(d.meta.get("room_id", ""), []).append(d)
    return out
