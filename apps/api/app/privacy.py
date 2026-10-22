"""Personal data: export (ZIP), account deletion with a grace period, consent records,
and the purge executed by the worker when the grace period ends.

Deletion policy: the account is anonymised (e-mail, name, password, MFA, consents),
sessions/tokens are removed. Projects of an organisation where the user is the only
member are deleted with their stored files; organisations with other members keep
their projects (they are the organisation's records), only the person's name is removed
from them. Audit events stay (security/legal) but reference an anonymised user."""
from __future__ import annotations

import io
import json
import logging
import zipfile
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .config import get_settings
from .storage import get_storage

log = logging.getLogger("forma.privacy")
CONSENT_KEYS = {"marketing_emails", "product_analytics"}
EXPORT_FILE_BUDGET = 200 * 1024 * 1024  # embedded project files; larger exports list files instead


def _iso(d):
    return d.isoformat() if isinstance(d, datetime) else d


def export_zip(db: Session, user: m.User) -> bytes:
    buf = io.BytesIO()
    st = get_storage()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        profile = {"id": user.id, "email": user.email, "name": user.name, "locale": user.locale, "created_at": _iso(user.created_at),
                   "email_verified_at": _iso(user.email_verified_at), "mfa_enabled": user.mfa_enabled_at is not None, "consents": user.consents,
                   "memberships": [{"organisation": ms.org.name, "kind": ms.org.kind, "role": ms.role} for ms in user.memberships]}
        z.writestr("profile.json", json.dumps(profile, ensure_ascii=False, indent=1))
        sessions = db.scalars(select(m.AuthSession).where(m.AuthSession.user_id == user.id)).all()
        z.writestr("sessions.json", json.dumps([{"created_at": _iso(s.created_at), "last_seen_at": _iso(s.last_seen_at), "ip": s.ip,
                                                  "device": s.user_agent, "revoked_at": _iso(s.revoked_at)} for s in sessions], ensure_ascii=False, indent=1))
        events = db.scalars(select(m.AuditEvent).where(m.AuditEvent.user_id == user.id).order_by(m.AuditEvent.created_at)).all()
        z.writestr("activity.json", json.dumps([{"at": _iso(e.created_at), "action": e.action, "entity": e.entity, "data": e.data} for e in events],
                                               ensure_ascii=False, indent=1, default=str))
        budget = EXPORT_FILE_BUDGET
        projects = db.scalars(select(m.Project).where(m.Project.owner_id == user.id)).all()
        for p in projects:
            base = f"projects/{p.id}"
            z.writestr(f"{base}/project.json", json.dumps({"title": p.title, "address": p.address, "city": p.city, "area_m2": p.area_m2,
                                                            "preferences": p.preferences, "brief": p.brief, "client_name": p.client_name,
                                                            "created_at": _iso(p.created_at)}, ensure_ascii=False, indent=1, default=str))
            listed = []
            for a in db.scalars(select(m.SourceAsset).where(m.SourceAsset.project_id == p.id)):
                if a.scan_status == "purged" or not st.exists(a.storage_key):
                    continue
                if a.size <= budget:
                    z.writestr(f"{base}/files/{a.filename}", st.get(a.storage_key))
                    budget -= a.size
                else:
                    listed.append(a.filename)
            if listed:
                z.writestr(f"{base}/files_not_embedded.txt", "\n".join(listed))
            comments = db.scalars(select(m.Comment).where(m.Comment.project_id == p.id)).all()
            z.writestr(f"{base}/comments.json", json.dumps([{"at": _iso(c.created_at), "author": c.author_name, "body": c.body} for c in comments],
                                                            ensure_ascii=False, indent=1))
        z.writestr("README.txt", "Renovara personal data export. JSON files are UTF-8. Generated " + datetime.now(timezone.utc).isoformat())
    return buf.getvalue()


def set_consents(user: m.User, changes: dict[str, bool], ip: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    c = dict(user.consents or {})
    history = list(c.get("history", []))
    for k, v in changes.items():
        if k in CONSENT_KEYS and c.get(k, {}).get("granted") != v:
            c[k] = {"granted": bool(v), "at": now}
            history.append({"key": k, "granted": bool(v), "at": now, "ip": ip})
    c["history"] = history[-200:]
    user.consents = c
    return c


def request_deletion(user: m.User) -> datetime:
    user.status = "deletion_pending"
    user.deletion_due_at = datetime.now(timezone.utc) + timedelta(days=get_settings().privacy_deletion_grace_days)
    return user.deletion_due_at


def cancel_deletion(user: m.User) -> None:
    user.status, user.deletion_due_at = "active", None


def purge_due_accounts(db: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    st = get_storage()
    n = 0
    for u in db.scalars(select(m.User).where(m.User.status == "deletion_pending")).all():
        due = u.deletion_due_at if (u.deletion_due_at is None or u.deletion_due_at.tzinfo) else u.deletion_due_at.replace(tzinfo=timezone.utc)
        if not due or due > now:
            continue
        name = u.name
        for ms in list(u.memberships):
            others = db.scalars(select(m.Membership).where(m.Membership.org_id == ms.org_id, m.Membership.user_id != u.id)).first()
            if others is None and ms.org.kind in ("bureau", "supplier", "client"):
                for p in db.scalars(select(m.Project).where(m.Project.org_id == ms.org_id)).all():
                    for key, _ in st.list(f"projects/{p.id}/"):
                        st.delete(key)
                    db.delete(p)
            else:
                for p in db.scalars(select(m.Project).where(m.Project.org_id == ms.org_id, m.Project.designer_name == name)):
                    p.designer_name = ""
            db.delete(ms)
        db.flush()
        db.expire(u, ["memberships"])
        for s in db.scalars(select(m.AuthSession).where(m.AuthSession.user_id == u.id)):
            db.delete(s)
        for t in db.scalars(select(m.AuthToken).where(m.AuthToken.user_id == u.id)):
            db.delete(t)
        u.email, u.name = f"deleted+{u.id}@invalid", "—"
        u.password_hash, u.consents = "!", {}
        u.mfa_secret_enc = u.mfa_pending_enc = None
        u.mfa_enabled_at, u.mfa_backup_codes = None, []
        u.status, u.deletion_due_at = "deleted", None
        db.add(m.AuditEvent(user_id=u.id, action="privacy.account_purged", entity="user", entity_id=u.id, data={}))
        n += 1
    db.commit()
    if n:
        log.info("purged %d accounts", n)
    return n
