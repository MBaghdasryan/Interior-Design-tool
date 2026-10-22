"""P0-1 registration / e-mail verification / password reset and P0-2 sessions, cookies,
CSRF, rate limiting and the production guard."""
import re
import time
from datetime import datetime, timedelta, timezone
from email import message_from_bytes, policy

import pytest
from fastapi.testclient import TestClient

from app import models as m
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app, production_guard
from app.ratelimit import backend

STRONG = "Correct-Horse-42"
pytestmark = pytest.mark.usefixtures("client")  # app startup (tables, seed) runs in the session client


@pytest.fixture(autouse=True)
def _fresh_limits():
    backend().reset()
    yield
    backend().reset()


def browser() -> TestClient:
    return TestClient(app)  # startup already ran in the session client; this one keeps its own cookie jar


def mails_to(email: str) -> list[str]:
    d = get_settings().mail_dir
    safe = "".join(ch if ch.isalnum() else "_" for ch in email)[:60]
    out = []
    for p in sorted(d.glob(f"*_{safe}.eml")) if d.exists() else []:
        msg = message_from_bytes(p.read_bytes(), policy=policy.default)
        out.append(f"{msg['Subject']}\n{msg.get_content()}")
    return out


def link_token(mail: str, path: str) -> str:
    return re.search(rf"{path}\?token=([A-Za-z0-9_\-]+)", mail).group(1)


def register(c: TestClient, email: str, kind: str = "bureau", **extra):
    body = {"email": email, "password": STRONG, "name": "Test User", "org_name": "Test Studio", "org_kind": kind, "locale": "hy", "accept_terms": True, **extra}
    return c.post("/api/v1/auth/register", json=body)


def csrf(c: TestClient) -> dict:
    return {"X-CSRF-Token": c.cookies.get("forma_csrf")}


def test_register_sets_cookies_and_sends_localised_verification():
    c = browser()
    r = register(c, "new.bureau@example.com")
    assert r.status_code == 200, r.text
    assert c.cookies.get("forma_session") and c.cookies.get("forma_csrf")
    set_cookie = r.headers.get_list("set-cookie")
    assert any("forma_session=" in h and "HttpOnly" in h and "SameSite=lax" in h for h in set_cookie)
    assert not any("forma_csrf=" in h and "HttpOnly" in h for h in set_cookie)  # readable by JS for double-submit
    me = c.get("/api/v1/auth/me").json()  # cookie auth, safe method → no CSRF header needed
    assert me["email_verified"] is False and me["onboarded"] is False
    assert {"org_kind": "bureau", "role": "bureau_admin"}.items() <= me["memberships"][0].items()
    mail = mails_to("new.bureau@example.com")[-1]
    assert "Հաստատեք" in mail and "/verify-email?token=" in mail  # Armenian template (locale=hy)
    with SessionLocal() as db:
        u = db.query(m.User).filter_by(email="new.bureau@example.com").one()
        assert u.consents["terms"]["version"] == get_settings().terms_version
        assert all(t.token_hash != link_token(mail, "/verify-email") for t in db.query(m.AuthToken).all())  # only the hash is stored


def test_register_validation():
    c = browser()
    assert register(c, "dup@example.com").status_code == 200
    r = register(browser(), "dup@example.com")
    assert r.status_code == 409 and r.json()["code"] == "auth.email_taken"
    r = register(browser(), "weak@example.com", password="short")
    assert r.status_code == 422 and r.json()["code"] == "auth.weak_password"
    r = register(browser(), "weak2@example.com", password="weak2@example.com")
    assert r.json()["code"] == "auth.weak_password"
    r = register(browser(), "noterms@example.com", accept_terms=False)
    assert r.json()["code"] == "auth.terms_required"
    assert register(browser(), "x@forma.local").status_code == 422  # demo domain is reserved


def test_verify_email_once_and_expiry():
    c = browser()
    register(c, "verify.me@example.com")
    tok = link_token(mails_to("verify.me@example.com")[-1], "/verify-email")
    assert c.post("/api/v1/auth/verify-email", json={"token": tok}).json()["ok"]
    assert c.get("/api/v1/auth/me").json()["email_verified"] is True
    r = c.post("/api/v1/auth/verify-email", json={"token": tok})
    assert r.status_code == 400 and r.json()["code"] == "auth.token_invalid"
    # expired link
    c2 = browser()
    register(c2, "late@example.com")
    tok2 = link_token(mails_to("late@example.com")[-1], "/verify-email")
    with SessionLocal() as db:
        for t in db.query(m.AuthToken).filter_by(purpose="verify_email", used_at=None):
            t.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    r = c2.post("/api/v1/auth/verify-email", json={"token": tok2})
    assert r.status_code == 400 and r.json()["code"] == "auth.token_expired"


