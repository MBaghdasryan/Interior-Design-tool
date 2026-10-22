"""P1-1: Redis/RQ job queue (fakeredis, in-process SimpleWorker) — retries with
backoff, dead letter, recovery of orphaned jobs, idempotency, resumable SSE."""
from datetime import datetime, timedelta, timezone

import pytest
from fakeredis import FakeRedis
from rq import SimpleWorker
from rq.registry import FailedJobRegistry

from app import models as m
from app.db import SessionLocal
from app.jobs import runner

pytestmark = pytest.mark.usefixtures("client")
CALLS: dict[str, int] = {}


@runner.handler("test_flaky")
def _flaky(ctx):
    CALLS[ctx.job.id] = CALLS.get(ctx.job.id, 0) + 1
    if CALLS[ctx.job.id] < ctx.params.get("succeed_on", 2):
        raise RuntimeError("transient upstream error")
    return {"calls": CALLS[ctx.job.id]}


@pytest.fixture()
def queue(monkeypatch):
    monkeypatch.setattr(runner, "RETRY_INTERVALS_S", [0, 0])  # no waiting in tests (production: 15 s, 60 s)
    return runner.get_queue(connection=FakeRedis())


def _job(**params) -> str:
    with SessionLocal() as db:
        j = m.GenerationJob(kind="test_flaky", params=params)
        db.add(j)
        db.commit()
        return j.id


def _drain(q) -> None:
    SimpleWorker([q], connection=q.connection).work(burst=True, with_scheduler=False)


def _get(jid: str) -> m.GenerationJob:
    with SessionLocal() as db:
        return db.get(m.GenerationJob, jid)


def test_retry_after_transient_failure(queue):
    jid = _job(succeed_on=2)
    runner.submit(jid, queue=queue)
    _drain(queue)
    j = _get(jid)
    assert j.status == "succeeded" and j.attempts == 2 and j.result == {"calls": 2}


def test_dead_letter_after_max_attempts(queue):
    jid = _job(succeed_on=99)
    runner.submit(jid, queue=queue)
    _drain(queue)
    j = _get(jid)
    assert j.status == "failed" and j.attempts == runner.MAX_ATTEMPTS and j.counters.get("dead_letter") is True
    assert "transient upstream error" in j.error
    assert any(x.startswith(f"forma-{jid}") for x in FailedJobRegistry(queue=queue).get_job_ids())  # kept for inspection


def test_recover_orphans_after_worker_restart(queue):
    stale, fresh, lost = _job(succeed_on=1), _job(succeed_on=1), _job(succeed_on=1)
    with SessionLocal() as db:
        db.get(m.GenerationJob, stale).status = "running"  # worker died mid-run
        db.get(m.GenerationJob, stale).started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.get(m.GenerationJob, fresh).status = "running"  # just started elsewhere — leave it alone
        db.get(m.GenerationJob, fresh).started_at = datetime.now(timezone.utc)
        db.commit()  # `lost` stays queued but was never pushed to Redis (API crashed before submit)
        recovered = runner.recover_orphans(db, queue=queue)
    assert set(recovered) >= {stale, lost} and fresh not in recovered
    _drain(queue)
    assert _get(stale).status == "succeeded" and _get(lost).status == "succeeded" and _get(fresh).status == "running"


def test_enqueue_is_idempotent(queue, monkeypatch):
    monkeypatch.setattr(runner, "submit", lambda jid, queue=None, kind=None: None)
    with SessionLocal() as db:
        a = runner.enqueue(db, "test_flaky", project_id=None, params={}, idempotency_key="same-key")
        b = runner.enqueue(db, "test_flaky", project_id=None, params={}, idempotency_key="same-key")
        assert a.id == b.id


def test_sse_resumes_with_last_event_id(client, designer):
    pid = next(p for p in client.get("/api/v1/projects", headers=designer).json() if p["title"].startswith("Демо"))["id"]
    jobs = client.get(f"/api/v1/projects/{pid}/jobs", headers=designer).json()
    if not jobs:
        pytest.skip("no finished job in an isolated run")
    url = f"/api/v1/projects/{pid}/jobs/{jobs[0]['id']}/events"

    def read(headers):
        with client.stream("GET", url, headers=headers) as r:
            return "".join(r.iter_text())

    first = read(designer)
    assert "retry: 3000" in first and "event: progress" in first and "event: end" in first
    eid = next(line.split(":", 1)[1].strip() for line in first.splitlines() if line.startswith("id:"))
    resumed = read({**designer, "Last-Event-ID": eid})
    assert "event: progress" not in resumed and "event: end" in resumed  # unchanged state is not re-sent


def test_catalogue_jobs_use_their_own_queue(monkeypatch):
    """Long rate-limited crawls run on the catalogue worker and never queue behind / ahead of user jobs."""
    import fakeredis

    conn = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(runner, "get_queue", lambda connection=None, name=runner.QUEUE_NAME: __import__("rq").Queue(name, connection=conn))
    monkeypatch.setattr(runner, "_uses_rq", lambda q: True)
    monkeypatch.delenv("FORMA_JOBS_SYNC", raising=False)
    runner.submit("a" * 32, kind="source_index")
    runner.submit("b" * 32, kind="album")
    assert len(runner.get_queue(name=runner.CATALOG_QUEUE).get_job_ids()) == 1
    assert len(runner.get_queue(name=runner.QUEUE_NAME).get_job_ids()) == 1
