"""Authentication: login/logout with server-side sessions (HttpOnly cookie for the
browser, bearer token for API clients), registration with e-mail verification,
password reset, session management and onboarding."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..mail import send_template
from ..ratelimit import check, client_ip, failures_exceeded, record_failure
from ..security import (
    Principal,
    clear_session_cookies,
    consume_one_time_token,
    current_principal,
    hash_password,
    new_one_time_token,
    revoke_sessions,
    set_session_cookies,
    start_session,
    verify_password,
)
from ..seed import DEMO_PASSWORD, DEMO_USERS

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DEMO_DOMAIN = "@forma.local"
ORG_KINDS = {"bureau": "bureau_admin", "supplier": "supplier_admin"}
# roles a user may pick for themselves during onboarding (never platform roles)
SELF_ROLES = {"bureau": {"bureau_admin", "designer"}, "supplier": {"supplier_admin", "supplier_catalog", "manufacturer"}}
COMMON_PASSWORDS = {"password", "password123", "qwerty123", "1234567890", "123456789", "qwertyuiop", "11111111", "iloveyou", "admin12345", "letmein123"}


def me_dict(p: Principal) -> dict:
    u = p.user
    return {"id": u.id, "email": u.email, "name": u.name, "locale": u.locale,
            "email_verified": u.email_verified_at is not None, "onboarded": u.onboarded_at is not None,
            "memberships": [{"org_id": ms.org_id, "org_name": ms.org.name, "org_kind": ms.org.kind, "role": ms.role} for ms in u.memberships],
            "roles": sorted(p.all_roles())}


def _audit(db: Session, user_id: str | None, action: str, request: Request | None = None, **data) -> None:
    db.add(m.AuditEvent(user_id=user_id, action=action, entity="user", entity_id=user_id, data={**data, "ip": client_ip(request) if request else ""}))


def _check_password(pw: str, email: str) -> None:
    s = get_settings()
    low = pw.lower()
    if len(pw) < s.password_min_len or low in COMMON_PASSWORDS or low == email.lower() or low == email.split("@")[0].lower() or len(set(pw)) < 4:
        raise ApiError(422, "auth.weak_password", min=s.password_min_len)


def _link(path: str, token: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}{path}?token={token}"


def _send_verification(db: Session, user: m.User) -> None:
    s = get_settings()
    raw = new_one_time_token(db, user, "verify_email", s.verify_token_ttl_h * 3600)
    db.commit()
    send_template(user.email, "verify_email", user.locale, name=user.name, link=_link("/verify-email", raw), hours=s.verify_token_ttl_h)


def _login_response(db: Session, user: m.User, request: Request, response: Response) -> dict:
    sess, token = start_session(db, user, request)
    _audit(db, user.id, "auth.login", request, session=sess.id)
    db.commit()
    csrf = set_session_cookies(response, token)
    # `token` is for API clients/scripts (Authorization: Bearer); the web app relies on the HttpOnly cookie only
    return {"token": token, "csrf": csrf, "session_id": sess.id}


# ------------------------------------------------------------------ login / logout
class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=200)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    ip = client_ip(request)
    check(f"login-ip:{ip}", 30, 300)
    failures_exceeded(f"login-fail:{email}", 10, 900)  # password guessing on one account, even from many IPs
    s = get_settings()
    if s.is_production and email.endswith(DEMO_DOMAIN):
        raise ApiError(403, "auth.demo_disabled")
    u = db.scalar(select(m.User).where(m.User.email == email))
    if not u or not verify_password(body.password, u.password_hash):
        _audit(db, u.id if u else None, "auth.login_failed", request, email=email if u else "")
        db.commit()
        record_failure(f"login-fail:{email}", 900)
        raise ApiError(401, "auth.bad_credentials")
    if u.status != "active":
        raise ApiError(403, "auth.account_disabled")
    return _login_response(db, u, request, response)


@router.post("/logout")
def logout(response: Response, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if p.session_id:
        sess = db.get(m.AuthSession, p.session_id)
        if sess:
            sess.revoked_at = datetime.now(timezone.utc)
    _audit(db, p.user.id, "auth.logout")
    db.commit()
    clear_session_cookies(response)
    return {"ok": True}


# ------------------------------------------------------------------ registration
class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(max_length=200)
    name: str = Field(min_length=1, max_length=200)
    org_name: str = Field(min_length=1, max_length=200)
    org_kind: str = Field(default="bureau", pattern="^(bureau|supplier)$")
    locale: str = Field(default="ru", pattern="^(hy|ru|en)$")
    accept_terms: bool = False


@router.post("/register")
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    check(f"register-ip:{client_ip(request)}", 10, 3600)  # offices share one NAT address
    if not body.accept_terms:
        raise ApiError(422, "auth.terms_required")
    email = body.email.lower().strip()
    if email.endswith(DEMO_DOMAIN):
        raise ApiError(422, "validation", fields=["email"])
    _check_password(body.password, email)
    if db.scalar(select(m.User).where(m.User.email == email)):
        raise ApiError(409, "auth.email_taken")
    now = datetime.now(timezone.utc)
    org = m.Organization(name=body.org_name.strip(), kind=body.org_kind, settings={})
    user = m.User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), locale=body.locale,
                  consents={"terms": {"version": get_settings().terms_version, "at": now.isoformat(), "ip": client_ip(request)}})
    db.add_all([org, user])
    db.flush()
    db.add(m.Membership(user_id=user.id, org_id=org.id, role=ORG_KINDS[body.org_kind]))
    _audit(db, user.id, "auth.register", request, org_kind=body.org_kind)
    db.commit()
    db.refresh(user)
    _send_verification(db, user)
    return _login_response(db, user, request, response)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


@router.post("/verify-email")
def verify_email(body: TokenIn, request: Request, db: Session = Depends(get_db)):
    check(f"verify-ip:{client_ip(request)}", 20, 3600)
    user = consume_one_time_token(db, body.token, "verify_email")
    user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)
    _audit(db, user.id, "auth.email_verified", request)
    db.commit()
    return {"ok": True, "email": user.email}


@router.post("/verify-email/resend")
def resend_verification(request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    check(f"resend:{p.user.id}", 3, 3600)
    if p.user.email_verified_at is None:
        _send_verification(db, p.user)
    return {"ok": True}


# ------------------------------------------------------------------ password reset
class ForgotIn(BaseModel):
    email: str = Field(max_length=320)


@router.post("/password/forgot")
def forgot_password(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Always 200 — the response never reveals whether the address is registered."""
    email = body.email.lower().strip()
    check(f"forgot-ip:{client_ip(request)}", 10, 3600)
    check(f"forgot-email:{email}", 3, 3600)
    u = db.scalar(select(m.User).where(m.User.email == email))
    if u and u.status == "active" and not (get_settings().is_production and email.endswith(DEMO_DOMAIN)):
        s = get_settings()
        raw = new_one_time_token(db, u, "password_reset", s.reset_token_ttl_min * 60)
        _audit(db, u.id, "auth.password_reset_requested", request)
        db.commit()
        send_template(u.email, "password_reset", u.locale, name=u.name, link=_link("/reset-password", raw), minutes=s.reset_token_ttl_min)
    return {"ok": True}


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    password: str = Field(max_length=200)


