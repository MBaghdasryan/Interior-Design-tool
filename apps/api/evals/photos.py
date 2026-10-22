"""Synthetic «before renovation» photo set (Gemini Flash Image) with known labels: room type per
photo and which photos show the same room (two views of one living room / one bedroom are made by
editing the first view into the opposite angle). SYNTHETIC — real apartment photos (N99) replace it
when available.

    python -m evals.photos evals/datasets/photos      # needs GEMINI_API_KEY, ~8 images
"""
from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

import httpx

from app.config import get_settings

MODEL = "gemini-3.1-flash-image"
BASE = ("Realistic smartphone photo taken during a site survey of an empty apartment in Yerevan before renovation, "
        "daylight, eye level, no people, no text. ")
SHOTS = [  # (id, room, group, prompt, edit_of)
    ("p01", "living", "g_living", "Large empty living room, plastered white-box walls, concrete screed floor, two windows on the left wall, one radiator under each window, a doorway in the far right corner.", None),
    ("p02", "living", "g_living", "Same room seen from the opposite corner: the two windows with radiators are now on the right side; keep the same walls, floor and windows.", "p01"),
    ("p03", "bedroom", "g_bed1", "Empty bedroom with bare concrete walls and floor, one window with a radiator, a balcony door next to it, electrical boxes on the wall.", None),
    ("p04", "bedroom", "g_bed1", "Same bedroom seen from the balcony door towards the entrance door; keep the same concrete walls and floor.", "p03"),
    ("p05", "kitchen", "g_kitchen", "Small empty kitchen in white-box condition: water pipes and a sewer outlet sticking out of the wall, a gas pipe, one window, tiled floor not yet laid.", None),
    ("p06", "bathroom", "g_bath", "Bare bathroom before renovation: concrete walls, a vertical sewer riser in the corner, water pipe stubs, no fixtures installed.", None),
    ("p07", "hallway", "g_hall", "Narrow entrance hallway of an apartment: the metal entrance door, an electrical panel on the wall, three interior doorways, concrete floor.", None),
    ("p08", "kids", "g_kids", "Small empty child's room in white-box condition with one window and a radiator, light painted walls, laminate not yet laid.", None),
]


def _gen(client: httpx.Client, key: str, prompt: str, ref: bytes | None) -> bytes:
    parts = [{"text": BASE + prompt}] + ([{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(ref).decode()}}] if ref else [])
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "4:3"}}}
    for attempt in range(4):
        r = client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent", json=body, headers={"x-goog-api-key": key})
        if r.status_code == 200:
            part = next(p for p in r.json()["candidates"][0]["content"]["parts"] if "inlineData" in p)
            return base64.b64decode(part["inlineData"]["data"])
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"{r.status_code}: {r.text[:200]}")


def build(out: Path) -> list[dict]:
    from io import BytesIO

    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    key = get_settings().gemini_api_key
    if not key:
        raise SystemExit("GEMINI_API_KEY is required to synthesise the photo set")
    client = httpx.Client(timeout=180)
    made: dict[str, bytes] = {}
    labels = []
    for pid, room, group, prompt, edit_of in SHOTS:
        img = _gen(client, key, prompt, made.get(edit_of) if edit_of else None)
        im = Image.open(BytesIO(img)).convert("RGB")
        im.thumbnail((1280, 1280))
        buf = BytesIO()
        im.save(buf, "JPEG", quality=88)
        made[pid] = buf.getvalue()
        (out / f"{pid}.jpg").write_bytes(made[pid])
        labels.append({"id": pid, "room_type": room, "group": group})
        print("generated", pid, room)
    (out / "labels.json").write_text(json.dumps({"synthetic": True, "model": MODEL, "photos": labels}, indent=1), encoding="utf-8")
    return labels


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "evals/datasets/photos"))