def test_csrf_required_for_cookie_auth_but_not_bearer():
    c = browser()
    r = register(c, "csrf@example.com")
    token = r.json()["token"]
    r = c.patch("/api/v1/auth/me", json={"name": "No CSRF"})
    assert r.status_code == 403 and r.json()["code"] == "auth.csrf"
    r = c.patch("/api/v1/auth/me", json={"name": "Wrong"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403
    assert c.patch("/api/v1/auth/me", json={"name": "With CSRF"}, headers=csrf(c)).json()["name"] == "With CSRF"
    plain = browser()  # API client: bearer header, no cookies → no CSRF needed
    assert plain.patch("/api/v1/auth/me", json={"name": "Bearer"}, headers={"Authorization": f"Bearer {token}"}).status_code == 200


def test_forgot_and_reset_password_revokes_sessions():
    c = browser()
    old_bearer = register(c, "reset.me@example.com").json()["token"]
    anon = browser()
    assert anon.post("/api/v1/auth/password/forgot", json={"email": "nobody@example.com"}).json() == {"ok": True}
    assert mails_to("nobody@example.com") == []  # no enumeration, nothing sent
    assert anon.post("/api/v1/auth/password/forgot", json={"email": "reset.me@example.com"}).json() == {"ok": True}
    tok = link_token(mails_to("reset.me@example.com")[-1], "/reset-password")
    r = anon.post("/api/v1/auth/password/reset", json={"token": tok, "password": "short"})
    assert r.status_code == 422 and r.json()["code"] == "auth.weak_password"  # rejected attempt does not burn the link
    assert anon.post("/api/v1/auth/password/reset", json={"token": tok, "password": "Brand-New-Pass-7"}).json()["ok"]
    assert browser().get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_bearer}"}).status_code == 401  # all sessions revoked
    assert c.get("/api/v1/auth/me").status_code == 401  # the cookie session too
    assert browser().post("/api/v1/auth/login", json={"email": "reset.me@example.com", "password": "Brand-New-Pass-7"}).status_code == 200
    assert "Գաղտնաբառը փոխվել" in mails_to("reset.me@example.com")[-1]  # notification in the user's language
    assert anon.post("/api/v1/auth/password/reset", json={"token": tok, "password": "Another-Pass-88"}).json()["code"] == "auth.token_invalid"


def test_sessions_list_and_revoke():
    a, b = browser(), browser()
    register(a, "two.devices@example.com")
    assert b.post("/api/v1/auth/login", json={"email": "two.devices@example.com", "password": STRONG}).status_code == 200
    sessions = a.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2 and sum(s["current"] for s in sessions) == 1
    other = next(s for s in sessions if not s["current"])
    assert a.delete(f"/api/v1/auth/sessions/{other['id']}", headers=csrf(a)).json()["ok"]
    r = b.get("/api/v1/auth/me")
    assert r.status_code == 401 and r.json()["code"] == "auth.invalid_session"
    assert a.post("/api/v1/auth/logout", headers=csrf(a)).json()["ok"]
    assert a.get("/api/v1/auth/me").status_code == 401


def test_login_rate_limit_returns_429_with_retry_after():
    c = browser()
    codes = [c.post("/api/v1/auth/login", json={"email": "designer@forma.local", "password": "wrong"}).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429
    r = c.post("/api/v1/auth/login", json={"email": "designer@forma.local", "password": "demo1234"})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and int(r.headers["Retry-After"]) > 0


def test_onboarding_steps():
    c = browser()
    register(c, "onboard@example.com", kind="supplier")
    h = csrf(c)
    me = c.post("/api/v1/auth/onboarding", json={"org_name": "Tile House", "city": "Yerevan", "phone": "+374 10 000000"}, headers=h).json()
    assert me["memberships"][0]["org_name"] == "Tile House"
    assert c.post("/api/v1/auth/onboarding", json={"role": "platform_admin"}, headers=h).status_code == 422  # never self-grant platform roles
    me = c.post("/api/v1/auth/onboarding", json={"role": "supplier_catalog", "done": True}, headers=h).json()
    assert me["onboarded"] is True and "supplier_catalog" in me["roles"] and "supplier_admin" in me["roles"]
    with SessionLocal() as db:
        org = db.query(m.Organization).filter_by(name="Tile House").one()
        assert org.settings["title_block"]["address"] == "Yerevan"


def test_sse_uses_cookie_not_query_token(designer, client):
    pid = next(p for p in client.get("/api/v1/projects", headers=designer).json() if p["title"].startswith("Демо"))["id"]
    jobs = client.get(f"/api/v1/projects/{pid}/jobs", headers=designer).json()
    if not jobs:
        pytest.skip("no job yet in isolated run")
    url = f"/api/v1/projects/{pid}/jobs/{jobs[0]['id']}/events"
    assert browser().get(url).status_code == 401  # no cookie, no bearer
    c = browser()
    c.post("/api/v1/auth/login", json={"email": "designer@forma.local", "password": "demo1234"})
    with c.stream("GET", url) as r:
        assert r.status_code == 200
        body = ""
        t0 = time.time()
        for chunk in r.iter_text():
            body += chunk
            if "event: end" in body or time.time() - t0 > 10:
                break
    assert "event: progress" in body


def test_production_guard_and_demo_lockout(monkeypatch):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        production_guard(Settings(env="production", secret_key="dev-only-change-me", seed_demo=False))
    with pytest.raises(RuntimeError, match="SEED_DEMO"):
        production_guard(Settings(env="production", secret_key="x" * 40, seed_demo=True))
    production_guard(Settings(env="production", secret_key="x" * 40, seed_demo=False, cookie_secure=True))  # ok
    s = get_settings()
    monkeypatch.setattr(s, "env", "production")
    c = browser()
    assert c.get("/api/v1/auth/demo-accounts").status_code == 404
    r = c.post("/api/v1/auth/login", json={"email": "designer@forma.local", "password": "demo1234"})
    assert r.status_code == 403 and r.json()["code"] == "auth.demo_disabled"


def test_seeded_demo_accounts_skip_onboarding(client):
    """Fresh databases (seed after migrations) must not send demo users into the sign-up wizard."""
    c = browser()
    c.post("/api/v1/auth/login", json={"email": "designer@forma.local", "password": "demo1234"})
    me = c.get("/api/v1/auth/me").json()
    assert me["onboarded"] is True and me["email_verified"] is True
