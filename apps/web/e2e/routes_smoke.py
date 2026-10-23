"""Route smoke test: every UI route renders without JS errors or 5xx API calls, per role. Run against the compose stack."""
import json, urllib.request
from playwright.sync_api import sync_playwright
import os
B = os.environ.get("BASE", "http://localhost:8085")
def api(path, data=None, tok=None, method=None):
    r = urllib.request.Request(B + "/api/v1" + path, data=json.dumps(data).encode() if data is not None else None, method=method or ("POST" if data is not None else "GET"),
                               headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    return json.loads(urllib.request.urlopen(r).read())
res = []
def run(email, routes):
    tok = api("/auth/login", {"email": email, "password": "demo1234"})["token"]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1366, "height": 900})
        errs, bad = [], []
        pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
        pg.on("response", lambda r: bad.append(f"{r.status} {r.url.split('/api/v1')[-1][:60]}") if "/api/" in r.url and r.status >= 500 else None)
        pg.context.request.post(B + "/api/v1/auth/login", data={"email": email, "password": "demo1234"})
        for r in routes:
            errs.clear(); bad.clear()
            pg.goto(B + r); pg.wait_for_timeout(1800)
            body = pg.inner_text("body")[:2000]
            ok = not errs and not bad and len(body.strip()) > 40
            res.append((("PASS" if ok else "FAIL"), email.split("@")[0], r, errs[:2], bad[:2]))
        b.close()
    return tok
tok = api("/auth/login", {"email": "designer@forma.local", "password": "demo1234"})["token"]
projs = api("/projects", tok=tok)
demo = next(p for p in projs if p["title"].startswith("Демо")); pid = demo["id"]
vid = api(f"/projects/{pid}/variants", tok=tok)[0]["id"]
jid = api(f"/projects/{pid}/jobs?kind=pipeline", tok=tok) or api(f"/projects/{pid}/jobs", tok=tok)
jid = jid[0]["id"]
share = api(f"/projects/{pid}", tok=tok).get("share_token")
run("designer@forma.local", ["/", "/app", "/app/projects", "/app/new", f"/app/p/{pid}/upload", f"/app/p/{pid}/geometry", f"/app/p/{pid}/generate/{jid}", f"/app/p/{pid}",
    f"/app/p/{pid}/editor/{vid}", f"/app/p/{pid}/documents", f"/app/p/{pid}/procurement", f"/app/p/{pid}/versions/{vid}", "/app/catalog", "/app/suppliers"])
run("bureau@forma.local", ["/app/bureau"])
run("supplier@forma.local", ["/app/supplier", "/app/pim"])
run("admin@forma.local", ["/app/admin", "/app/admin?tab=orgs", "/app/admin?tab=suppliers", "/app/admin?tab=sources", "/app/bureau", "/app/supplier", "/app/catalog"])
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
    for r in ["/login", "/register", "/forgot-password", f"/client/{share}"]:
        errs.clear(); pg.goto(B + r); pg.wait_for_timeout(1800); res.append(("PASS" if not errs else "FAIL", "anon", r, errs[:2], []))
    b.close()
for r in res: print(*r[:3], *(r[3] + r[4]))
print("TOTAL", len(res), "FAIL", sum(r[0] == "FAIL" for r in res))
