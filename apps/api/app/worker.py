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
from .jobs import catalog, documents, pipeline, recognize  # noqa: F401  (register job handlers)
from .jobs.runner import get_queue, recover_orphans

log = logging.getLogger("forma.worker")


def maintenance_loop(q, interval_s: int = 60) -> None:
    """Every minute: re-submit orphaned jobs (a killed worker), then run due periodic tasks."""
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

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if not get_settings().redis_url:
        raise SystemExit("REDIS_URL is not set — the API runs jobs in-process; no worker needed")
    q = get_queue()
    with SessionLocal() as db:
        n = recover_orphans(db, queue=q, running_older_than_s=30)
    log.info("worker starting on queue %s (recovered %d orphaned jobs)", q.name, len(n))
    threading.Thread(target=maintenance_loop, args=(q,), daemon=True, name="forma-maintenance").start()
    Worker([q], connection=q.connection).work(with_scheduler=True)


if __name__ == "__main__":
    main()
