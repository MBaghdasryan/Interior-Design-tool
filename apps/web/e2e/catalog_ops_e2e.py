"""E2E (P1-7): admin opens a source's connector history (runs, alerts, schedule); a supplier
configures the scheduled price feed (https only) in the cabinet. Run against the compose stack."""
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
    for email in ("admin@forma.local", "supplier@forma.local"):
        ctx = b.new_context(viewport={"width": 1366, "height": 900})
        pg = ctx.new_page()
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
        ctx.request.post(B + "/api/v1/auth/login", data={"email": email, "password": "demo1234"})
        pg.goto(B + "/app")
        pg.get_by_role("button", name="Eng").first.click()
        if email.startswith("admin"):
            pg.goto(B + "/app/admin")
            row = pg.locator("tr", has_text="VLV Centre").first
            row.get_by_role("button", name="History").click()
            pg.wait_for_selector("text=Alerts")
            txt = pg.inner_text("body")
            check("Indexing every 30 min" in txt and "Price TTL" in txt, "admin: VLV history shows the schedule and TTL")
            pg.screenshot(path=f"{OUT}/admin_history.png", full_page=True)
        else:
            pg.goto(B + "/app/supplier")
            pg.wait_for_selector("#feed-h")
            url = pg.locator("input[type=url]")
            url.fill("http://insecure.example.com/p.csv")
            pg.get_by_role("button", name="Save").click()
            pg.wait_for_timeout(600)
            check("feed settings saved" not in pg.inner_text("body").lower(), "supplier: plain-http feed URL refused")
            url.fill("https://feeds.example.com/price.csv")
            pg.get_by_role("button", name="Save").click()
            pg.wait_for_selector("text=Feed settings saved")
            check(True, "supplier: https feed URL saved")
            pg.screenshot(path=f"{OUT}/supplier_feed.png", full_page=True)
            ctx.request.put(B + "/api/v1/supplier/feed", data={"enabled": False, "url": ""},
                            headers={"X-CSRF-Token": next(c["value"] for c in ctx.cookies() if c["name"] == "forma_csrf")})
        pg.get_by_role("button", name="Рус").first.click()  # restore the demo user's language
        pg.wait_for_timeout(300)
        check(not errs, f"{email}: no JS errors {errs[:2]}")
        ctx.close()
    b.close()
print("FAILURES:", failures) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
