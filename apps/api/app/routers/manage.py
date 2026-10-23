"""Administration (users, organisations, suppliers), organisation teams and manual product management.

Who can do what:
* platform admin (`users:manage`) — every user and organisation, any supplier and product;
* bureau admin (`team:manage`) / supplier admin (`supplier:manage`) — the team of their own organisation;
* catalogue writers (`catalog:write`) — products: platform staff for any supplier, a supplier's staff only its own.
Nothing is hard-deleted that other records depend on: users are suspended or go through the privacy
deletion flow, products are archived (hidden from catalogue and design, kept for existing estimates)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..catalog.taxonomy import CATEGORIES, STYLES
from ..config import get_settings
from ..db import get_db
from ..errors import ApiError
from ..mail import send_template
from ..security import Principal, audit, current_principal, hash_password, new_one_time_token, require, revoke_sessions

router = APIRouter(prefix="/api/v1", tags=["manage"])
ORG_ROLES = {"platform": {"platform_admin", "platform_ops", "linguist"},
             "bureau": {"bureau_admin", "designer", "collaborator"},
             "supplier": {"supplier_admin", "supplier_catalog", "manufacturer", "installer"}}
TEAM_ADMIN = {"bureau": ("team:manage", "bureau_admin"), "supplier": ("supplier:manage", "supplier_admin")}
INVITE_TTL_H = 72


def _invite(db: Session, user: m.User, org: m.Organization) -> None:
    """New account created by an admin: the person sets a password through a one-time link (the reset flow)."""
    s = get_settings()
    raw = new_one_time_token(db, user, "password_reset", INVITE_TTL_H * 3600)
    db.commit()
    send_template(user.email, "invite", user.locale, name=user.name, org=org.name, link=f"{s.public_base_url.rstrip('/')}/reset-password?token={raw}", hours=INVITE_TTL_H)


def user_dict(db: Session, u: m.User) -> dict:
    last = db.scalar(select(func.max(m.AuthSession.last_seen_at)).where(m.AuthSession.user_id == u.id))
    return {"id": u.id, "email": u.email, "name": u.name, "locale": u.locale, "status": u.status, "email_verified": u.email_verified_at is not None,
            "mfa": u.mfa_enabled_at is not None, "created_at": u.created_at.isoformat() if u.created_at else None, "last_seen_at": last.isoformat() if last else None,
            "memberships": [{"id": ms.id, "org_id": ms.org_id, "org_name": ms.org.name, "org_kind": ms.org.kind, "role": ms.role} for ms in u.memberships]}


def _check_role(org: m.Organization, role: str) -> None:
    if role not in ORG_ROLES.get(org.kind, set()):
        raise ApiError(422, "validation", fields=["role"])


def _last_admin(db: Session, org_id: str, role: str, user_id: str) -> bool:
    others = db.scalar(select(func.count(m.Membership.id)).where(m.Membership.org_id == org_id, m.Membership.role == role, m.Membership.user_id != user_id))
    return not others


# ------------------------------------------------------------------ platform: users
@router.get("/admin/users")
def list_users(q: str = "", status: str = "", org_id: str = "", role: str = "", limit: int = Query(200, le=500),
               p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    stmt = select(m.User).where(m.User.status != "deleted")
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(m.User.email).like(like), func.lower(m.User.name).like(like)))
    if status:
        stmt = stmt.where(m.User.status == status)
    if org_id or role:
        sub = select(m.Membership.user_id)
        if org_id:
            sub = sub.where(m.Membership.org_id == org_id)
        if role:
            sub = sub.where(m.Membership.role == role)
        stmt = stmt.where(m.User.id.in_(sub))
    users = db.scalars(stmt.order_by(m.User.created_at.desc()).limit(limit)).all()
    counts = dict(db.execute(select(m.User.status, func.count()).group_by(m.User.status)).all())
    return {"items": [user_dict(db, u) for u in users], "counts": counts}


class NewUserIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=1, max_length=200)
    org_id: str
    role: str
    locale: str = Field(default="hy", pattern="^(hy|ru|en)$")


@router.post("/admin/users")
def create_user(body: NewUserIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    org = db.get(m.Organization, body.org_id)
    if not org:
        raise ApiError(404, "not_found")
    _check_role(org, body.role)
    email = body.email.strip().lower()
    if db.scalar(select(m.User.id).where(m.User.email == email)):
        raise ApiError(409, "user.exists")
    import secrets

    u = m.User(email=email, name=body.name.strip(), locale=body.locale, password_hash=hash_password(secrets.token_urlsafe(24)),
               email_verified_at=datetime.now(timezone.utc), onboarded_at=datetime.now(timezone.utc))
    db.add(u)
    db.flush()
    db.add(m.Membership(user_id=u.id, org_id=org.id, role=body.role))
    audit(db, p, "user.create", "user", u.id, org_id=org.id, data={"role": body.role})
    db.commit()
    _invite(db, u, org)
    db.refresh(u)
    return user_dict(db, u)


class UserPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    locale: str | None = Field(default=None, pattern="^(hy|ru|en)$")
    status: str | None = Field(default=None, pattern="^(active|suspended)$")


@router.patch("/admin/users/{uid}")
def patch_user(uid: str, body: UserPatch, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    u = db.get(m.User, uid)
    if not u or u.status == "deleted":
        raise ApiError(404, "not_found")
    if body.status == "suspended" and u.id == p.user.id:
        raise ApiError(409, "user.self_action")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(u, k, v)
    if body.status == "suspended":
        revoke_sessions(db, u.id)  # a suspended account is signed out everywhere
    audit(db, p, "user.update", "user", uid, data=body.model_dump(exclude_none=True))
    db.commit()
    return user_dict(db, u)


class MembershipIn(BaseModel):
    org_id: str
    role: str


@router.post("/admin/users/{uid}/memberships")
def add_membership(uid: str, body: MembershipIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    u, org = db.get(m.User, uid), db.get(m.Organization, body.org_id)
    if not u or not org:
        raise ApiError(404, "not_found")
    _check_role(org, body.role)
    if not db.scalar(select(m.Membership.id).where(m.Membership.user_id == uid, m.Membership.org_id == org.id, m.Membership.role == body.role)):
        db.add(m.Membership(user_id=uid, org_id=org.id, role=body.role))
    audit(db, p, "user.role_add", "user", uid, org_id=org.id, data={"role": body.role})
    db.commit()
    db.refresh(u)
    return user_dict(db, u)


@router.delete("/admin/users/{uid}/memberships/{mid}")
def remove_membership(uid: str, mid: str, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    ms = db.get(m.Membership, mid)
    if not ms or ms.user_id != uid:
        raise ApiError(404, "not_found")
    if ms.role == "platform_admin" and _last_admin(db, ms.org_id, "platform_admin", uid):
        raise ApiError(409, "user.last_admin")
    audit(db, p, "user.role_remove", "user", uid, org_id=ms.org_id, data={"role": ms.role})
    db.delete(ms)
    db.commit()
    u = db.get(m.User, uid)
    db.refresh(u)
    return user_dict(db, u)


@router.post("/admin/users/{uid}/reset-password")
def admin_reset_password(uid: str, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    u = db.get(m.User, uid)
    if not u or u.status == "deleted":
        raise ApiError(404, "not_found")
    s = get_settings()
    raw = new_one_time_token(db, u, "password_reset", s.reset_token_ttl_min * 60)
    audit(db, p, "user.reset_password", "user", uid)
    db.commit()
    send_template(u.email, "password_reset", u.locale, name=u.name, link=f"{s.public_base_url.rstrip('/')}/reset-password?token={raw}", minutes=s.reset_token_ttl_min)
    return {"ok": True}


@router.post("/admin/users/{uid}/revoke-sessions")
def admin_revoke_sessions(uid: str, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    if not db.get(m.User, uid):
        raise ApiError(404, "not_found")
    n = revoke_sessions(db, uid, except_sid=p.session_id if uid == p.user.id else None)
    audit(db, p, "user.revoke_sessions", "user", uid, data={"n": n})
    db.commit()
    return {"revoked": n}


@router.post("/admin/users/{uid}/reset-mfa")
def admin_reset_mfa(uid: str, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    """Lost phone: the second factor is removed; enforced roles must enrol again at the next sign-in."""
    u = db.get(m.User, uid)
    if not u:
        raise ApiError(404, "not_found")
    u.mfa_secret_enc = u.mfa_pending_enc = None
    u.mfa_enabled_at = None
    u.mfa_backup_codes = []
    revoke_sessions(db, uid)
    audit(db, p, "user.reset_mfa", "user", uid)
    db.commit()
    return user_dict(db, u)


@router.delete("/admin/users/{uid}")
def delete_user(uid: str, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    """Deletion goes through the privacy flow (grace period, then anonymisation) — never a silent hard delete."""
    u = db.get(m.User, uid)
    if not u or u.status == "deleted":
        raise ApiError(404, "not_found")
    if u.id == p.user.id:
        raise ApiError(409, "user.self_action")
    if any(ms.role == "platform_admin" and _last_admin(db, ms.org_id, "platform_admin", uid) for ms in u.memberships):
        raise ApiError(409, "user.last_admin")
    u.status = "deletion_pending"
    u.deletion_due_at = datetime.now(timezone.utc) + timedelta(days=get_settings().privacy_deletion_grace_days)
    revoke_sessions(db, uid)
    audit(db, p, "user.delete_requested", "user", uid)
    db.commit()
    return user_dict(db, u)


# ------------------------------------------------------------------ platform: organisations
def org_dict(db: Session, o: m.Organization) -> dict:
    users = db.scalar(select(func.count(func.distinct(m.Membership.user_id))).where(m.Membership.org_id == o.id)) or 0
    projects = db.scalar(select(func.count(m.Project.id)).where(m.Project.org_id == o.id)) or 0
    sup = db.scalar(select(m.Supplier).where(m.Supplier.org_id == o.id).limit(1))
    return {"id": o.id, "name": o.name, "kind": o.kind, "status": "suspended" if (o.settings or {}).get("suspended") else "active",
            "plan": (o.settings or {}).get("plan"), "users": users, "projects": projects, "supplier_id": sup.id if sup else None,
            "created_at": o.created_at.isoformat() if o.created_at else None}


@router.get("/admin/organizations")
def list_organizations(kind: str = "", q: str = "", p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    stmt = select(m.Organization)
    if kind:
        stmt = stmt.where(m.Organization.kind == kind)
    if q:
        stmt = stmt.where(func.lower(m.Organization.name).like(f"%{q.lower()}%"))
    return [org_dict(db, o) for o in db.scalars(stmt.order_by(m.Organization.name))]


class OrgIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: str = Field(pattern="^(bureau|supplier)$")


@router.post("/admin/organizations")
def create_organization(body: OrgIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    o = m.Organization(name=body.name.strip(), kind=body.kind, settings={})
    db.add(o)
    db.flush()
    audit(db, p, "org.create", "organization", o.id, org_id=o.id, data={"kind": body.kind})
    db.commit()
    return org_dict(db, o)


class OrgPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    status: str | None = Field(default=None, pattern="^(active|suspended)$")


@router.patch("/admin/organizations/{oid}")
def patch_organization(oid: str, body: OrgPatch, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    o = db.get(m.Organization, oid)
    if not o:
        raise ApiError(404, "not_found")
    if body.status and o.kind == "platform":
        raise ApiError(409, "org.platform_locked")
    if body.name:
        o.name = body.name.strip()
    if body.status:
        o.settings = {**(o.settings or {}), "suspended": body.status == "suspended"}
        if body.status == "suspended":  # members are signed out; their roles in this organisation stop working
            for ms in db.scalars(select(m.Membership).where(m.Membership.org_id == oid)):
                revoke_sessions(db, ms.user_id)
    audit(db, p, "org.update", "organization", oid, org_id=oid, data=body.model_dump(exclude_none=True))
    db.commit()
    return org_dict(db, o)


# ------------------------------------------------------------------ organisation team (bureau / supplier admins)
def _team_org(p: Principal, db: Session, org_id: str | None) -> m.Organization:
    """Own organisation of the caller (a bureau or supplier admin); platform admins may pass any org_id."""
    if org_id and p.can("users:manage"):
        org = db.get(m.Organization, org_id)
    else:
        org = next((o for o in (db.get(m.Organization, i) for i in p.org_ids) if o and o.kind in TEAM_ADMIN
                    and TEAM_ADMIN[o.kind][1] in p.roles.get(o.id, set())), None)
    if not org or org.kind not in TEAM_ADMIN:
        raise ApiError(403, "auth.forbidden")
    return org


def member_dict(db: Session, ms: m.Membership) -> dict:
    last = db.scalar(select(func.max(m.AuthSession.last_seen_at)).where(m.AuthSession.user_id == ms.user_id))
    return {"membership_id": ms.id, "user_id": ms.user_id, "name": ms.user.name, "email": ms.user.email, "role": ms.role, "status": ms.user.status,
            "email_verified": ms.user.email_verified_at is not None, "mfa": ms.user.mfa_enabled_at is not None, "last_seen_at": last.isoformat() if last else None}


@router.get("/team")
def team(org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _team_org(p, db, org_id)
    rows = db.scalars(select(m.Membership).where(m.Membership.org_id == org.id).order_by(m.Membership.role)).all()
    return {"org": {"id": org.id, "name": org.name, "kind": org.kind}, "roles": sorted(ORG_ROLES[org.kind]), "members": [member_dict(db, ms) for ms in rows]}


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    name: str = Field(min_length=1, max_length=200)
    role: str
    locale: str = Field(default="hy", pattern="^(hy|ru|en)$")


@router.post("/team/invite")
def team_invite(body: InviteIn, org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    """Adds an existing account to the organisation, or creates one and e-mails a link to set the password."""
    org = _team_org(p, db, org_id)
    _check_role(org, body.role)
    email = body.email.strip().lower()
    u = db.scalar(select(m.User).where(m.User.email == email))
    created = False
    if u is None:
        import secrets

        u = m.User(email=email, name=body.name.strip(), locale=body.locale, password_hash=hash_password(secrets.token_urlsafe(24)),
                   email_verified_at=datetime.now(timezone.utc), onboarded_at=datetime.now(timezone.utc))
        db.add(u)
        db.flush()
        created = True
    elif u.status != "active":
        raise ApiError(409, "user.inactive")
    if db.scalar(select(m.Membership.id).where(m.Membership.user_id == u.id, m.Membership.org_id == org.id, m.Membership.role == body.role)):
        raise ApiError(409, "team.already_member")
    ms = m.Membership(user_id=u.id, org_id=org.id, role=body.role)
    db.add(ms)
    audit(db, p, "team.invite", "user", u.id, org_id=org.id, data={"role": body.role, "new_account": created})
    db.commit()
    if created:
        _invite(db, u, org)
    from ..notify import notify

    if not created:
        notify(db, [u], "catalog_alert", params={"source": org.name, "reason": "team_added"}, link="/app")
        db.commit()
    db.refresh(ms)
    return member_dict(db, ms)


class RoleIn(BaseModel):
    role: str


@router.patch("/team/{mid}")
def team_role(mid: str, body: RoleIn, org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _team_org(p, db, org_id)
    ms = db.get(m.Membership, mid)
    if not ms or ms.org_id != org.id:
        raise ApiError(404, "not_found")
    _check_role(org, body.role)
    admin_role = TEAM_ADMIN[org.kind][1]
    if ms.role == admin_role and body.role != admin_role and _last_admin(db, org.id, admin_role, ms.user_id):
        raise ApiError(409, "user.last_admin")
    ms.role = body.role
    audit(db, p, "team.role", "user", ms.user_id, org_id=org.id, data={"role": body.role})
    db.commit()
    return member_dict(db, ms)


@router.delete("/team/{mid}")
def team_remove(mid: str, org_id: str | None = None, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    org = _team_org(p, db, org_id)
    ms = db.get(m.Membership, mid)
    if not ms or ms.org_id != org.id:
        raise ApiError(404, "not_found")
    admin_role = TEAM_ADMIN[org.kind][1]
    if ms.role == admin_role and _last_admin(db, org.id, admin_role, ms.user_id):
        raise ApiError(409, "user.last_admin")
    audit(db, p, "team.remove", "user", ms.user_id, org_id=org.id, data={"role": ms.role})
    db.delete(ms)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ platform: suppliers
def supplier_row(db: Session, s: m.Supplier) -> dict:
    n = db.scalar(select(func.count(m.Product.id)).where(m.Product.supplier_id == s.id, m.Product.status == "active")) or 0
    return {"id": s.id, "name": s.name, "slug": s.slug, "kind": s.kind, "city": s.city, "website": s.website, "is_demo": s.is_demo, "verification": s.verification,
            "commission_pct": s.commission_pct, "org_id": s.org_id, "org_name": (db.get(m.Organization, s.org_id).name if s.org_id else None), "products": n,
            "contacts": s.contacts, "delivery": s.delivery}


@router.get("/admin/suppliers/all")
def all_suppliers(q: str = "", p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    stmt = select(m.Supplier)
    if q:
        stmt = stmt.where(func.lower(m.Supplier.name).like(f"%{q.lower()}%"))
    return [supplier_row(db, s) for s in db.scalars(stmt.order_by(m.Supplier.is_demo, m.Supplier.name))]


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    kind: str = Field(default="store", pattern="^(store|manufacturer|installer)$")
    city: str = Field(default="Ереван", max_length=100)
    website: str = Field(default="", max_length=300)
    commission_pct: float = Field(default=0, ge=0, le=50)
    org_id: str | None = None
    verification: str = Field(default="verified", pattern="^(pending|verified|rejected)$")
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=200)


@router.post("/admin/suppliers")
def create_supplier(body: SupplierIn, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    if body.org_id and (not (o := db.get(m.Organization, body.org_id)) or o.kind != "supplier"):
        raise ApiError(422, "validation", fields=["org_id"])
    base = "".join(ch if ch.isalnum() else "-" for ch in body.name.lower()).strip("-")[:50] or "supplier"
    slug, n = base, 1
    while db.scalar(select(m.Supplier.id).where(m.Supplier.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    s = m.Supplier(name=body.name.strip(), slug=slug, kind=body.kind, city=body.city or "Ереван", website=body.website, commission_pct=body.commission_pct,
                   org_id=body.org_id, verification=body.verification, is_demo=False, contacts={"phone": body.phone, "email": body.email})
    db.add(s)
    db.flush()
    audit(db, p, "supplier.create", "supplier", s.id, data={"name": s.name})
    db.commit()
    return supplier_row(db, s)


class SupplierPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    kind: str | None = Field(default=None, pattern="^(store|manufacturer|installer)$")
    city: str | None = Field(default=None, max_length=100)
    website: str | None = Field(default=None, max_length=300)
    commission_pct: float | None = Field(default=None, ge=0, le=50)
    org_id: str | None = None
    verification: str | None = Field(default=None, pattern="^(pending|verified|rejected)$")
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)


@router.patch("/admin/suppliers/{sid}")
def patch_supplier(sid: str, body: SupplierPatch, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    s = db.get(m.Supplier, sid)
    if not s:
        raise ApiError(404, "not_found")
    data = body.model_dump(exclude_none=True)
    if "org_id" in data and data["org_id"] and (not (o := db.get(m.Organization, data["org_id"])) or o.kind != "supplier"):
        raise ApiError(422, "validation", fields=["org_id"])
    contacts = dict(s.contacts or {})
    for k in ("phone", "email"):
        if k in data:
            contacts[k] = data.pop(k)
    s.contacts = contacts
    for k, v in data.items():
        setattr(s, k, v)
    audit(db, p, "supplier.update", "supplier", sid, data=body.model_dump(exclude_none=True))
    db.commit()
    return supplier_row(db, s)


@router.delete("/admin/suppliers/{sid}")
def delete_supplier(sid: str, p: Principal = Depends(require("users:manage")), db: Session = Depends(get_db)):
    """A supplier with orders is kept (history, ledger); otherwise it is removed with its catalogue."""
    s = db.get(m.Supplier, sid)
    if not s:
        raise ApiError(404, "not_found")
    if db.scalar(select(m.Order.id).where(m.Order.supplier_id == sid, m.Order.status != "cart").limit(1)):
        raise ApiError(409, "supplier.has_orders")
    for prod in db.scalars(select(m.Product).where(m.Product.supplier_id == sid)):
        db.delete(prod)
    audit(db, p, "supplier.delete", "supplier", sid, data={"name": s.name})
    db.delete(s)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ products: manual create / edit / archive
def _writable_supplier(p: Principal, db: Session, supplier_id: str) -> m.Supplier:
    s = db.get(m.Supplier, supplier_id)
    if not s:
        raise ApiError(404, "not_found")
    if p.is_platform and p.can("catalog:write"):
        return s
    if s.org_id and s.org_id in p.org_ids and p.can("catalog:write", s.org_id):
        return s
    raise ApiError(403, "auth.forbidden")


class VariantIn(BaseModel):
    sku: str = Field(min_length=1, max_length=120)
    color: str = Field(default="", max_length=80)
    color_hex: str = Field(default="#cccccc", pattern=r"^#[0-9a-fA-F]{6}$")
    material: str = Field(default="", max_length=120)
    width_mm: float = Field(default=0, ge=0, le=20000)
    depth_mm: float = Field(default=0, ge=0, le=20000)
    height_mm: float = Field(default=0, ge=0, le=20000)
    price: float | None = Field(default=None, ge=0)
    currency: str = Field(default="AMD", pattern="^(AMD|USD|EUR|RUB)$")
    stock_status: str = Field(default="unknown", pattern="^(in_stock|to_order|out_of_stock|unknown)$")
    lead_time_days: int | None = Field(default=None, ge=0, le=365)
    url: str = Field(default="", max_length=500)
    image_url: str = Field(default="", max_length=500)


class ProductIn(BaseModel):
    supplier_id: str
    category: str
    name_ru: str = Field(min_length=1, max_length=300)
    name_hy: str = Field(default="", max_length=300)
    name_en: str = Field(default="", max_length=300)
    brand: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=4000)
    tier: str = Field(default="comfort", pattern="^(economy|comfort|business|premium)$")
    styles: list[str] = []
    unit: str = Field(default="pcs", pattern="^(pcs|m2|pack|l|kg|m)$")
    package_coverage_m2: float | None = Field(default=None, gt=0)
    item_type: str = Field(default="serial", pattern="^(serial|made_to_order|parametric|service|material|kit|custom)$")
    variants: list[VariantIn] = Field(default_factory=list, min_length=1)


def product_dict(prod: m.Product) -> dict:
    return {"id": prod.id, "supplier_id": prod.supplier_id, "supplier_name": prod.supplier.name if prod.supplier else "", "category": prod.category,
            "name_ru": prod.name_ru, "name_hy": prod.name_hy, "name_en": prod.name_en, "brand": prod.brand, "description": prod.description, "tier": prod.tier,
            "styles": prod.styles, "unit": prod.unit, "package_coverage_m2": prod.package_coverage_m2, "item_type": prod.item_type, "status": prod.status,
            "is_demo": prod.is_demo,
            "variants": [{"id": v.id, "sku": v.sku, "color": v.color, "color_hex": v.color_hex, "material": v.material, "width_mm": v.width_mm, "depth_mm": v.depth_mm,
                          "height_mm": v.height_mm, "price": v.price, "currency": v.currency, "price_status": v.price_status, "stock_status": v.stock_status,
                          "lead_time_days": v.lead_time_days, "url": v.url, "image_url": v.image_url, "has_3d": bool(v.model3d_url),
                          "price_checked_at": v.price_checked_at.isoformat() if v.price_checked_at else None} for v in prod.variants]}


def _validate_product(body) -> None:
    if body.category not in CATEGORIES:
        raise ApiError(422, "validation", fields=["category"])
    if any(s not in STYLES for s in body.styles):
        raise ApiError(422, "validation", fields=["styles"])


def _apply_variant(v: m.ProductVariant, data: dict, db: Session) -> None:
    now = datetime.now(timezone.utc)
    if "price" in data and data["price"] != v.price and data["price"] is not None:
        db.add(m.PriceHistory(variant_id=v.id, price=data["price"], currency=data.get("currency", v.currency), source="manual"))
    for k, val in data.items():
        setattr(v, k, val)
    if "price" in data:
        v.price_status = "confirmed" if v.price is not None else "quote_required"
        v.price_checked_at = now
    if "stock_status" in data:
        v.availability_checked_at = now


def _can_write(p: Principal, db: Session, supplier_id: str) -> bool:
    try:
        _writable_supplier(p, db, supplier_id)
        return True
    except ApiError:
        return False


@router.get("/catalog/products/{product_id}/detail")
def product_detail(product_id: str, p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    prod = db.get(m.Product, product_id)
    if not prod:
        raise ApiError(404, "product.not_found")
    return {**product_dict(prod), "can_edit": _can_write(p, db, prod.supplier_id)}


@router.get("/catalog/variants/{vid}/product")
def product_of_variant(vid: str, p: Principal = Depends(require("catalog:read")), db: Session = Depends(get_db)):
    """The catalogue lists variants (`pv:<id>`); the editor opens the whole product."""
    v = db.get(m.ProductVariant, vid)
    if not v:
        raise ApiError(404, "product.not_found")
    return {**product_dict(v.product), "can_edit": _can_write(p, db, v.product.supplier_id)}


@router.post("/catalog/products")
def create_product(body: ProductIn, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    s = _writable_supplier(p, db, body.supplier_id)
    _validate_product(body)
    skus = [v.sku for v in body.variants]
    if len(set(skus)) != len(skus):
        raise ApiError(422, "validation", fields=["variants"])
    prod = m.Product(supplier_id=s.id, category=body.category, name_ru=body.name_ru.strip(), name_hy=body.name_hy.strip(), name_en=body.name_en.strip(), brand=body.brand,
                     description=body.description, tier=body.tier, styles=body.styles, unit=body.unit, package_coverage_m2=body.package_coverage_m2,
                     item_type=body.item_type, is_demo=s.is_demo)
    db.add(prod)
    db.flush()
    for vin in body.variants:
        v = m.ProductVariant(product_id=prod.id, sku=vin.sku)
        db.add(v)
        db.flush()
        _apply_variant(v, vin.model_dump(), db)
    audit(db, p, "product.create", "product", prod.id, data={"supplier": s.id, "variants": len(body.variants)})
    db.commit()
    db.refresh(prod)
    return product_dict(prod)


class ProductPatch(BaseModel):
    category: str | None = None
    name_ru: str | None = Field(default=None, min_length=1, max_length=300)
    name_hy: str | None = Field(default=None, max_length=300)
    name_en: str | None = Field(default=None, max_length=300)
    brand: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    tier: str | None = Field(default=None, pattern="^(economy|comfort|business|premium)$")
    styles: list[str] | None = None
    unit: str | None = Field(default=None, pattern="^(pcs|m2|pack|l|kg|m)$")
    package_coverage_m2: float | None = Field(default=None, gt=0)
    status: str | None = Field(default=None, pattern="^(active|archived)$")


@router.patch("/catalog/products/{product_id}")
def patch_product(product_id: str, body: ProductPatch, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    prod = db.get(m.Product, product_id)
    if not prod:
        raise ApiError(404, "product.not_found")
    _writable_supplier(p, db, prod.supplier_id)
    data = body.model_dump(exclude_none=True)
    if "category" in data and data["category"] not in CATEGORIES or any(s not in STYLES for s in data.get("styles", [])):
        raise ApiError(422, "validation", fields=["category"])
    for k, v in data.items():
        setattr(prod, k, v)
    audit(db, p, "product.update", "product", product_id, data={k: v for k, v in data.items() if k != "description"})
    db.commit()
    return product_dict(prod)


@router.delete("/catalog/products/{product_id}")
def archive_product(product_id: str, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    """Archived, not erased: existing estimates and albums keep referring to it; catalogue and design skip it."""
    prod = db.get(m.Product, product_id)
    if not prod:
        raise ApiError(404, "product.not_found")
    _writable_supplier(p, db, prod.supplier_id)
    prod.status = "archived"
    audit(db, p, "product.archive", "product", product_id)
    db.commit()
    return product_dict(prod)


@router.post("/catalog/products/{product_id}/variants")
def add_variant(product_id: str, body: VariantIn, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    prod = db.get(m.Product, product_id)
    if not prod:
        raise ApiError(404, "product.not_found")
    _writable_supplier(p, db, prod.supplier_id)
    if any(v.sku == body.sku for v in prod.variants):
        raise ApiError(409, "product.sku_exists")
    v = m.ProductVariant(product_id=prod.id, sku=body.sku)
    db.add(v)
    db.flush()
    _apply_variant(v, body.model_dump(), db)
    audit(db, p, "product.variant_add", "product", product_id, data={"sku": body.sku})
    db.commit()
    db.refresh(prod)
    return product_dict(prod)


class VariantPatch(BaseModel):
    sku: str | None = Field(default=None, min_length=1, max_length=120)
    color: str | None = Field(default=None, max_length=80)
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    material: str | None = Field(default=None, max_length=120)
    width_mm: float | None = Field(default=None, ge=0, le=20000)
    depth_mm: float | None = Field(default=None, ge=0, le=20000)
    height_mm: float | None = Field(default=None, ge=0, le=20000)
    price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, pattern="^(AMD|USD|EUR|RUB)$")
    stock_status: str | None = Field(default=None, pattern="^(in_stock|to_order|out_of_stock|unknown)$")
    lead_time_days: int | None = Field(default=None, ge=0, le=365)
    url: str | None = Field(default=None, max_length=500)
    image_url: str | None = Field(default=None, max_length=500)


@router.patch("/catalog/variants/{vid}")
def patch_variant(vid: str, body: VariantPatch, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    v = db.get(m.ProductVariant, vid)
    if not v:
        raise ApiError(404, "product.not_found")
    _writable_supplier(p, db, v.product.supplier_id)
    data = body.model_dump(exclude_none=True)
    if "sku" in data and any(o.sku == data["sku"] and o.id != v.id for o in v.product.variants):
        raise ApiError(409, "product.sku_exists")
    _apply_variant(v, data, db)
    audit(db, p, "product.variant_update", "product", v.product_id, data={k: val for k, val in data.items() if k in ("sku", "price", "stock_status")})
    db.commit()
    return product_dict(v.product)


@router.delete("/catalog/variants/{vid}")
def delete_variant(vid: str, p: Principal = Depends(require("catalog:write")), db: Session = Depends(get_db)):
    v = db.get(m.ProductVariant, vid)
    if not v:
        raise ApiError(404, "product.not_found")
    prod = v.product
    _writable_supplier(p, db, prod.supplier_id)
    if len(prod.variants) <= 1:
        raise ApiError(409, "product.last_variant")  # archive the product instead
    audit(db, p, "product.variant_delete", "product", prod.id, data={"sku": v.sku})
    db.delete(v)
    db.commit()
    db.refresh(prod)
    return product_dict(prod)
