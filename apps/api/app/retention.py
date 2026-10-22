"""File retention policy (docs/RUNBOOK.md §Retention), run daily by the worker:
* `incoming/` — presigned uploads never completed: deleted after RETENTION_INCOMING_DAYS;
* outgoing mail copies (console backend): deleted after RETENTION_MAIL_DAYS;
* objects under `projects/` referenced by no asset/document (deleted projects,
  superseded temp files): deleted after RETENTION_ORPHAN_DAYS.
Project assets, generated documents and approved snapshots are never purged here —
deleting a project's data is an explicit, audited user action (privacy export/delete)."""
from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .config import get_settings
from .scheduler import periodic
from .storage import get_storage

log = logging.getLogger("forma.retention")
_last_run = 0.0


def apply_retention(db: Session, now: float | None = None) -> dict:
    s = get_settings()
    now = now or time.time()
    st = get_storage()
    out = {"incoming": 0, "mail": 0, "orphans": 0}
    for key, mtime in st.list("incoming/"):
        if now - mtime > s.retention_incoming_days * 86400:
            st.delete(key)
            out["incoming"] += 1
    if s.mail_dir.exists():
        for f in s.mail_dir.glob("*.eml"):
            if now - f.stat().st_mtime > s.retention_mail_days * 86400:
                f.unlink(missing_ok=True)
                out["mail"] += 1
    referenced = set(db.scalars(select(m.SourceAsset.storage_key))) | set(db.scalars(select(m.Document.storage_key)))
    for key, mtime in st.list("projects/"):
        if key not in referenced and now - mtime > s.retention_orphan_days * 86400:
            st.delete(key)
            out["orphans"] += 1
    db.add(m.AuditEvent(action="retention.run", entity="storage", data=out))
    db.commit()
    log.info("retention: %s", out)
    return out


@periodic("retention")
def daily_retention(db: Session) -> bool:
    global _last_run
    if time.time() - _last_run < 24 * 3600:
        return False
    _last_run = time.time()
    apply_retention(db)
    return True
