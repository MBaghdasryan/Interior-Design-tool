"""E2E: sign-up → confirm e-mail (link from the outgoing mail) → onboarding → first project,
then log out, forgot password → reset → sign in with the new password.

Needs the API mail directory (console mail backend) mounted read-only, e.g.:
  docker run --rm --network host -v interier-design-tool_storage:/apidata:ro -v $PWD/apps/web/e2e:/e2e \
    mcr.microsoft.com/playwright/python:v1.49.0-jammy sh -c "pip install -q playwright==1.49.0 && python /e2e/auth_e2e.py"
Env: BASE (default http://localhost:8085), MAIL_DIR (default /apidata/mail)."""
import os
import re
import sys
import time
from email import message_from_bytes, policy
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("BASE", "http://localhost:8085")
MAIL_DIR = Path(os.environ.get("MAIL_DIR", "/apidata/mail"))
EMAIL = f"e2e.{int(time.time())}@example.com"
PASSWORD, NEW_PASSWORD = "E2e-Strong-Pass-1", "E2e-Strong-Pass-2"
failures: list[str] = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def last_link(path: str, timeout: float = 10) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in EMAIL)[:60]
    t0 = time.time()
    while time.time() - t0 < timeout:
        for f in sorted(MAIL_DIR.glob(f"*_{safe}.eml"), reverse=True):
            body = message_from_bytes(f.read_bytes(), policy=policy.default).get_content()
            m = re.search(rf"https?://\S+{path}\?token=[A-Za-z0-9_\-]+", body)
            if m:
                return m.group(0)
        time.sleep(0.5)
    raise RuntimeError(f"no mail with {path} for {EMAIL}")


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(BASE + "/login")
    pg.evaluate("localStorage.setItem('forma.lang','en')")
    pg.goto(BASE + "/register")
    pg.fill("#r-org", "E2E Studio")
    pg.fill("#r-name", "E2E Designer")
    pg.fill("#r-email", EMAIL)
    pg.fill("#r-pw", PASSWORD)
    pg.check("input[type=checkbox]")
    pg.click("button.primary")
    pg.wait_for_url("**/app/onboarding", timeout=15000)
    check(True, "sign-up opens onboarding")
    check("forma_session" in {c["name"] for c in ctx.cookies()}, "session cookie set (HttpOnly, not in localStorage)")
    check(pg.evaluate("Object.keys(localStorage).some(k => k.includes('token'))") is False, "no auth token in localStorage")
    try:
        pg.wait_for_selector("text=Please confirm your e-mail", timeout=8000)
        check(True, "unverified banner shown")
    except Exception:
        check(False, "unverified banner shown")

    # confirm e-mail from the real outgoing message
    pg.goto(last_link("/verify-email"))
    pg.wait_for_selector("text=Your e-mail is confirmed", timeout=10000)
    check(True, "e-mail confirmed via link")

    # onboarding: organisation → role → first project
    pg.goto(BASE + "/app/onboarding")
    pg.fill("#o-city", "Yerevan")
    pg.fill("#o-phone", "+374 10 000000")
    pg.get_by_role("button", name="Next").click()
    pg.get_by_role("button", name="Next").click()
    pg.get_by_role("button", name="Create a project").click()
    pg.wait_for_url("**/app/new", timeout=10000)
    pg.locator("form input").first.fill("E2E apartment")
    pg.locator("form button.primary").click()
    pg.wait_for_url(re.compile(r".*/app/p/[0-9a-f]+/upload"), timeout=10000)
    check(True, "first project created after onboarding")
    check("confirm your e-mail" not in pg.inner_text("body").lower(), "banner gone after confirmation")

    # sign out → forgot password → reset → sign in with the new password
    pg.get_by_role("button", name="Sign out").click()
    pg.wait_for_url("**/login*", timeout=10000)
    check(ctx.request.get(BASE + "/api/v1/auth/me").status == 401, "logout revokes the session")
    pg.goto(BASE + "/forgot-password")
    pg.fill("#f-email", EMAIL)
    pg.click("button.primary")
    pg.wait_for_selector("text=If an account with this address exists", timeout=10000)
    pg.goto(last_link("/reset-password"))
    pg.fill("#n-pw", NEW_PASSWORD)
    pg.fill("#n-pw2", NEW_PASSWORD)
    pg.click("button.primary")
    pg.wait_for_selector("text=Password changed", timeout=10000)
    pg.goto(BASE + "/login")
    pg.fill("#em", EMAIL)
    pg.fill("#pw", NEW_PASSWORD)
    pg.click("form button.primary")
    pg.wait_for_url("**/app", timeout=10000)
    check(True, "sign-in with the new password")
    check(not errors, f"no page errors {errors[:3]}")
    b.close()

print(f"\n{len(failures)} failures")
sys.exit(1 if failures else 0)
