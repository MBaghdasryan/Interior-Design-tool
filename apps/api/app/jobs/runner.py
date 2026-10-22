"""Background job runner. Jobs and their steps are persisted, so progress survives
restarts and is streamed to the UI over SSE.

Queue drivers (same job code, docs/ADR-004):
* `REDIS_URL` set → Redis + RQ: jobs run in the separate `worker` service
  (`python -m app.worker`) with retries and backoff; jobs that exhaust their
  retries stay in RQ's FailedJobRegistry (dead letter) and are flagged in the DB.
* no Redis (local dev) → in-process thread pool.
* `FORMA_JOBS_SYNC=1` (tests, CLI) → inline.
`recover_orphans()` re-submits jobs left queued/running by a crashed process."""
from __future__ import annotations

import logging
import os
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..db import SessionLocal

log = logging.getLogger("forma.jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="forma-job")
QUEUE_NAME = "forma"
MAX_ATTEMPTS = 3  # first run + 2 retries
RETRY_INTERVALS_S = [15, 60]
HANDLERS: dict[str, Callable[["JobContext"], dict]] = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn

    return deco


class JobContext:
    def __init__(self, db: Session, job: m.GenerationJob):
        self.db = db
        self.job = job
        self._steps = {s.key: s for s in job.steps}

    @property
    def params(self) -> dict:
        return self.job.params or {}

    def define_steps(self, steps: list[tuple[str, str, str]]) -> None:
        if self.job.steps:
            return
        for i, (key, title, phase) in enumerate(steps):
            s = m.GenerationStep(job_id=self.job.id, order=i, key=key, title=title, phase=phase)
            self.db.add(s)
            self._steps[key] = s
        self.db.commit()

    def start(self, key: str, detail: str = "") -> None:
        s = self._steps[key]
        s.status, s.detail, s.started_at = "running", detail, datetime.now(timezone.utc)
        self._progress()
        self.db.commit()

    def done(self, key: str, detail: str = "", status: str = "done", **params) -> None:
        s = self._steps[key]
        s.status, s.detail, s.finished_at = status, detail, datetime.now(timezone.utc)
        s.params = params
        if not s.started_at:
            s.started_at = s.finished_at
        self._progress()
        self.db.commit()

    def counters(self, **kw) -> None:
        self.job.counters = {**(self.job.counters or {}), **kw}
        self.db.commit()

    def _progress(self) -> None:
        steps = list(self._steps.values())
        if steps:
            finished = sum(1 for s in steps if s.status in ("done", "warning", "skipped", "failed"))
            self.job.progress = round(finished / len(steps), 3)


def enqueue(db: Session, kind: str, *, project_id: str | None, params: dict, idempotency_key: str | None = None) -> m.GenerationJob:
    if idempotency_key:
        existing = db.query(m.GenerationJob).filter(m.GenerationJob.idempotency_key == idempotency_key).first()
        if existing:
            return existing
    job = m.GenerationJob(project_id=project_id, kind=kind, params=params, idempotency_key=idempotency_key)
    db.add(job)
    db.commit()
    submit(job.id)
    db.refresh(job)  # inline (sync) runs update the row from another session
    return job


def get_queue(connection=None):
    from redis import Redis
    from rq import Queue

    conn = connection or Redis.from_url(get_settings().redis_url)
    return Queue(QUEUE_NAME, connection=conn, default_timeout=3600)


def _uses_rq(queue) -> bool:
    return queue is not None or bool(get_settings().redis_url)


def submit(job_id: str, queue=None) -> None:
    if os.environ.get("FORMA_JOBS_SYNC") == "1" and queue is None:  # tests / CLI: run inline, deterministically
        _run(job_id)
        return
    if _uses_rq(queue):
        from rq import Retry

        (queue or get_queue()).enqueue("app.jobs.runner.run_job", job_id, job_id=f"forma-{job_id}-{os.urandom(3).hex()}",
                                       retry=Retry(max=MAX_ATTEMPTS - 1, interval=RETRY_INTERVALS_S), failure_ttl=7 * 24 * 3600)
        return
    _pool.submit(_run, job_id)


def run_sync(job_id: str) -> None:
    """Used by tests to execute a job deterministically in the calling thread."""
    _run(job_id)


def run_job(job_id: str) -> None:
    """RQ entrypoint: a failed run raises so RQ applies the retry policy; the DB keeps the error."""
    if _run(job_id) == "failed":
        raise RuntimeError(f"job {job_id} failed")


def _active_rq_job_ids(queue) -> set[str]:
    """Jobs RQ is still responsible for: waiting, waiting for a retry, or being run by a
    worker whose heartbeat is fresh (a killed worker stops beating)."""
    from rq import Worker
    from rq.registry import ScheduledJobRegistry

    ids = list(queue.get_job_ids()) + list(ScheduledJobRegistry(queue=queue).get_job_ids())
    alive_after = datetime.now(timezone.utc) - timedelta(seconds=90)
    for w in Worker.all(queue=queue):
        hb = w.last_heartbeat
        if hb and (hb if hb.tzinfo else hb.replace(tzinfo=timezone.utc)) > alive_after and w.get_current_job_id():
            ids.append(w.get_current_job_id())
    return {jid.split("-")[1] for jid in ids if jid and jid.startswith("forma-")}


def recover_orphans(db: Session, *, running_older_than_s: int = 120, queue=None) -> list[str]:
    """Re-submit jobs a dead process left behind: `queued` jobs nobody holds and `running`
    jobs without a live worker. A just-started job (< running_older_than_s) gets time to
    appear in a worker heartbeat before it is judged."""
    rq = _uses_rq(queue)
    q = (queue or get_queue()) if rq else None
    active = _active_rq_job_ids(q) if rq else set()
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=running_older_than_s)
    out = []
    for job in db.query(m.GenerationJob).filter(m.GenerationJob.status.in_(("queued", "running"))):
        if job.id in active:
            continue
        started = job.started_at if (job.started_at is None or job.started_at.tzinfo) else job.started_at.replace(tzinfo=timezone.utc)
        if job.status == "running" and started and started > cutoff:
            continue
        job.status = "queued"
        out.append(job.id)
    db.commit()
    for jid in out:
        log.warning("recovering orphaned job %s", jid)
        submit(jid, queue=q)
    return out


