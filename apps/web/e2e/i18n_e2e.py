"""E2E localisation test (Playwright). Run against a running stack:
  docker run --rm --add-host=host.docker.internal:host-gateway -v $PWD:/w -w /w \
    mcr.microsoft.com/playwright/python:v1.49.0-jammy sh -c "pip install -q playwright==1.49.0 && python apps/web/e2e/i18n_e2e.py"
Env: BASE (default http://host.docker.internal:8085), OUT (screenshot dir)."""
import json
import os
import re
import sys
import urllib.request

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://host.docker.internal:8085")
OUT = os.environ.get("OUT", "docs/screenshots")
# UI vocabulary that must not leak into hy/en (user content such as project/product names is excluded)
RU_UI = ["Проекты", "Каталог товаров", "Поставщики", "Утвердить", "Смета", "Загрузка", "Сохранить", "Изменить с ИИ", "Редактировать", "Главная", "Выйти", "В наличии", "Помещение", "Согласовать"]
failures: list[str] = []


def api(path, token=None, data=None, method=None):
    req = urllib.request.Request(BASE + "/api/v1" + path, data=json.dumps(data).encode() if data is not None else None, method=method,
                                 headers={"content-type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.load(urllib.request.urlopen(req))


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


token = api("/auth/login", data={"email": "designer@forma.local", "password": "demo1234"})["token"]
projects = api("/projects", token)
pid = next(p["id"] for p in projects if p["title"].startswith("Демо"))
variants = api(f"/projects/{pid}/variants", token)
vid = variants[0]["id"]
share = api(f"/projects/{pid}", token)["share_token"]
routes = {"dashboard": "/app", "project": f"/app/p/{pid}", "editor": f"/app/p/{pid}/editor/{vid}", "catalog": "/app/catalog", "client": f"/client/{share}"}

with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/login")
    pg.evaluate(f"localStorage.setItem('forma.token', '{token}')")
    for lang, label in (("hy", "Հայ"), ("ru", "Рус"), ("en", "Eng")):
        pg.goto(BASE + "/app")
        pg.get_by_role("button", name=label).first.click()
        pg.wait_for_timeout(600)
        check(pg.evaluate("document.documentElement.lang") == lang, f"[{lang}] switch without reload sets <html lang>")
        for name, path in routes.items():
            pg.goto(BASE + path)
            pg.wait_for_timeout(3500 if name != "client" else 5000)
            if name == "project":
                pg.get_by_role("button", name=re.compile({"hy": "Նախահաշիվ", "ru": "Смета", "en": "Estimate"}[lang])).first.click()
                pg.wait_for_timeout(800)
            text = pg.inner_text("body")
            if lang != "ru":
                leaked = [w for w in RU_UI if w in text]
                check(not leaked, f"[{lang}] {name}: no Russian UI words {leaked}")
            pg.screenshot(path=f"{OUT}/{name}_{lang}.png", timeout=120000)
        # persistence after reload
        pg.reload()
        pg.wait_for_timeout(1500)
        check(pg.evaluate("document.documentElement.lang") == lang, f"[{lang}] persists after reload")
        check(api("/auth/me", token)["locale"] == lang, f"[{lang}] saved in user profile")
    # new device (fresh storage): profile language wins at login
    ctx2 = b.new_context()
    pg2 = ctx2.new_page()
    pg2.goto(BASE + "/login")
    pg2.evaluate(f"localStorage.setItem('forma.token', '{token}')")
    pg2.goto(BASE + "/app")
    pg2.wait_for_timeout(2500)
    check(pg2.evaluate("document.documentElement.lang") == "en", "new session picks the profile language")
    # API error is shown translated (wrong password, Armenian UI)
    pg2.evaluate("localStorage.removeItem('forma.token'); localStorage.setItem('forma.lang','hy')")
    pg2.goto(BASE + "/login")
    pg2.fill("#pw", "wrong")
    pg2.click("button[type=submit], form button.primary")
    pg2.wait_for_timeout(1200)
    check("Սխալ էլ. փոստ կամ գաղտնաբառ" in pg2.inner_text("body"), "API error code translated to Armenian")
    check(not errors, f"no page errors {errors[:3]}")
    b.close()

print(f"\n{len(failures)} failures")
sys.exit(1 if failures else 0)
