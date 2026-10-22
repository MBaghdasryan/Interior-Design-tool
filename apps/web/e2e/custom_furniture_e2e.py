"""E2E (P2-5): a designer builds a kitchen from modules, sees validation against production
ranges, «price on request» without manufacturer rates, a new spec version per save, and gets the PDF
drawing; ordering is disabled below Production Ready. Run against the compose stack."""
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
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    ctx.request.post(B + "/api/v1/auth/login", data={"email": "designer@forma.local", "password": "demo1234"})
    demo = next(x for x in ctx.request.get(B + "/api/v1/projects").json() if x["title"].startswith("Демо"))
    pg.goto(B + "/app")
    pg.get_by_role("button", name="Eng").first.click()
    pg.goto(B + f"/app/p/{demo['id']}/custom")
    pg.wait_for_selector("#cst-ed")
    pg.get_by_role("textbox", name="Name").fill("E2E kitchen")
    pg.get_by_role("button", name="Add module").click()
    pg.get_by_role("button", name="Add module").click()
    pg.get_by_role("textbox", name="Width").nth(1).fill("2000")  # out of range
    pg.get_by_role("button", name="Save and check").click()
    pg.wait_for_selector("#cst-res")
    check("allowed 300–1000 mm" in pg.inner_text("#cst-res") or "Width: allowed" in pg.inner_text("body"), "out-of-range width reported")
    pg.get_by_role("textbox", name="Width").nth(1).fill("600")
    pg.get_by_role("button", name="Save and check").click()
    pg.wait_for_timeout(800)
    body = pg.inner_text("body")
    check("Check and price (version 2)" in body, "second save creates spec version 2")
    check("No price is invented" in body, "no manufacturer rates → price on request")
    if demo.get("accuracy_level") != "production":
        check(pg.get_by_role("button", name="Order from the manufacturer").is_disabled(), "ordering disabled below Production Ready")
    pdf = ctx.request.get(B + pg.get_by_role("link", name="PDF").get_attribute("href"))
    check(pdf.status == 200 and pdf.body()[:5] == b"%PDF-", "PDF drawing downloads")
    pg.screenshot(path=f"{OUT}/custom_furniture.png", full_page=True)
    cid = next(c["id"] for c in ctx.request.get(B + f"/api/v1/projects/{demo['id']}/custom").json() if c["name"] == "E2E kitchen")
    csrf = next(c["value"] for c in ctx.cookies() if c["name"] == "forma_csrf")
    check(ctx.request.delete(B + f"/api/v1/projects/{demo['id']}/custom/{cid}", headers={"X-CSRF-Token": csrf}).ok, "configuration deleted (cleanup)")
    pg.get_by_role("button", name="Рус").first.click()
    pg.wait_for_timeout(300)
    check(not errs, f"no JS errors {errs[:2]}")
    b.close()
print("FAILURES:", failures) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
