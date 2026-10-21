"""Authentication (signed bearer tokens), password hashing, RBAC and tenant
isolation. Every project resource goes through `project_access`."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass

from fastapi import Depends, Header, status
from sqlalchemy.orm import Session

from . import models as m
from .config import get_settings
from .db import get_db
from .errors import ApiError

TOKEN_TTL_S = 60 * 60 * 12

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


def issue_token(user_id: str) -> str:
    payload = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_S}).encode())
    sig = _b64(hmac.new(get_settings().secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_token(token: str) -> str | None:
    try:
        payload, sig = token.split(".")
    except ValueError:
        return None
    good = _b64(hmac.new(get_settings().secret_key.encode(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(good, sig):
        return None
    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    if data.get("exp", 0) < time.time():
        return None
    return data.get("sub")


@dataclass
class Principal:
    user: m.User
    roles: dict[str, set[str]]  # org_id -> roles

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


def current_principal(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Principal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "auth.required")
    uid = read_token(authorization.split(" ", 1)[1])
    user = db.get(m.User, uid) if uid else None
    if not user:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "auth.invalid_session")
    roles: dict[str, set[str]] = {}
    for ms in user.memberships:
        roles.setdefault(ms.org_id, set()).add(ms.role)
    return Principal(user=user, roles=roles)


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
