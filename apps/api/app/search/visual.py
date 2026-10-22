"""Local visual descriptor for «similar by photo» (P2-4): HSV colour histogram (8×4×4) plus
gradient-orientation histogram (16 bins, texture/shape cue). No neural model — it finds products
that LOOK alike in colour and texture, not semantically equal objects; the UI labels it as such."""
from __future__ import annotations

import io
import math

from PIL import Image, ImageFilter


def describe(data: bytes) -> list[float]:
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((256, 256))
    hsv = im.convert("HSV")
    hist = [0.0] * 128
    for h, s, v in hsv.getdata():
        hist[(h * 8 // 256) * 16 + (s * 4 // 256) * 4 + (v * 4 // 256)] += 1
    g = im.convert("L")
    gx = g.filter(ImageFilter.Kernel((3, 3), (-1, 0, 1, -2, 0, 2, -1, 0, 1), 1, 128))
    gy = g.filter(ImageFilter.Kernel((3, 3), (-1, -2, -1, 0, 0, 0, 1, 2, 1), 1, 128))
    ori = [0.0] * 16
    for a, b in zip(gx.getdata(), gy.getdata(), strict=True):
        dx, dy = a - 128, b - 128
        mag = math.hypot(dx, dy)
        if mag > 8:
            ori[int((math.atan2(dy, dx) + math.pi) / (2 * math.pi) * 16) % 16] += mag
    def norm(x):
        n = math.sqrt(sum(t * t for t in x)) or 1.0
        return [t / n for t in x]
    return norm(norm(hist) + [0.5 * t for t in norm(ori)])
