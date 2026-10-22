"""In-app notification centre (bell) and per-user notification preferences."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..db import get_db
from ..errors import ApiError
from ..notify import KINDS
from ..security import Principal, current_principal

router = APIRouter(prefix="/api/v1", tags=["notifications"])


def n_dict(n: m.Notification) -> dict:
    return {"id": n.id, "kind": n.kind, "params": n.params, "link": n.link, "project_id": n.project_id, "read": n.read_at is not None,
            "created_at": n.created_at.isoformat()}


@router.get("/notifications")
def list_notifications(unread_only: bool = False, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    q = select(m.Notification).where(m.Notification.user_id == p.user.id)
    if unread_only:
        q = q.where(m.Notification.read_at.is_(None))
    rows = db.scalars(q.order_by(m.Notification.created_at.desc()).limit(50)).all()
    unread = db.scalar(select(func.count()).select_from(m.Notification).where(m.Notification.user_id == p.user.id, m.Notification.read_at.is_(None)))
    return {"items": [n_dict(n) for n in rows], "unread": unread or 0}


@router.post("/notifications/{nid}/read")
def read_notification(nid: str, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    n = db.get(m.Notification, nid)
    if not n or n.user_id != p.user.id:
        raise ApiError(404, "not_found")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()
    return n_dict(n)


@router.post("/notifications/read-all")
def read_all(p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    for n in db.scalars(select(m.Notification).where(m.Notification.user_id == p.user.id, m.Notification.read_at.is_(None))):
        n.read_at = now
    db.commit()
    return {"ok": True}


@router.get("/auth/me/notification-prefs")
def get_prefs(p: Principal = Depends(current_principal)):
    prefs = p.user.notification_prefs or {}
    return {"kinds": {k: prefs.get("kinds", {}).get(k, True) for k in KINDS}, "email_digest": prefs.get("email_digest", True)}


class PrefsIn(BaseModel):
    kinds: dict[str, bool] = {}
    email_digest: bool | None = None


@router.put("/auth/me/notification-prefs")
def put_prefs(body: PrefsIn, p: Principal = Depends(current_principal), db: Session = Depends(get_db)):
    prefs = dict(p.user.notification_prefs or {})
    kinds = dict(prefs.get("kinds", {}))
    kinds.update({k: v for k, v in body.kinds.items() if k in KINDS})
    prefs["kinds"] = kinds
    if body.email_digest is not None:
        prefs["email_digest"] = body.email_digest
    p.user.notification_prefs = prefs
    db.commit()
    return get_prefs(p)
