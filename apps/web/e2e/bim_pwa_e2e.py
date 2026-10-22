"""E2E (P2-6): the geometry page offers IFC4 export (downloads a valid STEP file) and RoomPlan import;
the app is installable (manifest + service worker registered). Read-only: no geometry is changed."""
import os
import sys

from playwright.sync_api import sync_playwright

B = os.environ.get("BASE", "http://localhost:8085")
failures: list[str] = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    ctx.request.post(B + "/api/v1/auth/login", data={"email": "designer@forma.local", "password": "demo1234"})
    demo = next(x for x in ctx.request.get(B + "/api/v1/projects").json() if x["title"].startswith("Демо"))
    pg.goto(B + "/app")
    pg.get_by_role("button", name="Eng").first.click()
    pg.goto(B + f"/app/p/{demo['id']}/geometry")
    pg.wait_for_selector("text=Export IFC4")
    href = pg.get_by_role("link", name="Export IFC4").get_attribute("href")
    ifc = ctx.request.get(B + href)
    check(ifc.status == 200 and ifc.body().startswith(b"ISO-10303-21") and b"IFCWALL" in ifc.body(), "IFC4 export downloads a STEP file with walls")
    check(pg.get_by_text("Import a RoomPlan scan (JSON)").count() == 1, "RoomPlan import offered")
    man = ctx.request.get(B + "/manifest.webmanifest")
    check(man.status == 200 and man.json()["display"] == "standalone", "web app manifest served")
    for _ in range(20):
        if pg.evaluate("navigator.serviceWorker.getRegistrations().then(r => r.length)"):
            break
        pg.wait_for_timeout(500)
    check(pg.evaluate("navigator.serviceWorker.getRegistrations().then(r => r.length)") >= 1, "service worker registered")
    pg.get_by_role("button", name="Рус").first.click()
    pg.wait_for_timeout(300)
    check(not errs, f"no JS errors {errs[:2]}")
    b.close()
print("FAILURES:", failures) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
