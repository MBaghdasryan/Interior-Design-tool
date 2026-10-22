"""Synthetic floor-plan dataset with exact ground truth (rooms, areas, doors, windows,
scale). Layout templates are rectangle partitions, scaled per sample, drawn like an
architect's plan (thick exterior walls, door arcs, window double lines, room names and
areas in hy/ru/en, one overall dimension string) and degraded in six quality modes.

    python -m evals.plans out_dir        # writes plan_XX.png + plan_XX.json (deterministic)
"""
from __future__ import annotations

import io
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
NAMES = {
    "living": {"ru": "Гостиная", "hy": "Հյուրասենյակ", "en": "Living room"}, "kitchen": {"ru": "Кухня", "hy": "Խոհանոց", "en": "Kitchen"},
    "bedroom": {"ru": "Спальня", "hy": "Ննջասենյակ", "en": "Bedroom"}, "kids": {"ru": "Детская", "hy": "Մանկական", "en": "Kids room"},
    "bathroom": {"ru": "Санузел", "hy": "Սանհանգույց", "en": "Bathroom"}, "hallway": {"ru": "Прихожая", "hy": "Նախասենյակ", "en": "Hallway"},
    "wc": {"ru": "Туалет", "hy": "Զուգարան", "en": "WC"}, "kitchen_living": {"ru": "Кухня-гостиная", "hy": "Խոհանոց-հյուրասենյակ", "en": "Kitchen-living"},
}
UNIT = {"ru": "м²", "hy": "մ²", "en": "m²"}
# templates: rooms as (type, x0, y0, x1, y1) on a 0..1 grid of the outer rectangle
TEMPLATES = [
    [("kitchen_living", 0, 0, .62, .6), ("bedroom", .62, 0, 1, .6), ("hallway", 0, .6, .45, 1), ("bathroom", .45, .6, .7, 1), ("kids", .7, .6, 1, 1)],
    [("living", 0, 0, .55, .55), ("kitchen", .55, 0, 1, .4), ("bedroom", .55, .4, 1, 1), ("hallway", 0, .55, .35, 1), ("bathroom", .35, .55, .55, 1)],
    [("kitchen_living", 0, 0, 1, .5), ("hallway", 0, .5, .3, 1), ("bathroom", .3, .5, .55, .78), ("wc", .3, .78, .55, 1), ("bedroom", .55, .5, 1, 1)],
    [("living", 0, 0, .5, .5), ("bedroom", .5, 0, 1, .5), ("kitchen", 0, .5, .35, 1), ("hallway", .35, .5, .65, 1), ("bathroom", .65, .5, 1, .75), ("wc", .65, .75, 1, 1)],
    [("kitchen_living", 0, 0, .7, 1), ("bathroom", .7, 0, 1, .4), ("hallway", .7, .4, 1, 1)],
    [("living", 0, 0, .4, .6), ("kitchen", .4, 0, .7, .45), ("bedroom", .7, 0, 1, .6), ("hallway", .4, .45, .7, 1), ("bathroom", 0, .6, .4, 1), ("kids", .7, .6, 1, 1)],
]
QUALITIES = ["clean", "low_res", "noisy_blur", "rotated", "no_area_labels", "photo_skew"]
WINDOW_ROOMS = {"living", "kitchen", "bedroom", "kids", "kitchen_living"}