def _run(job_id: str) -> str | None:
    db = SessionLocal()
    try:
        job = db.get(m.GenerationJob, job_id)
        if not job or job.status in ("succeeded", "running"):
            return None
        fn = HANDLERS.get(job.kind)
        if not fn:
            job.status, job.error = "failed", f"no handler for {job.kind}"
            db.commit()
            return None  # nothing to retry
        job.status, job.started_at, job.attempts = "running", datetime.now(timezone.utc), job.attempts + 1
        db.commit()
        ctx = JobContext(db, job)
        try:
            result = fn(ctx) or {}
            job.result = result
            job.status = "succeeded"
            job.progress = 1.0
        except Exception as e:  # noqa: BLE001 - job failures are recorded, never raised into the pool
            db.rollback()
            job = db.get(m.GenerationJob, job_id)
            log.error("job %s failed (attempt %s): %s", job_id, job.attempts, traceback.format_exc())
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            if job.attempts >= MAX_ATTEMPTS:
                job.counters = {**(job.counters or {}), "dead_letter": True}
            for s in job.steps:
                if s.status == "running":
                    s.status, s.detail = "failed", str(e)[:400]
        job.finished_at = datetime.now(timezone.utc)
        _notify_job(db, job)
        db.commit()
        return job.status
    finally:
        db.close()


NOTIFY_KINDS = {"pipeline", "album", "render", "render_edit", "recognize", "aps_dwg"}


def _notify_job(db: Session, job: m.GenerationJob) -> None:
    if job.kind not in NOTIFY_KINDS or not job.project_id or job.status not in ("succeeded", "failed"):
        return
    if job.status == "failed" and job.attempts < MAX_ATTEMPTS and _uses_rq(None):
        return  # a retry is scheduled — notify only on the final outcome
    try:
        from ..notify import notify, project_people

        project = db.get(m.Project, job.project_id)
        if project:
            notify(db, project_people(db, project), "job_done" if job.status == "succeeded" else "job_failed",
                   params={"job": job.kind, "project": project.title}, link=f"/app/p/{project.id}", project_id=project.id)
    except Exception:  # noqa: BLE001 - notifications never break a job
        log.exception("job notification failed")


def job_dict(job: m.GenerationJob) -> dict:
    return {
        "id": job.id, "kind": job.kind, "status": job.status, "progress": job.progress, "error": job.error, "counters": job.counters,
        "result": job.result, "project_id": job.project_id, "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None, "attempts": job.attempts,
        "steps": [{"key": s.key, "title": s.title, "phase": s.phase, "status": s.status, "detail": s.detail, "params": s.params or {},
                   "started_at": s.started_at.isoformat() if s.started_at else None, "finished_at": s.finished_at.isoformat() if s.finished_at else None}
                  for s in sorted(job.steps, key=lambda s: s.order)],
    }
