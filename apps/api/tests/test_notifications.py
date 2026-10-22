"""P1-8: in-app notifications (events → rows), read state, per-user preferences, daily digest."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app import models as m
from app.db import SessionLocal
from app.jobs import runner
from app.notify import send_digests

pytestmark = pytest.mark.usefixtures("client")


def _project(db):
    return db.query(m.Project).filter(m.Project.title.like("Демо%")).first()


def _variant(db, proj) -> str:
    v = db.query(m.DesignVariant).filter_by(project_id=proj.id).first()
    if not v:
        v = m.DesignVariant(project_id=proj.id, key="n1", title="N", style="modern", tier="comfort")
        db.add(v)
        db.flush()
        ver = m.DesignVersion(variant_id=v.id, number=1, scene={})
        db.add(ver)
        db.flush()
        v.current_version_id = ver.id
        db.commit()
    return v.id


def _clear(db, uid):
    db.query(m.Notification).filter_by(user_id=uid).delete()
    db.commit()


def test_events_create_notifications_and_read_state(client, designer, admin):
    with SessionLocal() as db:
        proj = _project(db)
        owner = proj.owner_id
        _clear(db, owner)
        token, pid, vid = proj.share_token, proj.id, _variant(db, proj)
    assert client.post(f"/api/v1/client/{token}/comments", json={"name": "Анна", "body": "Нравится", "variant_id": vid}).status_code == 200
    assert client.post(f"/api/v1/client/{token}/decision", json={"name": "Анна", "variant_id": vid, "decision": "changes_requested"}).status_code == 200

    real = runner.HANDLERS.get("render")
    runner.HANDLERS["render"] = lambda ctx: {}
    try:
        with SessionLocal() as db:
            runner.enqueue(db, "render", project_id=pid, params={})
    finally:
        runner.HANDLERS["render"] = real

    r = client.get("/api/v1/notifications", headers=designer).json()
    kinds = [n["kind"] for n in r["items"]]
    assert {"client_comment", "client_changes", "job_done"} <= set(kinds) and r["unread"] >= 3
    assert all(n["link"].startswith(f"/app/p/{pid}") for n in r["items"])
    nid = r["items"][0]["id"]
    # another user cannot read or mark someone else's notification
    assert client.post(f"/api/v1/notifications/{nid}/read", headers=admin).status_code == 404
    assert client.post(f"/api/v1/notifications/{nid}/read", headers=designer).json()["read"] is True
    assert client.get("/api/v1/notifications?unread_only=true", headers=designer).json()["unread"] == r["unread"] - 1
    client.post("/api/v1/notifications/read-all", headers=designer)
    assert client.get("/api/v1/notifications", headers=designer).json()["unread"] == 0


def test_decision_without_generated_version_is_404(client):
    with SessionLocal() as db:
        proj = _project(db)
        v = m.DesignVariant(project_id=proj.id, key="empty", title="E", style="modern", tier="comfort")
        db.add(v)
        db.commit()
        token, vid = proj.share_token, v.id
    assert client.post(f"/api/v1/client/{token}/decision", json={"name": "A", "variant_id": vid, "decision": "approved"}).status_code == 404
    with SessionLocal() as db:
        db.delete(db.get(m.DesignVariant, vid))
        db.commit()


def test_prefs_switch_kinds_off(client, designer):
    p = client.get("/api/v1/auth/me/notification-prefs", headers=designer).json()
    assert p["kinds"]["client_comment"] is True and p["email_digest"] is True
    p = client.put("/api/v1/auth/me/notification-prefs", headers=designer, json={"kinds": {"client_comment": False, "bogus": True}}).json()
    assert p["kinds"]["client_comment"] is False and "bogus" not in p["kinds"]
    with SessionLocal() as db:
        proj = _project(db)
        _clear(db, proj.owner_id)
        token, vid = proj.share_token, _variant(db, proj)
    client.post(f"/api/v1/client/{token}/comments", json={"name": "Б", "body": "x", "variant_id": vid})
    assert not [n for n in client.get("/api/v1/notifications", headers=designer).json()["items"] if n["kind"] == "client_comment"]
    client.put("/api/v1/auth/me/notification-prefs", headers=designer, json={"kinds": {"client_comment": True}})


def test_daily_digest_once_per_day_localised(client):
    mail = Path(os.environ["MAIL_DIR"])
    with SessionLocal() as db:
        proj = _project(db)
        u = db.get(m.User, proj.owner_id)
        db.query(m.Notification).delete()
        db.commit()
        u.locale, u.notification_prefs = "hy", {}
        db.add(m.Notification(user_id=u.id, kind="rfq_reply", params={"supplier": "VLV", "project": proj.title}, link="/app"))
        db.commit()
        before = set(mail.glob("*")) if mail.exists() else set()
        now = datetime.now(timezone.utc)
        assert send_digests(db, now) == 1
        new = set(mail.glob("*")) - before
        assert len(new) == 1
        body = next(iter(new)).read_text(encoding="utf-8", errors="replace")
        assert "VLV" in body or "=?utf-8?" in body  # Armenian subject is MIME-encoded
        db.add(m.Notification(user_id=u.id, kind="job_done", params={"job": "album", "project": proj.title}))
        db.commit()
        assert send_digests(db, now + timedelta(hours=2)) == 0  # one e-mail a day
        assert send_digests(db, now + timedelta(hours=24)) == 1
        u.notification_prefs = {"email_digest": False}
        db.add(m.Notification(user_id=u.id, kind="job_done", params={"job": "album", "project": proj.title}))
        db.commit()
        assert send_digests(db, now + timedelta(hours=72)) == 0
        u.notification_prefs, u.locale = {}, "ru"
        _clear(db, u.id)
