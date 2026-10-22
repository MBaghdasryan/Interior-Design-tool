"""E2E (P1-8): a client comment through the share link → the designer's bell shows an unread
notification in hy/ru/en → clicking it opens the project and clears the counter; the Account page
lists the notification preferences. Run against the compose stack (BASE, default http://localhost:8085)."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

B = os.environ.get("BASE", "http://localhost:8085")
OUT = os.environ.get("OUT", "/tmp")
failures: list[str] = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def api(path, data=None, tok=None):
    r = urllib.request.Request(B + "/api/v1" + path, data=json.dumps(data).encode() if data is not None else None, method="POST" if data is not None else "GET",
                               headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    return json.loads(urllib.request.urlopen(r).read())


tok = api("/auth/login", {"email": "designer@forma.local", "password": "demo1234"})["token"]
api("/notifications/read-all", {}, tok)
demo = next(p for p in api("/projects", tok=tok) if p["title"].startswith("Демо"))
vid = api(f"/projects/{demo['id']}/variants", tok=tok)[0]["id"]
api(f"/client/{demo['share_token']}/comments", {"name": "Anna E2E", "body": "e2e", "variant_id": vid})
check(api("/notifications", tok=tok)["unread"] >= 1, "client comment created an unread notification")

EXPECT = {"en": "Anna E2E left a comment", "ru": "Anna E2E оставил(а) комментарий", "hy": "Anna E2E-ը թողել է մեկնաբանություն"}
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1366, "height": 900})
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    pg.context.request.post(B + "/api/v1/auth/login", data={"email": "designer@forma.local", "password": "demo1234"})
    pg.goto(B + "/app")
    pg.wait_for_selector(".notif-btn")
    for lang, label in (("hy", "Հայ"), ("en", "Eng"), ("ru", "Рус")):  # ends on the demo user's own language
        pg.get_by_role("button", name=label).first.click()
        pg.wait_for_timeout(300)
        pg.wait_for_selector(".notif-count", timeout=8000)
        pg.click(".notif-btn")
        pg.wait_for_selector(".notif-panel")
        txt = pg.inner_text(".notif-panel")
        check(EXPECT[lang] in txt, f"[{lang}] bell shows the localised comment notification")
        pg.screenshot(path=f"{OUT}/notif_{lang}.png")
        pg.keyboard.press("Escape")
    pg.click(".notif-btn")
    pg.click(".notif-item.unread")
    pg.wait_for_url(f"**/app/p/{demo['id']}**", timeout=8000)
    check(True, "clicking the notification opens the project")
    pg.wait_for_timeout(800)
    check(pg.locator(".notif-count").count() == 0, "counter cleared after reading")
    pg.goto(B + "/app/account")
    pg.wait_for_selector("#notifications")
    check(pg.locator("#notifications [role=switch]").count() == 9, "Account lists 8 kinds + digest switch")
    check(not errs, f"no JS errors {errs[:2]}")
    b.close()
print("FAILURES:", failures) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
