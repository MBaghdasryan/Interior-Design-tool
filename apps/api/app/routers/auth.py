"""Authentication: login/logout with server-side sessions (HttpOnly cookie for the
browser, bearer token for API clients), registration with e-mail verification,
password reset, session management and onboarding."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import mfa
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
    mfa_required = mfa.required_for(p.all_roles())
    return {"id": u.id, "email": u.email, "name": u.name, "locale": u.locale,
            "email_verified": u.email_verified_at is not None, "onboarded": u.onboarded_at is not None,
            "mfa_enabled": u.mfa_enabled_at is not None, "mfa_required": mfa_required,
            "mfa_enrollment_required": mfa_required and u.mfa_enabled_at is None,
            "deletion_due_at": u.deletion_due_at.isoformat() if u.deletion_due_at else None,
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
    if u.status not in ("active", "deletion_pending"):
        raise ApiError(403, "auth.account_disabled")
    if u.mfa_enabled_at:
        # second step: no session yet — the client posts the TOTP / backup code with this short-lived token
        return {"mfa_required": True, "mfa_token": mfa.issue_mfa_token(u.id)}
    return _login_response(db, u, request, response)


class MfaVerifyIn(BaseModel):
    mfa_token: str = Field(max_length=400)
    code: str | None = Field(default=None, max_length=12)
    backup_code: str | None = Field(default=None, max_length=20)


@router.post("/mfa/verify")
def mfa_verify(body: MfaVerifyIn, request: Request, response: Response, db: Session = Depends(get_db)):
    uid = mfa.read_mfa_token(body.mfa_token)
    if not uid:
        raise ApiError(401, "auth.invalid_session")
    failures_exceeded(f"mfa-fail:{uid}", 5, 900)
    u = db.get(m.User, uid)
    if not u or not u.mfa_enabled_at or not mfa.check_second_factor(u, body.code, body.backup_code):
        record_failure(f"mfa-fail:{uid}", 900)
        _audit(db, uid, "auth.mfa_failed", request)
        db.commit()
        raise ApiError(401, "auth.mfa_invalid")
    _audit(db, u.id, "auth.mfa_passed", request, method="backup_code" if body.backup_code and not body.code else "totp")
    return _login_response(db, u, request, response)


# ------------------------------------------------------------------ MFA management
class CodeIn(BaseModel):
    code: str | None = Field(default=None, max_length=12)
    backup_code: str | None = Field(default=None, max_length=20)


@router.post("/mfa/setup")
def mfa_setup(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Starts enrolment: a new secret (pending until confirmed), otpauth URI and QR code."""
    out = mfa.start_setup(p.user)
    db.commit()
    return out


