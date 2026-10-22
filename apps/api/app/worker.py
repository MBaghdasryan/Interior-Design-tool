"""Job worker (separate compose service): `python -m app.worker`.
Recovers orphaned jobs, then processes the RQ queue with the scheduler enabled
(retry backoff). A maintenance thread re-checks for orphaned jobs every minute
and runs due periodic tasks (`app.scheduler`). SIGTERM → warm shutdown: the
current job finishes first."""
from __future__ import annotations

import logging
import threading
import time

from .config import get_settings
from .db import SessionLocal
from .jobs import catalog, documents, pipeline, recognize, render  # noqa: F401  (register job handlers)
from .jobs.runner import QUEUE_NAME, get_queue, recover_orphans
from .observability import setup_logging, setup_sentry

log = logging.getLogger("forma.worker")


def maintenance_loop(q, interval_s: int = 60) -> None:
    """Every minute: re-submit orphaned jobs (a killed worker), then run due periodic tasks."""
    from . import notify, retention  # noqa: F401  (register the digest and daily retention tasks)
    from .catalog import maintenance  # noqa: F401  (catalogue index / TTL / feed schedules)
    from .scheduler import run_due

    while True:
        time.sleep(interval_s)
        try:
            with SessionLocal() as db:
                recover_orphans(db, queue=q)
                run_due(db)
        except Exception:  # noqa: BLE001 - maintenance must never kill the worker
            log.exception("maintenance tick failed")


def main() -> None:
    from rq import Worker

    s = get_settings()
    setup_logging(s.log_format)
    setup_sentry(s.sentry_dsn, s.env)
    if not s.redis_url:
        raise SystemExit("REDIS_URL is not set — the API runs jobs in-process; no worker needed")
    import os

    names = [n.strip() for n in os.environ.get("WORKER_QUEUES", QUEUE_NAME).split(",") if n.strip()]
    queues = [get_queue(name=n) for n in names]
    # only the main worker recovers orphans and runs periodic tasks (one scheduler for the whole system)
    if QUEUE_NAME in names:
        with SessionLocal() as db:
            n = recover_orphans(db, running_older_than_s=30)
        log.info("worker starting on queues %s (recovered %d orphaned jobs)", names, len(n))
        threading.Thread(target=maintenance_loop, args=(None,), daemon=True, name="forma-maintenance").start()
    else:
        log.info("worker starting on queues %s", names)
    Worker(queues, connection=queues[0].connection).work(with_scheduler=True)


if __name__ == "__main__":
    main()
