"""E2E (P2-4): smart (multilingual) catalogue search finds sofas for an Armenian query, the honest
«not a neural model» label is shown with the local provider, and the analogs dialog explains its ranking.
Needs a built index (CI: POST /admin/search/reindex runs inline from this script)."""
import os
import sys

from playwright.sync_api import sync_playwright

B = os.environ.get("BASE", "http://localhost:8085")
OUT = os.environ.get("OUT", "/tmp")
failures: list[str] = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


with sync_playwright() as p:
    b = p.chromium.launch()
    adm = b.new_context()
    adm.request.post(B + "/api/v1/auth/login", data={"email": "admin@forma.local", "password": "demo1234"})
    csrf = next(c["value"] for c in adm.cookies() if c["name"] == "forma_csrf")
    adm.request.post(B + "/api/v1/admin/search/reindex", headers={"X-CSRF-Token": csrf})
    adm.close()
    ctx = b.new_context(viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    ctx.request.post(B + "/api/v1/auth/login", data={"email": "designer@forma.local", "password": "demo1234"})
    for _ in range(30):  # the reindex job may run on the worker
        if ctx.request.get(B + "/api/v1/catalog/search/status").json()["indexed"]["text"] > 0:
            break
        pg.wait_for_timeout(1000)
    pg.goto(B + "/app/catalog")
    pg.get_by_role("button", name="Eng").first.click()
    pg.get_by_role("button", name="Smart").click()
    pg.get_by_role("textbox", name="Search").fill("բազմոց")
    pg.wait_for_timeout(1500)
    body = pg.inner_text("body")
    check("Not a neural model" in body, "honest label for the local lexical provider")
    first = pg.locator(".grid.g4 .card").first.inner_text()
    check("Sofa" in first, f"Armenian query finds sofas first ({first[:40]!r})")
    pg.locator(".grid.g4 .card").first.get_by_role("button", name="Analogs").click()
    pg.wait_for_selector(".modal")
    txt = pg.inner_text(".modal")
    check("description" in txt and "size" in txt and "%" in txt, "analogs dialog shows the ranking components")
    pg.screenshot(path=f"{OUT}/search_analogs.png")
    pg.get_by_role("button", name="Close").click()
    pg.get_by_role("button", name="Рус").first.click()
    pg.wait_for_timeout(300)
    check(not errs, f"no JS errors {errs[:2]}")
    b.close()
print("FAILURES:", failures) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
