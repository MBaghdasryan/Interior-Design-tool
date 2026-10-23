"""Grant a platform role to an existing account (after the person registered).

    docker compose exec api python -m app.grant_role someone@example.com linguist
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from . import models as m
from .db import SessionLocal


def main() -> None:
    email, role = sys.argv[1].strip().lower(), sys.argv[2]
    if role not in ("linguist", "platform_ops"):
        raise SystemExit("role must be linguist | platform_ops")
    with SessionLocal() as db:
        u = db.scalar(select(m.User).where(m.User.email == email))
        if not u:
            raise SystemExit("no such account — register first")
        org = db.scalar(select(m.Organization).where(m.Organization.kind == "platform").limit(1))
        if not db.scalar(select(m.Membership).where(m.Membership.user_id == u.id, m.Membership.org_id == org.id, m.Membership.role == role)):
            db.add(m.Membership(user_id=u.id, org_id=org.id, role=role))
        db.add(m.AuditEvent(action="role.grant", entity="user", entity_id=u.id, data={"role": role, "via": "cli"}))
        db.commit()
    print(f"granted {role}")


if __name__ == "__main__":
    main()
