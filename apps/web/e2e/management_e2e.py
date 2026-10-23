"""Management E2E against the compose stack: platform users / organisations / suppliers, admin inside bureau and
supplier cabinets, bureau head inviting staff, supplier adding a product by hand, catalogue edit. RU + HY screenshots."""
import json, os, time, urllib.request
from playwright.sync_api import sync_playwright

B = os.environ.get("BASE", "http://localhost:8085")
SHOTS = os.environ.get("SHOTS", "/tmp/shots")
os.makedirs(SHOTS, exist_ok=True)
STAMP = str(int(time.time()))[-6:]
fails = []


def api(path, data=None, tok=None, method=None):
    r = urllib.request.Request(B + "/api/v1" + path, data=json.dumps(data).encode() if data is not None else None, method=method or ("POST" if data is not None else "GET"),
                               headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {tok}"} if tok else {})})
    return json.loads(urllib.request.urlopen(r).read())


def token(email):
    return api("/auth/login", {"email": email, "password": "demo1234"})["token"]


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def session(p, email, lang):
    api("/auth/me", {"locale": lang}, tok=token(email), method="PATCH")  # the profile language wins on sign-in
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 960})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    pg.on("response", lambda r: errs.append(f"{r.status} {r.url.split('/api/v1')[-1][:70]}") if "/api/" in r.url and r.status >= 500 else None)
    pg.on("dialog", lambda d: d.accept())
    pg.context.request.post(B + "/api/v1/auth/login", data={"email": email, "password": "demo1234"})
    return b, pg, errs


def go(pg, path, wait=1500):
    pg.goto(B + path)
    pg.wait_for_timeout(wait)


def shot(pg, name, lang):
    pg.screenshot(path=f"{SHOTS}/{name}_{lang}.png", full_page=False)


with sync_playwright() as p:
    for lang in ("ru", "hy"):
        # ---------------------------------------------------------------- platform admin
        b, pg, errs = session(p, "admin@forma.local", lang)
        go(pg, "/app/admin?tab=users")
        check(pg.locator("table").first.is_visible(), f"[{lang}] admin users table")
        shot(pg, "admin_users", lang)
        if lang == "ru":
            pg.get_by_role("button", name="Добавить пользователя").click()
            dlg = pg.get_by_role("dialog")
            dlg.locator("input[type=email]").fill(f"e2e.{STAMP}@example.am")
            dlg.locator("input").nth(1).fill("E2E Сотрудник")
            dlg.get_by_role("button", name="Отправить приглашение").click()
            pg.wait_for_timeout(1200)
            check(pg.get_by_text(f"e2e.{STAMP}@example.am").first.is_visible(), "admin adds a user through the UI")
            pg.get_by_text(f"e2e.{STAMP}@example.am").first.click()
            pg.wait_for_timeout(500)
            check(pg.locator(".drawer").is_visible(), "user drawer opens")
            shot(pg, "admin_user_drawer", lang)
            pg.get_by_role("button", name="Приостановить").click()
            pg.wait_for_timeout(800)
            check(pg.locator(".drawer").get_by_text("Приостановлен").first.is_visible(), "admin suspends the user")
            pg.locator(".drawer").get_by_role("button", name="Закрыть").click()
        go(pg, "/app/admin?tab=orgs")
        check(pg.locator("table tbody tr").count() >= 3, f"[{lang}] organisations listed")
        shot(pg, "admin_orgs", lang)
        go(pg, "/app/admin?tab=suppliers")
        check(pg.locator("table tbody tr").count() >= 1, f"[{lang}] suppliers listed")
        shot(pg, "admin_suppliers", lang)
        # bureau cabinet through the picker
        tok = token("admin@forma.local")
        bureau = next(o for o in api("/admin/organizations?kind=bureau", tok=tok) if o["projects"])
        go(pg, f"/app/bureau?org={bureau['id']}", 2200)
        check(pg.locator(".kpi").count() >= 4 and pg.locator("#team-h").is_visible(), f"[{lang}] admin sees a bureau cabinet with KPIs and team")
        shot(pg, "bureau_cabinet_admin", lang)
        sup = next(s for s in api("/admin/suppliers/all", tok=tok) if s["products"])
        go(pg, f"/app/supplier?supplier={sup['id']}", 2500)
        check(pg.locator("#sprod-h").is_visible() and pg.locator("table tbody tr").count() > 0, f"[{lang}] admin sees a supplier cabinet with products")
        shot(pg, "supplier_cabinet_admin", lang)
        go(pg, "/app/catalog", 2500)
        check(pg.locator("button:has(svg.lucide-pencil)").count() > 0, f"[{lang}] catalogue shows edit buttons to the admin")
        pg.locator("button:has(svg.lucide-pencil)").first.click()
        pg.wait_for_timeout(1200)
        check(pg.locator(".drawer").is_visible(), f"[{lang}] product editor opens from the catalogue")
        shot(pg, "catalog_product_editor", lang)
        check(not errs, f"[{lang}] admin: no JS errors / 5xx {errs[:3]}")
        b.close()

        # ---------------------------------------------------------------- bureau head
        b, pg, errs = session(p, "bureau@forma.local", lang)
        go(pg, "/app/bureau", 2000)
        check(pg.locator("#team-h").is_visible(), f"[{lang}] bureau head sees the team card")
        if lang == "ru":
            pg.get_by_role("button", name="Пригласить сотрудника").click()
            dlg = pg.get_by_role("dialog")
            dlg.locator("input[type=email]").fill(f"designer.{STAMP}@example.am")
            dlg.locator("input").nth(1).fill("Новый Дизайнер")
            dlg.get_by_role("button", name="Отправить приглашение").click()
            pg.wait_for_timeout(1200)
            check(pg.get_by_text(f"designer.{STAMP}@example.am", exact=True).is_visible(), "bureau head invites an employee")
        shot(pg, "bureau_team", lang)
        check(not errs, f"[{lang}] bureau: no JS errors / 5xx {errs[:3]}")
        b.close()

        # ---------------------------------------------------------------- supplier
        b, pg, errs = session(p, "supplier@forma.local", lang)
        go(pg, "/app/supplier", 2500)
        if lang == "ru":
            pg.get_by_role("button", name="Добавить товар").click()
            pg.wait_for_timeout(800)
            d = pg.locator(".drawer")
            d.locator("label:has-text('Название (рус.)') input").fill(f"Кресло E2E {STAMP}")
            d.locator(".card.flat input.mono").fill(f"E2E-{STAMP}")
            d.locator(".card.flat input[inputmode=numeric]").first.fill("185000")
            d.get_by_role("button", name="Сохранить").click()
            pg.wait_for_timeout(1500)
            check(pg.get_by_text(f"E2E-{STAMP}", exact=True).is_visible(), "supplier adds a product by hand")
            pg.locator(f"tr:has-text('E2E-{STAMP}') button:has(svg.lucide-archive)").click()
            pg.wait_for_timeout(1500)
            check(pg.get_by_text(f"E2E-{STAMP}", exact=True).count() == 0, "supplier archives the product")
        shot(pg, "supplier_cabinet", lang)
        check(not errs, f"[{lang}] supplier: no JS errors / 5xx {errs[:3]}")
        b.close()

    for email in ("admin@forma.local", "bureau@forma.local", "supplier@forma.local"):
        api("/auth/me", {"locale": "ru"}, tok=token(email), method="PATCH")

print("FAILURES", len(fails))
