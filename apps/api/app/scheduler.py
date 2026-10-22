"""Periodic tasks run by the worker's maintenance loop (no extra cron container).
Each task records its last run in `ExternalSource.stats` / settings so restarts do
not cause bursts. Tasks only enqueue jobs — the work itself runs in the queue."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

log = logging.getLogger("forma.scheduler")

# registry filled by modules that own periodic work: name -> callable(db) -> None
TASKS: dict[str, object] = {}


def periodic(name: str):
    def deco(fn):
        TASKS[name] = fn
        return fn

    return deco


def run_due(db: Session) -> list[str]:
    ran = []
    for name, fn in TASKS.items():
        try:
            if fn(db):  # each task decides whether it is due and returns True when it enqueued work
                ran.append(name)
        except Exception:  # noqa: BLE001
            log.exception("periodic task %s failed", name)
            db.rollback()
    if ran:
        log.info("periodic tasks run at %s: %s", datetime.now(timezone.utc).isoformat(timespec="seconds"), ", ".join(ran))
    return ran
