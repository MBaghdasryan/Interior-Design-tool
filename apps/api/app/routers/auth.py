from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..security import Principal, current_principal, issue_token, verify_password
from ..seed import DEMO_PASSWORD, DEMO_USERS

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    password: str


def me_dict(p: Principal) -> dict:
    return {"id": p.user.id, "email": p.user.email, "name": p.user.name, "locale": p.user.locale,
            "memberships": [{"org_id": ms.org_id, "org_name": ms.org.name, "org_kind": ms.org.kind, "role": ms.role} for ms in p.user.memberships],
            "roles": sorted(p.all_roles())}


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(m.User).where(m.User.email == body.email.lower().strip()))
    if not u or not verify_password(body.password, u.password_hash):
        raise ApiError(401, "auth.bad_credentials")
    db.add(m.AuditEvent(user_id=u.id, action="auth.login", entity="user", entity_id=u.id))
    db.commit()
    return {"token": issue_token(u.id)}


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


@router.get("/demo-accounts")
def demo_accounts():
    if get_settings().env == "production":
        raise ApiError(404, "not_found")
    return [{"email": e, "name": n, "role": r, "password": DEMO_PASSWORD} for e, n, _, r in DEMO_USERS]
