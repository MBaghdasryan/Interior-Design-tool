"""Real-plan evaluation set built from a real apartment album (PDF, not committed: client data).
Six plan sheets of one apartment, cropped to the drawing (the title block AND the room
schedule are cut away, so the model cannot copy the answers). Ground truth = the album's
room schedule (explication).

    python -m evals.real_plans "<album.pdf>" evals/datasets/real
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# «Պարույր Սևակ 5» measured-plan schedule (sheet ԴՆ1.1): hallway, bathroom, bedroom, living room, kitchen
TRUTH_ROOMS = [("hallway", 7.79), ("bathroom", 5.76), ("bedroom", 15.20), ("living", 18.01), ("kitchen", 11.37)]
SHEETS = {3: "measured", 4: "demolition", 5: "new_elements", 7: "zoning", 17: "floors", 21: "furniture"}
CROP = (0.03, 0.05, 0.676, 0.95)  # fraction of the page: drawing area left of the schedule table and title block


def build(pdf: str, out: Path) -> list[dict]:
    import pymupdf

    out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    truths = []
    for page_no, kind in SHEETS.items():
        page = doc[page_no - 1]
        r = page.rect
        clip = pymupdf.Rect(r.x0 + r.width * CROP[0], r.y0 + r.height * CROP[1], r.x0 + r.width * CROP[2], r.y0 + r.height * CROP[3])
        png = page.get_pixmap(dpi=150, clip=clip).tobytes("png")
        pid = f"real_{page_no:02d}_{kind}"
        (out / f"{pid}.png").write_bytes(png)
        truth = {"id": pid, "lang": "hy", "quality": f"real:{kind}", "rooms": [{"type": t, "area_m2": a} for t, a in TRUTH_ROOMS],
                 "total_area_m2": round(sum(a for _, a in TRUTH_ROOMS), 2), "doors": None, "windows": None, "mime": "image/png"}
        (out / f"{pid}.json").write_text(json.dumps(truth, ensure_ascii=False, indent=1), encoding="utf-8")
        truths.append(truth)
    return truths


if __name__ == "__main__":
    print(len(build(sys.argv[1], Path(sys.argv[2] if len(sys.argv) > 2 else "evals/datasets/real"))), "real plan sheets")
