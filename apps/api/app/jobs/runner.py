"""Background job runner. Jobs and their steps are persisted, so progress survives
API restarts and is streamed to the UI over SSE. The in-process thread pool is the
MVP queue driver; the interface matches a Redis/BullMQ/Celery worker so it can be
swapped without touching job code (docs/ADR-004)."""
from __future__ import annotations

import logging
import os
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .. import models as m
from ..db import SessionLocal

log = logging.getLogger("forma.jobs")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="forma-job")
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


def submit(job_id: str) -> None:
    if os.environ.get("FORMA_JOBS_SYNC") == "1":  # tests / CLI: run inline, deterministically
        _run(job_id)
        return
    _pool.submit(_run, job_id)


def run_sync(job_id: str) -> None:
    """Used by tests to execute a job deterministically in the calling thread."""
    _run(job_id)


def _run(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(m.GenerationJob, job_id)
        if not job or job.status in ("succeeded", "running"):
            return
        fn = HANDLERS.get(job.kind)
        if not fn:
            job.status, job.error = "failed", f"no handler for {job.kind}"
            db.commit()
            return
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
            log.error("job %s failed: %s", job_id, traceback.format_exc())
            job.status, job.error = "failed", f"{type(e).__name__}: {e}"
            for s in job.steps:
                if s.status == "running":
                    s.status, s.detail = "failed", str(e)[:400]
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def job_dict(job: m.GenerationJob) -> dict:
    return {
        "id": job.id, "kind": job.kind, "status": job.status, "progress": job.progress, "error": job.error, "counters": job.counters,
        "result": job.result, "project_id": job.project_id, "created_at": job.created_at.isoformat() if job.created_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None, "attempts": job.attempts,
        "steps": [{"key": s.key, "title": s.title, "phase": s.phase, "status": s.status, "detail": s.detail, "params": s.params or {},
                   "started_at": s.started_at.isoformat() if s.started_at else None, "finished_at": s.finished_at.isoformat() if s.finished_at else None}
                  for s in sorted(job.steps, key=lambda s: s.order)],
    }
