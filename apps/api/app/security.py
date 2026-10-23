"""Authentication (signed bearer tokens), password hashing, RBAC and tenant
isolation. Every project resource goes through `project_access`."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .config import get_settings
from .db import get_db
from .errors import ApiError

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {"*"},
    "platform_ops": {"project:read", "catalog:read", "catalog:write", "sources:manage", "jobs:read", "audit:read"},
    "bureau_admin": {"project:read", "project:write", "project:approve", "catalog:read", "team:manage", "rfq:send", "documents:write"},
    "designer": {"project:read", "project:write", "project:approve", "catalog:read", "rfq:send", "documents:write"},
    "client": {"project:read", "project:write", "project:approve", "comment:write"},
    "collaborator": {"project:read", "comment:write"},
    "supplier_admin": {"catalog:read", "catalog:write", "supplier:manage", "rfq:respond"},
    "supplier_catalog": {"catalog:read", "catalog:write"},
    "manufacturer": {"catalog:read", "catalog:write", "rfq:respond"},
    "installer": {"project:read"},
    "verifier": {"project:read", "project:verify"},
    # Armenian terminology reviewer (native-speaking architect): proposes and approves album terms
    "linguist": {"glossary:review"},
}


def hash_password(pw: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 240_000)
    return f"pbkdf2${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt_b64, dk_b64 = stored.split("$")
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt_b64), 240_000)
    return hmac.compare_digest(dk, base64.b64decode(dk_b64))


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


SESSION_COOKIE = "forma_session"
CSRF_COOKIE = "forma_csrf"
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _sign(payload: str) -> str:
    return _b64(hmac.new(get_settings().secret_key.encode(), payload.encode(), hashlib.sha256).digest())


def issue_token(user_id: str, sid: str, ttl_s: int | None = None) -> str:
    """Signed token `{sub, sid, exp}`; valid only while the AuthSession `sid` is not revoked."""
    ttl = ttl_s or get_settings().session_ttl_h * 3600
    payload = _b64(json.dumps({"sub": user_id, "sid": sid, "exp": int(time.time()) + ttl}).encode())
    return f"{payload}.{_sign(payload)}"


def read_token(token: str) -> tuple[str, str] | None:
    try:
        payload, sig = token.split(".")
        if not hmac.compare_digest(_sign(payload), sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    if data.get("exp", 0) < time.time() or not data.get("sid"):
        return None
    return data.get("sub"), data.get("sid")


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def new_one_time_token(db: Session, user: m.User, purpose: str, ttl_s: int) -> str:
    """Creates a single-use token; previous unused tokens of the same purpose are invalidated."""
    now = datetime.now(timezone.utc)
    for old in db.scalars(select(m.AuthToken).where(m.AuthToken.user_id == user.id, m.AuthToken.purpose == purpose, m.AuthToken.used_at.is_(None))):
        old.used_at = now
    raw = secrets.token_urlsafe(32)
    db.add(m.AuthToken(user_id=user.id, purpose=purpose, token_hash=hash_token(raw), expires_at=now + timedelta(seconds=ttl_s)))
    return raw


def consume_one_time_token(db: Session, raw: str, purpose: str) -> m.User:
    tok = db.scalar(select(m.AuthToken).where(m.AuthToken.token_hash == hash_token(raw or ""), m.AuthToken.purpose == purpose))
    if not tok or tok.used_at is not None:
        raise ApiError(400, "auth.token_invalid")
    if _aware(tok.expires_at) < datetime.now(timezone.utc):
        raise ApiError(400, "auth.token_expired")
    tok.used_at = datetime.now(timezone.utc)
    user = db.get(m.User, tok.user_id)
    if not user:
        raise ApiError(400, "auth.token_invalid")
    return user


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def start_session(db: Session, user: m.User, request: Request | None) -> tuple[m.AuthSession, str]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    sess = m.AuthSession(user_id=user.id, user_agent=(request.headers.get("user-agent", "") if request else "")[:300],
                         ip=_ip(request), last_seen_at=now, expires_at=now + timedelta(hours=s.session_ttl_h))
    db.add(sess)
    db.flush()
    return sess, issue_token(user.id, sess.id)


def set_session_cookies(response: Response, token: str) -> str:
    """HttpOnly session cookie + readable CSRF cookie (double-submit). Returns the CSRF value."""
    s = get_settings()
    csrf = secrets.token_urlsafe(24)
    common = {"secure": s.cookie_secure, "samesite": "lax", "domain": s.cookie_domain, "path": "/"}
    response.set_cookie(SESSION_COOKIE, token, httponly=True, max_age=s.session_ttl_h * 3600, **common)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, max_age=s.session_ttl_h * 3600, **common)
    return csrf


def clear_session_cookies(response: Response) -> None:
    s = get_settings()
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", domain=s.cookie_domain, secure=s.cookie_secure, samesite="lax")


def revoke_sessions(db: Session, user_id: str, except_sid: str | None = None) -> int:
    now = datetime.now(timezone.utc)
    n = 0
    for sess in db.scalars(select(m.AuthSession).where(m.AuthSession.user_id == user_id, m.AuthSession.revoked_at.is_(None))):
        if sess.id != except_sid:
            sess.revoked_at = now
            n += 1
    return n


def _ip(request: Request | None) -> str:
    if request is None:
        return ""
    fwd = request.headers.get("x-forwarded-for", "")
    return ((fwd.split(",")[0].strip() if fwd else "") or (request.client.host if request.client else ""))[:64]


@dataclass
class Principal:
    user: m.User
    roles: dict[str, set[str]]  # org_id -> roles
    session_id: str | None = None

    @property
    def org_ids(self) -> set[str]:
        return set(self.roles)

    def all_roles(self) -> set[str]:
        return {r for rs in self.roles.values() for r in rs}

    def can(self, perm: str, org_id: str | None = None) -> bool:
        scopes = self.roles.items() if org_id is None else [(org_id, self.roles.get(org_id, set()))]
        for _oid, rs in list(scopes) + [(o, r) for o, r in self.roles.items() if "platform_admin" in r]:
            for r in rs:
                perms = ROLE_PERMISSIONS.get(r, set())
                if "*" in perms or perm in perms:
                    return True
        return False

    @property
    def is_platform(self) -> bool:
        return bool(self.all_roles() & {"platform_admin", "platform_ops"})


def principal_from_token(token: str | None, db: Session) -> Principal:
    parsed = read_token(token) if token else None
    if not parsed:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "auth.required" if not token else "auth.invalid_session")
    uid, sid = parsed
    sess = db.get(m.AuthSession, sid)
    now = datetime.now(timezone.utc)
    if not sess or sess.user_id != uid or sess.revoked_at is not None or _aware(sess.expires_at) < now:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "auth.invalid_session")
    user = db.get(m.User, uid)
    if not user or user.status in ("deleted", "suspended"):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "auth.invalid_session")
    if (now - _aware(sess.last_seen_at)).total_seconds() > 60:  # throttle writes
        sess.last_seen_at = now
        db.commit()
    roles: dict[str, set[str]] = {}
    for ms in user.memberships:
        if (ms.org.settings or {}).get("suspended"):
            continue  # roles in a suspended organisation stop working
        roles.setdefault(ms.org_id, set()).add(ms.role)
    return Principal(user=user, roles=roles, session_id=sid)


def current_principal(request: Request, authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Principal:
    """Bearer header (API clients, scripts) or the HttpOnly session cookie (browser).
    Cookie-authenticated unsafe requests must carry `X-CSRF-Token` equal to the CSRF cookie."""
    if authorization and authorization.lower().startswith("bearer "):
        p = principal_from_token(authorization.split(" ", 1)[1], db)
    else:
        token = request.cookies.get(SESSION_COOKIE)
        if token and request.method not in SAFE_METHODS:
            sent, cookie = request.headers.get(CSRF_HEADER, ""), request.cookies.get(CSRF_COOKIE, "")
            if not sent or not cookie or not hmac.compare_digest(sent, cookie):
                raise ApiError(403, "auth.csrf")
        p = principal_from_token(token, db)
    from .mfa import ENROLMENT_ALLOWED_PATHS, required_for

    if p.user.mfa_enabled_at is None and required_for(p.all_roles()) and not request.url.path.startswith(ENROLMENT_ALLOWED_PATHS):
        raise ApiError(403, "auth.mfa_enrollment_required")
    return p


def require(perm: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.can(perm):
            raise ApiError(403, "auth.forbidden", permission=perm)
        return p

    return dep


def project_access(project_id: str, perm: str, p: Principal, db: Session) -> m.Project:
    """Server-side authorization + tenant isolation for every project resource."""
    proj = db.get(m.Project, project_id)
    if not proj:
        raise ApiError(404, "project.not_found")
    if p.is_platform and p.can(perm):
        return proj
    if proj.org_id not in p.org_ids or not p.can(perm, proj.org_id):
        # 404 instead of 403 so other tenants cannot probe for project ids
        raise ApiError(404, "project.not_found")
    return proj


def audit(db: Session, p: Principal | None, action: str, entity: str, entity_id: str | None, *, project_id: str | None = None, org_id: str | None = None, data: dict | None = None) -> None:
    db.add(m.AuditEvent(org_id=org_id, user_id=p.user.id if p else None, project_id=project_id, action=action, entity=entity, entity_id=entity_id, data=data or {}))
