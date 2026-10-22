"""Photo survey pipeline (P1-6): independent steps, each behind its own task/provider
routing so a step can move to a specialised model without touching the others:

1. room classification (vision LLM)     → task photo_rooms
2. elements & finishes (vision LLM)      → task photo_elements
3. depth estimation                      → DepthProvider (none configured → step reported as unavailable)
4. multi-view matching (vision LLM)      → task view_groups

Metric geometry is never derived from photos alone: without a plan or a control dimension
the scene gets placeholder rooms marked as assumptions with confidence 0.2."""
from __future__ import annotations

import io

from PIL import Image
from sqlalchemy.orm import Session

from ..ai.orchestrator import get_orchestrator
from ..ai.providers import ImageInput
from ..scene.model import Assumption, Room, Scene

MAX_PHOTOS = 12


class DepthProvider:
    """Monocular depth (e.g. Depth Anything / ZoeDepth worker). Not deployed: available() is False."""

    name = "none"

    def available(self) -> bool:
        return False

    def estimate(self, image: bytes) -> dict:  # pragma: no cover - boundary
        raise NotImplementedError


def _thumb(data: bytes, mime: str) -> ImageInput:
    try:
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((1280, 1280))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return ImageInput(buf.getvalue(), "image/jpeg")
    except Exception:  # noqa: BLE001 - videos / unsupported: pass through
        return ImageInput(data, mime)


def survey(db: Session, project_id: str, photos: list[tuple[str, bytes, str]], depth: DepthProvider | None = None) -> dict:
    """photos: [(asset_id, bytes, mime)] → per-photo results, room groups, step status."""
    photos = photos[:MAX_PHOTOS]
    images = [_thumb(b, mime) for _, b, mime in photos]
    orch = get_orchestrator()
    steps: dict[str, dict] = {}
    rooms, p1 = orch.run("photo_rooms", {"count": len(images)}, db=db, project_id=project_id, images=images, stub_on_quota=True)
    steps["classification"] = {"provider": p1}
    elements, p2 = orch.run("photo_elements", {"count": len(images)}, db=db, project_id=project_id, images=images, stub_on_quota=True)
    steps["elements"] = {"provider": p2}
    depth = depth or DepthProvider()
    steps["depth"] = {"provider": depth.name, "available": depth.available(),
                      "note": "monocular depth model not deployed — metric size needs a plan or a control dimension"}
    groups, p3 = orch.run("view_groups", {"photos": [r.model_dump() for r in rooms.photos]}, db=db, project_id=project_id, images=images, stub_on_quota=True)
    steps["view_matching"] = {"provider": p3}
    by_index = {e.index: e for e in elements.photos}
    out_photos = []
    for i, (asset_id, _, _) in enumerate(photos):
        cls = next((r for r in rooms.photos if r.index == i), None)
        el = by_index.get(i)
        out_photos.append({"asset_id": asset_id, "index": i, "room_type": cls.room_type if cls else "unknown", "confidence": cls.confidence if cls else 0,
                           **({k: v for k, v in el.model_dump().items() if k != "index"} if el else {})})
    heights = [p["ceiling_height_mm_estimate"] for p in out_photos if p.get("ceiling_height_mm_estimate")]
    return {"photos": out_photos, "rooms": [g.model_dump() for g in groups.rooms], "uncertainties": groups.uncertainties, "steps": steps,
            "ceiling_height_estimate_mm": round(sorted(heights)[len(heights) // 2]) if heights else None}


def scene_from_survey(s: dict) -> Scene:
    """Rooms without geometry: placeholders laid in a row, flagged so the designer draws the plan."""
    rooms, x = [], 0.0
    for i, g in enumerate([g for g in s["rooms"] if g["room_type"] != "unknown"], 1):
        rid = f"R{i}"
        rooms.append(Room(id=rid, number=i, type=g["room_type"], name=g["room_type"], polygon=[(x, 0), (x + 3000, 0), (x + 3000, 3000), (x, 3000)],
                          source="assumed", confidence=0.2))
        x += 3200
    sc = Scene(name="По фотографиям (без геометрии)", rooms=rooms, ceiling_height=s.get("ceiling_height_estimate_mm") or 2700)
    sc.assumptions.append(Assumption(key="photos_only", severity="critical",
                                     text=f"Помещения определены по {len(s['photos'])} фото; размеры — условные квадраты 3×3 м. Загрузите план или постройте стены и задайте контрольный размер"))
    if s.get("ceiling_height_estimate_mm"):
        sc.assumptions.append(Assumption(key="ceiling_from_door", severity="warning",
                                         text=f"Высота потолка ≈{s['ceiling_height_estimate_mm']} мм оценена по двери на фото — измерьте на объекте"))
    sc.assumptions += [Assumption(key=f"pu{i}", severity="warning", text=u) for i, u in enumerate(s.get("uncertainties", [])[:6])]
    return sc
