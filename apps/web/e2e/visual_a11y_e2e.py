"""E2E (P1-9): visual regression of the public pages (hy/ru/en) against committed baselines and an
axe-core accessibility audit of the main app routes (no serious/critical violations).

    UPDATE=1 python visual_a11y_e2e.py     # re-record baselines (review the PNG diff in git)
Baselines are recorded in the pinned Playwright image (fonts and rendering are deterministic there)."""
import json
import os
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from axe_playwright_python.sync_playwright import Axe
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

B = os.environ.get("BASE", "http://localhost:8085")
OUT = Path(os.environ.get("OUT", "/tmp"))
BASE_DIR = Path(__file__).parent / "visual"
UPDATE = os.environ.get("UPDATE") == "1"
MAX_DIFF = 0.004  # share of pixels allowed to differ (anti-aliasing noise)
failures: list[str] = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def diff_ratio(a: bytes, b: bytes) -> tuple[float, Image.Image | None]:
    ia, ib = Image.open(BytesIO(a)).convert("RGB"), Image.open(BytesIO(b)).convert("RGB")
    if ia.size != ib.size:
        return 1.0, None
    d = ImageChops.difference(ia, ib).convert("L").point(lambda v: 255 if v > 24 else 0)
    return sum(d.histogram()[255:]) / (ia.size[0] * ia.size[1]), d


def api(path, data=None, tok=None):
    r = urllib.request.Request(B + "/api/v1" + path, data=json.dumps(data).encode() if data is not None else None, method="POST" if data is not None else "GET",
                               headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    return json.loads(urllib.request.urlopen(r).read())


with sync_playwright() as p:
    b = p.chromium.launch()
    # ---------------------------------------------------------------- visual regression
    BASE_DIR.mkdir(exist_ok=True)
    pg = b.new_page(viewport={"width": 1280, "height": 800}, device_scale_factor=1)
    for route in ("/", "/login", "/register", "/forgot-password"):
        for lang in ("hy", "ru", "en"):
            pg.goto(B + route)
            pg.evaluate(f"localStorage.setItem('forma.lang', '{lang}')")
            pg.reload()
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(400)
            # live data (showcase scene, KPI numbers) is masked: baselines must not depend on the database
            shot = pg.screenshot(animations="disabled", caret="hide", mask=[pg.locator("canvas, .skeleton, .kpi .v")])
            name = f"{route.strip('/') or 'landing'}_{lang}.png"
            ref = BASE_DIR / name
            if UPDATE or not ref.exists():
                ref.write_bytes(shot)
                print("RECORDED", name)
                continue
            ratio, d = diff_ratio(ref.read_bytes(), shot)
            if ratio > MAX_DIFF:
                (OUT / f"actual_{name}").write_bytes(shot)
                if d:
                    d.save(OUT / f"diff_{name}")
            check(ratio <= MAX_DIFF, f"visual {name}: {ratio:.4%} pixels differ")
    pg.close()

    # ---------------------------------------------------------------- accessibility (axe-core)
    axe = Axe()
    tok = api("/auth/login", {"email": "designer@forma.local", "password": "demo1234"})["token"]
    demo = next(x for x in api("/projects", tok=tok) if x["title"].startswith("Демо"))
    plan = [
        (None, ["/", "/login", "/register", "/forgot-password", f"/client/{demo['share_token']}"]),
        ("designer@forma.local", ["/app", "/app/projects", "/app/new", "/app/catalog", "/app/suppliers", "/app/account", f"/app/p/{demo['id']}",
                                  f"/app/p/{demo['id']}/procurement", f"/app/p/{demo['id']}/documents"]),
        ("supplier@forma.local", ["/app/supplier"]),
        ("admin@forma.local", ["/app/admin", "/app/pim"]),
    ]
    for email, routes in plan:
        ctx = b.new_context(viewport={"width": 1366, "height": 900}, bypass_csp=True)  # the axe script is injected
        if email:
            ctx.request.post(B + "/api/v1/auth/login", data={"email": email, "password": "demo1234"})
        pg = ctx.new_page()
        for r in routes:
            pg.goto(B + r)
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(800)
            res = axe.run(pg, options={"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa"]}})
            bad = [v for v in res.response["violations"] if v["impact"] in ("serious", "critical")]
            detail = "; ".join(f"{v['id']}×{len(v['nodes'])} e.g. {v['nodes'][0]['target']}" for v in bad)
            check(not bad, f"a11y {email or 'anon'} {r}: {detail or 'no serious/critical violations'}")
        ctx.close()
    b.close()
print("FAILURES:", len(failures)) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
