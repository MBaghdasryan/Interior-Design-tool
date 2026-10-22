"""Geometry control images for photoreal rendering, rasterised from the same scene model
as the album: (1) a shaded schematic perspective from a scene camera — the structural
guide (camera, walls, openings, furniture placement); (2) a flat-colour segmentation map
with a legend (colour → object code) — used for masks and for grounding checks."""
from __future__ import annotations

import colorsys
import io

from PIL import Image, ImageDraw, ImageFilter

from ..album import render3d
from ..scene.model import Camera, Scene

SIZE = (1344, 768)  # 16:9-ish; generated renders keep this aspect ratio
EYE_Z, TARGET_Z, FOV = 1450, 1150, 72


def project(scene: Scene, room_id: str, cam: Camera):
    faces = render3d.room_interior_faces(scene, room_id)
    return render3d.perspective(faces, (cam.position[0], cam.position[1], EYE_Z), (cam.target[0], cam.target[1], TARGET_Z), fov_deg=FOV)


def _xy(pts, size):
    w, h = size
    k = max(w, h) / 2
    return [(w / 2 + x * k, h / 2 - y * k) for x, y in pts]  # projection is y-up, images are y-down


def _object_colors(items) -> dict[str, str]:
    groups = sorted({f.group for _, f in items if f.group})
    out = {}
    for i, g in enumerate(groups):
        r, gg, b = colorsys.hsv_to_rgb((i * 0.618034) % 1.0, 0.85, 0.95)  # well separated hues
        out[g] = "#%02x%02x%02x" % (int(r * 255), int(gg * 255), int(b * 255))
    return out


def control_image(items, size=SIZE) -> bytes:
    img = Image.new("RGB", size, "#f6f2ec")
    d = ImageDraw.Draw(img)
    for pts, f in items:
        xy = _xy(pts, size)
        if len(xy) >= 3:
            d.polygon(xy, fill=f.color, outline=f.stroke or None)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


ENVELOPE = {0: "#3c3c3c", 1: "#9a9a9a", 2: "#5b8fd6"}  # floor/ceiling, walls, openings/rugs


def segmentation(items, scene: Scene, size=SIZE) -> tuple[bytes, dict[str, dict]]:
    colors = _object_colors(items)
    codes = {o.id: o for o in scene.objects}
    img = Image.new("RGB", size, "#000000")
    d = ImageDraw.Draw(img)
    for pts, f in items:
        xy = _xy(pts, size)
        if len(xy) >= 3:
            d.polygon(xy, fill=colors.get(f.group) or ENVELOPE.get(f.layer, "#777777"))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    legend = {c: {"object_id": g, "code": codes[g].code if g in codes else g, "category": codes[g].category if g in codes else ""} for g, c in colors.items()}
    return buf.getvalue(), legend


def visible_objects(seg_png: bytes, legend: dict[str, dict], min_px: int = 400) -> dict[str, dict]:
    """Objects that actually appear in this camera view (pixel count, bbox, horizontal position)."""
    img = Image.open(io.BytesIO(seg_png)).convert("RGB")
    w, h = img.size
    counts: dict[str, list] = {}
    px = img.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            c = "#%02x%02x%02x" % px[x, y]
            if c in legend:
                e = counts.setdefault(c, [0, w, h, 0, 0])
                e[0] += 16
                e[1], e[2], e[3], e[4] = min(e[1], x), min(e[2], y), max(e[3], x), max(e[4], y)
    out = {}
    for c, (n, x0, y0, x1, y1) in counts.items():
        if n >= min_px:
            cx = (x0 + x1) / 2 / w
            out[legend[c]["object_id"]] = {**legend[c], "pixels": n, "bbox": [x0, y0, x1, y1],
                                           "position": "left" if cx < 0.36 else "right" if cx > 0.64 else "center"}
    return out


def mask_for(seg_png: bytes, legend: dict[str, dict], object_ids: set[str], grow_px: int = 24) -> bytes:
    """White where the given objects are (dilated so the new item can differ slightly in size)."""
    from PIL import ImageChops

    img = Image.open(io.BytesIO(seg_png)).convert("RGB")
    mask = Image.new("L", img.size, 0)
    for c, v in legend.items():
        if v["object_id"] not in object_ids:
            continue
        r, g, b = ImageChops.difference(img, Image.new("RGB", img.size, c)).split()
        exact = ImageChops.lighter(ImageChops.lighter(r, g), b)  # 0 only where all three channels match exactly
        mask = ImageChops.lighter(mask, exact.point(lambda d: 255 if d == 0 else 0))
    if grow_px:
        mask = mask.filter(ImageFilter.MaxFilter(grow_px * 2 + 1))
    buf = io.BytesIO()
    mask.save(buf, "PNG")
    return buf.getvalue()


def composite(base_png: bytes, new_png: bytes, mask_png: bytes, feather_px: int = 6) -> bytes:
    """Masked regeneration guarantee: pixels outside the mask are taken from the previous render."""
    base = Image.open(io.BytesIO(base_png)).convert("RGB")
    new = Image.open(io.BytesIO(new_png)).convert("RGB").resize(base.size)
    mask = Image.open(io.BytesIO(mask_png)).convert("L").resize(base.size)
    if feather_px:
        mask = mask.filter(ImageFilter.GaussianBlur(feather_px))
    out = Image.composite(new, base, mask)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()
