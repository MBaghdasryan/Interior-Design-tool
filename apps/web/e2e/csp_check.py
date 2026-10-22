"""CSP enforcement check: every page (incl. the Autodesk APS Viewer on the documents page and the
WebGL landing) must load without Content-Security-Policy violations. Env: BASE."""
import json
import os
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:8085")


def api(path, data=None, tok=None):
    r = urllib.request.Request(BASE + "/api/v1" + path, data=json.dumps(data).encode() if data is not None else None, method="POST" if data is not None else "GET",
                               headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    return json.loads(urllib.request.urlopen(r).read())


tok = api("/auth/login", {"email": "designer@forma.local", "password": "demo1234"})["token"]
demo = next(p for p in api("/projects", tok=tok) if p["title"].startswith("Демо"))
vid = api(f"/projects/{demo['id']}/variants", tok=tok)[0]["id"]
docs = api(f"/projects/{demo['id']}/documents", tok=tok)
has_dwg = any(d["kind"] == "dwg" for d in docs)
routes = ["/", "/login", "/register", "/app", f"/app/p/{demo['id']}", f"/app/p/{demo['id']}/editor/{vid}", f"/app/p/{demo['id']}/documents",
          "/app/catalog", "/app/account", f"/client/{demo['share_token']}"]
violations: list[str] = []
viewer_ok = None
# third-party telemetry stays blocked on purpose (privacy): reported separately, not a failure
BLOCKED_ON_PURPOSE = ("mixpanel.com",)
blocked: list[str] = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
    ctx = b.new_context(viewport={"width": 1366, "height": 900})
    ctx.request.post(BASE + "/api/v1/auth/login", data={"email": "designer@forma.local", "password": "demo1234"})
    pg = ctx.new_page()
    def on_console(msg):
        if "Content Security Policy" in msg.text or "Refused to" in msg.text:
            (blocked if any(d in msg.text for d in BLOCKED_ON_PURPOSE) else violations).append(f"{pg.url}: {msg.text[:200]}")

    pg.on("console", on_console)
    for r in routes:
        pg.goto(BASE + r)
        pg.wait_for_timeout(4000)
        if r.endswith("/documents") and has_dwg:
            pg.evaluate("localStorage.setItem('forma.lang','en')")
            pg.reload()
            pg.wait_for_timeout(3000)
            btn = pg.get_by_role("button", name="View", exact=True)
            print("  viewer buttons:", btn.count())
            if btn.count():
                btn.first.click()
                for _ in range(60):  # polled from Python: page-side eval would itself be blocked by the CSP
                    if pg.evaluate("typeof window.Autodesk !== 'undefined' && !!document.querySelector('.adsk-viewing-viewer canvas')"):
                        break
                    pg.wait_for_timeout(1000)
                pg.wait_for_timeout(8000)  # model/derivative loading (workers, wss)
                viewer_ok = pg.evaluate("!!document.querySelector('.adsk-viewing-viewer canvas')")
        print("visited", r)
    b.close()
print("APS viewer rendered under the enforced CSP:", viewer_ok, "" if has_dwg else "(no DWG document in this database)")
print("third-party telemetry blocked by CSP (intended):", len(blocked))
print("CSP violations:", len(violations))
for v in sorted({v.split("Refused to ")[-1][:110] for v in violations}):
    print("  ", v)
sys.exit(1 if violations else 0)
