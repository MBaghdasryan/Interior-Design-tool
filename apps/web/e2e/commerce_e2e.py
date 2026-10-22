"""E2E (P2-1/P2-2): platform Finance tab (ledger reconciliation, «Integration pending», tariffs,
commission/tax rules), supplier cabinet orders section, procurement page. Nothing here records money:
the ledger is append-only, so the E2E only reads it. Run against the compose stack."""
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
    for email in ("admin@forma.local", "supplier@forma.local", "designer@forma.local"):
        ctx = b.new_context(viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
        ctx.request.post(B + "/api/v1/auth/login", data={"email": email, "password": "demo1234"})
        csrf = next(c["value"] for c in ctx.cookies() if c["name"] == "forma_csrf")
        pg.goto(B + "/app")
        pg.get_by_role("button", name="Eng").first.click()
        pg.wait_for_timeout(300)
        if email.startswith("admin"):
            pg.goto(B + "/app/admin")
            pg.get_by_role("button", name="Finance").click()
            pg.wait_for_selector("#fin-ledger")
            txt = pg.inner_text("body")
            check("Balanced" in txt and "Payments match cash" in txt, "admin: ledger reconciles")
            check("Online payment: Integration pending" in txt, "admin: no provider → Integration pending (no fake payments)")
            before = ctx.request.get(B + "/api/v1/admin/tariffs").json()
            pg.get_by_role("button", name="Add a plan").click()
            pg.locator("section[aria-labelledby=fin-tariffs]").get_by_role("textbox", name="Name").last.fill("E2E plan")
            pg.locator("section[aria-labelledby=fin-tariffs]").get_by_role("button", name="Save").click()
            pg.wait_for_timeout(600)
            after = ctx.request.get(B + "/api/v1/admin/tariffs").json()
            check(any(x["name"] == "E2E plan" for x in after["bureau_plans"]), "admin: tariff plan saved")
            ctx.request.put(B + "/api/v1/admin/tariffs", data=before, headers={"X-CSRF-Token": csrf})  # restore
            pg.screenshot(path=f"{OUT}/finance.png", full_page=True)
        elif email.startswith("supplier"):
            pg.goto(B + "/app/supplier")
            pg.wait_for_selector("#sord-h")
            check("Orders" in pg.inner_text("#sord-h"), "supplier: orders section rendered")
        else:
            tok_projects = ctx.request.get(B + "/api/v1/projects").json()
            demo = next(x for x in tok_projects if x["title"].startswith("Демо"))
            pg.goto(B + f"/app/p/{demo['id']}/procurement")
            pg.wait_for_timeout(1500)
            check("Carts" in pg.inner_text("body") or "carts" in pg.inner_text("body").lower(), "designer: procurement page rendered")
        pg.get_by_role("button", name="Рус").first.click()
        pg.wait_for_timeout(300)
        check(not errs, f"{email}: no JS errors {errs[:2]}")
        ctx.close()
    b.close()
print("FAILURES:", failures) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