def make(idx: int) -> tuple[bytes, dict]:
    rnd = random.Random(1000 + idx)
    tpl = TEMPLATES[idx % len(TEMPLATES)]
    lang = ["ru", "hy", "en"][idx % 3]
    quality = QUALITIES[(idx // 5) % len(QUALITIES)]  # 5 plans per quality mode
    W, H = rnd.randint(78, 115) * 100, rnd.randint(58, 85) * 100  # outer interior size, mm
    rooms = []
    for t, a, b, c, d in tpl:
        x0, y0, x1, y1 = round(a * W), round(b * H), round(c * W), round(d * H)
        rooms.append({"type": t, "rect": [x0, y0, x1, y1], "area_m2": round((x1 - x0) * (y1 - y0) / 1e6, 1)})
    s = 900 / max(W, H)  # px per mm
    M = 90
    img = Image.new("RGB", (int(W * s) + 2 * M, int(H * s) + 2 * M), "white")
    d = ImageDraw.Draw(img)
    big, small = ImageFont.truetype(FONT, 18), ImageFont.truetype(FONT, 14)

    def P(x, y):
        return (M + x * s, M + y * s)
    for r in rooms:  # interior partitions
        x0, y0, x1, y1 = r["rect"]
        d.rectangle([P(x0, y0), P(x1, y1)], outline="black", width=5)
    d.rectangle([P(0, 0), P(W, H)], outline="black", width=12)  # exterior walls
    doors = windows = 0
    for r in rooms:  # one door per room on a shared interior edge, windows on exterior edges
        x0, y0, x1, y1 = r["rect"]
        if r["type"] != "hallway":
            for e in ((x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)):
                ex = e[0] == e[2] and e[0] in (0, W) or e[1] == e[3] and e[1] in (0, H)
                if ex:
                    continue
                horiz = e[1] == e[3]
                L = (e[2] - e[0]) if horiz else (e[3] - e[1])
                if L < 1200:
                    continue
                off = rnd.randint(200, int(L - 1000))
                if horiz:
                    a, b = P(e[0] + off, e[1]), P(e[0] + off + 850, e[1])
                    d.line([a, b], fill="white", width=7)
                    d.arc([a[0], a[1] - 850 * s, a[0] + 1700 * s, a[1] + 850 * s], 270, 360, fill="black", width=2)
                else:
                    a, b = P(e[0], e[1] + off), P(e[0], e[1] + off + 850)
                    d.line([a, b], fill="white", width=7)
                    d.arc([a[0] - 850 * s, a[1], a[0] + 850 * s, a[1] + 1700 * s], 0, 90, fill="black", width=2)
                doors += 1
                break
        if r["type"] in WINDOW_ROOMS:
            for e in ((x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)):
                if not (e[1] == e[3] and e[1] in (0, H) or e[0] == e[2] and e[0] in (0, W)):
                    continue
                horiz = e[1] == e[3]
                L = (e[2] - e[0]) if horiz else (e[3] - e[1])
                if L < 1600:
                    continue
                mid = L / 2
                if horiz:
                    a, b = P(e[0] + mid - 700, e[1]), P(e[0] + mid + 700, e[1])
                    d.line([a, b], fill="white", width=13)
                    d.line([(a[0], a[1] - 4), (b[0], b[1] - 4)], fill="black", width=2)
                    d.line([(a[0], a[1] + 4), (b[0], b[1] + 4)], fill="black", width=2)
                else:
                    a, b = P(e[0], e[1] + mid - 700), P(e[0], e[1] + mid + 700)
                    d.line([a, b], fill="white", width=13)
                    d.line([(a[0] - 4, a[1]), (b[0] - 4, b[1])], fill="black", width=2)
                    d.line([(a[0] + 4, a[1]), (b[0] + 4, b[1])], fill="black", width=2)
                windows += 1
                break
        cx, cy = P((x0 + x1) / 2, (y0 + y1) / 2)
        d.text((cx, cy - 10), NAMES[r["type"]][lang], fill="black", font=big, anchor="mm")
        if quality != "no_area_labels":
            d.text((cx, cy + 14), f"{r['area_m2']:.1f} {UNIT[lang]}".replace(".", "," if lang == "ru" else "."), fill="black", font=small, anchor="mm")
    # overall dimension string above the plan (the scale reference)
    d.line([P(0, -450), P(W, -450)], fill="black", width=1)
    for x in (0, W):
        d.line([P(x, -600), P(x, -300)], fill="black", width=1)
    d.text(P(W / 2, -620), f"{W:,}".replace(",", " "), fill="black", font=small, anchor="ms")
    img = _degrade(img, quality, rnd)
    buf = io.BytesIO()
    img.save(buf, "PNG" if quality != "photo_skew" else "JPEG", quality=70)
    truth = {"id": f"plan_{idx + 1:02d}", "lang": lang, "quality": quality, "width_mm": W, "height_mm": H, "rooms": rooms,
             "doors": doors, "windows": windows, "dimension_text": str(W), "total_area_m2": round(sum(r["area_m2"] for r in rooms), 1),
             "mime": "image/jpeg" if quality == "photo_skew" else "image/png"}
    return buf.getvalue(), truth


def _degrade(img: Image.Image, q: str, rnd: random.Random) -> Image.Image:
    if q == "low_res":
        w, h = img.size
        return img.resize((w // 3, h // 3)).resize((w, h))
    if q == "noisy_blur":
        img = img.filter(ImageFilter.GaussianBlur(1.6))
        px = img.load()
        for _ in range(img.size[0] * img.size[1] // 25):
            x, y = rnd.randrange(img.size[0]), rnd.randrange(img.size[1])
            v = rnd.randint(90, 200)
            px[x, y] = (v, v, v)
        return img
    if q == "rotated":
        return img.rotate(90, expand=True, fillcolor="white")
    if q == "photo_skew":
        w, h = img.size
        bg = Image.new("RGB", (w + 120, h + 120), (205, 196, 182))
        bg.paste(img.rotate(3, expand=False, fillcolor="white"), (60, 60))
        return bg.transform(bg.size, Image.Transform.PERSPECTIVE, (1.03, 0.04, -30, 0.01, 1.02, -20, 0.00004, 0.00002), fillcolor=(205, 196, 182))
    return img


def build(out: Path, n: int = 30) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    truths = []
    for i in range(n):
        data, truth = make(i)
        ext = "jpg" if truth["mime"] == "image/jpeg" else "png"
        (out / f"{truth['id']}.{ext}").write_bytes(data)
        (out / f"{truth['id']}.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
        truths.append(truth)
    return truths


if __name__ == "__main__":
    t = build(Path(sys.argv[1] if len(sys.argv) > 1 else "evals/datasets/plans"))
    print(len(t), "plans;", {q: sum(1 for x in t if x["quality"] == q) for q in QUALITIES})
