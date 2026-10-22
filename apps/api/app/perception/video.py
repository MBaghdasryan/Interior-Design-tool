"""Keyframes from a walkthrough video for the photo survey (P1-6): frames sampled every
`step_s` seconds, blurred frames dropped (edge energy), near-duplicates dropped (32×32 grey
difference), at most `max_frames` kept — spread over the whole video. PyAV (bundled FFmpeg)."""
from __future__ import annotations

import io
import tempfile

from PIL import Image, ImageFilter, ImageStat


def _sharpness(im: Image.Image) -> float:
    return ImageStat.Stat(im.convert("L").resize((320, 180)).filter(ImageFilter.FIND_EDGES)).var[0]


def _sig(im: Image.Image) -> list[int]:
    return list(im.convert("L").resize((32, 32)).getdata())


def keyframes(data: bytes, *, max_frames: int = 8, step_s: float = 2.0, min_diff: float = 18.0) -> list[tuple[float, bytes]]:
    """→ [(time_s, jpeg bytes)]."""
    import av

    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        tmp.write(data)
        tmp.flush()
        with av.open(tmp.name) as box:
            stream = box.streams.video[0]
            stream.codec_context.skip_frame = "NONKEY" if stream.frames and stream.frames > 20000 else "DEFAULT"
            cands, next_t = [], 0.0
            for frame in box.decode(stream):
                t = float(frame.time or 0)
                if t + 1e-6 < next_t:
                    continue
                next_t = t + step_s
                im = frame.to_image()
                im.thumbnail((1280, 1280))
                cands.append((t, im, _sharpness(im)))
    if not cands:
        return []
    sharp = sorted(c[2] for c in cands)
    floor = sharp[len(sharp) // 4]  # drop the blurriest quarter (motion blur while walking)
    kept: list[tuple[float, Image.Image]] = []
    sigs: list[list[int]] = []
    for t, im, s in cands:
        if s < floor:
            continue
        sg = _sig(im)
        if any(sum(abs(a - b) for a, b in zip(sg, o, strict=True)) / len(sg) < min_diff for o in sigs):
            continue
        kept.append((t, im))
        sigs.append(sg)
    if len(kept) > max_frames:  # spread evenly over the walkthrough
        idx = [round(i * (len(kept) - 1) / (max_frames - 1)) for i in range(max_frames)]
        kept = [kept[i] for i in idx]
    out = []
    for t, im in kept:
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=85)
        out.append((round(t, 1), buf.getvalue()))
    return out