@router.post("/password/reset")
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    check(f"reset-ip:{client_ip(request)}", 10, 3600)
    user = consume_one_time_token(db, body.token, "password_reset")
    _check_password(body.password, user.email)
    user.password_hash = hash_password(body.password)
    user.email_verified_at = user.email_verified_at or datetime.now(timezone.utc)  # the link proves mailbox ownership
    n = revoke_sessions(db, user.id)
    _audit(db, user.id, "auth.password_reset", request, sessions_revoked=n)
    db.commit()
    send_template(user.email, "password_changed", user.locale, name=user.name)
    return {"ok": True}


# ------------------------------------------------------------------ profile, onboarding
@router.get("/me")
def me(p: Principal = Depends(current_principal)):
    return me_dict(p)


class MePatch(BaseModel):
    locale: str | None = None
    name: str | None = None


@router.patch("/me")
def patch_me(body: MePatch, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Persists the interface language (hy | ru | en) in the user profile."""
    if body.locale is not None:
        if body.locale not in ("hy", "ru", "en"):
            raise ApiError(422, "validation", fields=["locale"])
        p.user.locale = body.locale
    if body.name:
        p.user.name = body.name[:200]
    db.add(p.user)
    db.commit()
    return me_dict(p)


class OnboardingIn(BaseModel):
    org_name: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=50)
    contact_email: str | None = Field(default=None, max_length=320)
    role: str | None = Field(default=None, max_length=30)
    done: bool = False


@router.post("/onboarding")
def onboarding(body: OnboardingIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Three-step onboarding: organisation → own role → first project (the client navigates to /app/new)."""
    ms = next((x for x in p.user.memberships if x.org.kind in SELF_ROLES), None)
    if ms is None:
        raise ApiError(403, "auth.no_org")
    org = ms.org
    if body.org_name:
        org.name = body.org_name.strip()
    if any(v is not None for v in (body.city, body.phone, body.contact_email)):
        tb = dict((org.settings or {}).get("title_block", {}))
        tb.update({k: v for k, v in {"company": org.name, "address": body.city, "phone": body.phone, "email": body.contact_email}.items() if v is not None})
        org.settings = {**(org.settings or {}), "title_block": tb}
    if body.role:
        if body.role not in SELF_ROLES[org.kind]:
            raise ApiError(422, "validation", fields=["role"])
        # the founder keeps admin rights; the chosen role is added, not swapped
        if not any(x.org_id == org.id and x.role == body.role for x in p.user.memberships):
            db.add(m.Membership(user_id=p.user.id, org_id=org.id, role=body.role))
    if body.done:
        p.user.onboarded_at = p.user.onboarded_at or datetime.now(timezone.utc)
    _audit(db, p.user.id, "auth.onboarding", step="done" if body.done else "update")
    db.commit()
    db.refresh(p.user)
    roles: dict[str, set[str]] = {}
    for x in p.user.memberships:
        roles.setdefault(x.org_id, set()).add(x.role)
    return me_dict(Principal(user=p.user, roles=roles, session_id=p.session_id))


# ------------------------------------------------------------------ sessions & devices
@router.get("/sessions")
def list_sessions(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    rows = db.scalars(select(m.AuthSession).where(m.AuthSession.user_id == p.user.id, m.AuthSession.revoked_at.is_(None))
                      .order_by(m.AuthSession.last_seen_at.desc()).limit(50))
    now = datetime.now(timezone.utc)
    return [{"id": s.id, "user_agent": s.user_agent, "ip": s.ip, "created_at": s.created_at.isoformat(), "last_seen_at": s.last_seen_at.isoformat(),
             "current": s.id == p.session_id} for s in rows if (s.expires_at if s.expires_at.tzinfo else s.expires_at.replace(tzinfo=timezone.utc)) > now]


@router.delete("/sessions/{sid}")
def revoke_session(sid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    sess = db.get(m.AuthSession, sid)
    if not sess or sess.user_id != p.user.id:
        raise ApiError(404, "not_found")
    sess.revoked_at = datetime.now(timezone.utc)
    _audit(db, p.user.id, "auth.session_revoked", session=sid)
    db.commit()
    return {"ok": True}


@router.post("/sessions/revoke-others")
def revoke_other_sessions(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    n = revoke_sessions(db, p.user.id, except_sid=p.session_id)
    _audit(db, p.user.id, "auth.sessions_revoked", count=n)
    db.commit()
    return {"ok": True, "revoked": n}


@router.get("/demo-accounts")
def demo_accounts():
    if get_settings().is_production:
        raise ApiError(404, "not_found")
    return [{"email": e, "name": n, "role": r, "password": DEMO_PASSWORD} for e, n, _, r in DEMO_USERS]
