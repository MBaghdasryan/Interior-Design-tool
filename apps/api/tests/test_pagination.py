"""P1-9: keyset (cursor) pagination — stable across inserts, no duplicates or gaps, opaque cursor."""
from datetime import datetime, timedelta, timezone

import pytest

from app import models as m
from app.db import SessionLocal

pytestmark = pytest.mark.usefixtures("client")


def test_notifications_cursor_pages_are_complete_and_stable(client, designer):
    with SessionLocal() as db:
        u = db.query(m.User).filter_by(email="designer@forma.local").first()
        db.query(m.Notification).filter_by(user_id=u.id).delete()
        base = datetime.now(timezone.utc) - timedelta(hours=1)
        for i in range(7):  # two share a timestamp: the id breaks the tie
            db.add(m.Notification(user_id=u.id, kind="job_done", params={"i": i}, created_at=base + timedelta(minutes=min(i, 5))))
        db.commit()
    seen, cursor, pages = [], None, 0
    while True:
        r = client.get("/api/v1/notifications", headers=designer, params={"limit": 3, **({"cursor": cursor} if cursor else {})}).json()
        seen += [n["params"]["i"] for n in r["items"]]
        pages += 1
        if pages == 1:  # a row inserted after the first page must not shift later pages
            with SessionLocal() as db:
                db.add(m.Notification(user_id=u.id, kind="job_done", params={"i": 99}))
                db.commit()
        cursor = r["next_cursor"]
        if not cursor:
            break
    assert pages == 3 and sorted(seen) == list(range(7)) and len(seen) == len(set(seen))
    assert client.get("/api/v1/notifications", headers=designer, params={"cursor": "%%%"}).status_code == 422


def test_list_endpoints_use_next_cursor_header(client, designer, admin):
    with SessionLocal() as db:
        for i in range(3):
            db.add(m.AuditEvent(action="test.page", entity="t", data={"i": i}))
        db.commit()
    r = client.get("/api/v1/admin/audit", headers=admin, params={"limit": 2})
    assert len(r.json()) == 2 and r.headers.get("x-next-cursor")
    r2 = client.get("/api/v1/admin/audit", headers=admin, params={"limit": 2, "cursor": r.headers["x-next-cursor"]})
    assert r2.status_code == 200 and r2.json()
    assert not {a["data"].get("i") for a in r2.json() if a["action"] == "test.page"} & {a["data"].get("i") for a in r.json() if a["action"] == "test.page"}
    first = client.get("/api/v1/projects", headers=designer, params={"limit": 1})
    assert len(first.json()) == 1
    if first.headers.get("x-next-cursor"):
        nxt = client.get("/api/v1/projects", headers=designer, params={"limit": 1, "cursor": first.headers["x-next-cursor"]}).json()
        assert nxt and nxt[0]["id"] != first.json()[0]["id"]
    assert client.get("/api/v1/projects", headers=designer).headers.get("x-next-cursor") is None  # default page holds everything