@router.post("/mfa/enable")
def mfa_enable(body: CodeIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    secret = mfa.decrypt(p.user.mfa_pending_enc)
    if not secret:
        raise ApiError(409, "auth.mfa_not_started")
    if not mfa.verify_totp(secret, body.code or ""):
        raise ApiError(422, "auth.mfa_invalid")
    plain, hashed = mfa.new_backup_codes()
    p.user.mfa_secret_enc, p.user.mfa_pending_enc = mfa.encrypt(secret), None
    p.user.mfa_enabled_at, p.user.mfa_backup_codes = datetime.now(timezone.utc), hashed
    _audit(db, p.user.id, "auth.mfa_enabled", request)
    db.commit()
    return {"ok": True, "backup_codes": plain}  # shown once


@router.post("/mfa/backup-codes")
def mfa_regenerate_codes(body: CodeIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if not p.user.mfa_enabled_at or not mfa.check_second_factor(p.user, body.code, body.backup_code):
        raise ApiError(422, "auth.mfa_invalid")
    plain, hashed = mfa.new_backup_codes()
    p.user.mfa_backup_codes = hashed
    _audit(db, p.user.id, "auth.mfa_codes_regenerated", request)
    db.commit()
    return {"ok": True, "backup_codes": plain}


@router.post("/mfa/disable")
def mfa_disable(body: CodeIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    if not p.user.mfa_enabled_at or not mfa.check_second_factor(p.user, body.code, body.backup_code):
        raise ApiError(422, "auth.mfa_invalid")
    p.user.mfa_secret_enc = p.user.mfa_pending_enc = None
    p.user.mfa_enabled_at, p.user.mfa_backup_codes = None, []
    _audit(db, p.user.id, "auth.mfa_disabled", request)
    db.commit()
    return me_dict(p)


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
    ref: str = Field(default="", max_length=24, pattern=r"^[a-z0-9-]*$")  # partner code from the landing link


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
    referrer = db.scalar(select(m.PartnerCode).where(m.PartnerCode.code == body.ref)) if body.ref else None
    org = m.Organization(name=body.org_name.strip(), kind=body.org_kind, settings={"referred_by": referrer.code} if referrer else {})
    user = m.User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), locale=body.locale,
                  consents={"terms": {"version": get_settings().terms_version, "at": now.isoformat(), "ip": client_ip(request)}})
    db.add_all([org, user])
    db.flush()
    db.add(m.Membership(user_id=user.id, org_id=org.id, role=ORG_KINDS[body.org_kind]))
    from ..commerce import billing, tariffs

    default_plan = tariffs.get_tariffs(db).default_plan  # None = pilot without limits
    if default_plan and any(x.key == default_plan for x in tariffs.plans_for(tariffs.get_tariffs(db), org.kind)):
        billing.assign_plan(db, org, default_plan)
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


# ------------------------------------------------------------------ personal data (privacy)
@router.get("/me/export")
def export_my_data(request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """All personal data of the signed-in user (profile, consents, sessions, activity, own projects with files) as ZIP."""
    from fastapi.responses import Response as RawResponse

    from ..privacy import export_zip

    check(f"export:{p.user.id}", 5, 3600)
    data = export_zip(db, p.user)
    _audit(db, p.user.id, "privacy.export", request, size=len(data))
    db.commit()
    return RawResponse(data, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="renovara-my-data.zip"'})


class DeleteIn(BaseModel):
    password: str = Field(max_length=200)
    code: str | None = Field(default=None, max_length=12)


@router.post("/me/delete")
def delete_my_account(body: DeleteIn, request: Request, response: Response, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Schedules deletion after a grace period (PRIVACY_DELETION_GRACE_DAYS); signing in and cancelling stops it."""
    from ..privacy import request_deletion

    if not verify_password(body.password, p.user.password_hash):
        raise ApiError(401, "auth.bad_credentials")
    if p.user.mfa_enabled_at and not mfa.check_second_factor(p.user, body.code, None):
        raise ApiError(401, "auth.mfa_required")
    due = request_deletion(p.user)
    n = revoke_sessions(db, p.user.id, except_sid=p.session_id)
    _audit(db, p.user.id, "privacy.deletion_requested", request, due=due.isoformat(), sessions_revoked=n)
    db.commit()
    return me_dict(p)


@router.post("/me/delete/cancel")
def cancel_my_deletion(request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..privacy import cancel_deletion

    cancel_deletion(p.user)
    _audit(db, p.user.id, "privacy.deletion_cancelled", request)
    db.commit()
    return me_dict(p)


@router.get("/me/consents")
def my_consents(p: Principal = Depends(current_principal)):
    return p.user.consents or {}


class ConsentsIn(BaseModel):
    marketing_emails: bool | None = None
    product_analytics: bool | None = None


@router.put("/me/consents")
def update_consents(body: ConsentsIn, request: Request, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    from ..privacy import set_consents

    c = set_consents(p.user, body.model_dump(exclude_none=True), client_ip(request))
    _audit(db, p.user.id, "privacy.consents", request, **body.model_dump(exclude_none=True))
    db.commit()
    return c


@router.get("/demo-accounts")
def demo_accounts():
    if get_settings().is_production:
        raise ApiError(404, "not_found")
    return [{"email": e, "name": n, "role": r, "password": DEMO_PASSWORD} for e, n, _, r in DEMO_USERS]
