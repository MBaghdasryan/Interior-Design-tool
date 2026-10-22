"""P1-2: S3/MinIO storage (moto), presigned upload with quarantine, download redirect,
readiness probes, request ids, JSON logs, OpenTelemetry spans and file retention."""
import json
import logging
import os
import time

import pytest
from moto import mock_aws

from app import models as m
from app import storage as storage_mod
from app.db import SessionLocal
from app.storage import LocalStorage, S3Storage

pytestmark = pytest.mark.usefixtures("client")
PNG = b"\x89PNG\r\n\x1a\n" + b"1" * 3000


@pytest.fixture()
def s3(monkeypatch):
    with mock_aws():
        st = S3Storage("renovara-test", None, None, "us-east-1", "x", "y", sse="AES256")  # the driver's own SigV4 clients
        st.s3.create_bucket(Bucket="renovara-test")
        monkeypatch.setattr(storage_mod, "_storage", st)
        yield st


def test_s3_storage_contract(s3):
    s3.put("projects/p/a.pdf", b"%PDF-1.7 x", "application/pdf")
    head = s3.s3.head_object(Bucket="renovara-test", Key="projects/p/a.pdf")
    assert head["ServerSideEncryption"] == "AES256" and head["ContentType"] == "application/pdf"  # encrypted at rest
    assert s3.get("projects/p/a.pdf") == b"%PDF-1.7 x" and s3.exists("projects/p/a.pdf")
    s3.move("projects/p/a.pdf", "projects/p/b.pdf")
    assert not s3.exists("projects/p/a.pdf") and [k for k, _ in s3.list("projects/")] == ["projects/p/b.pdf"]
    url = s3.presigned_get("projects/p/b.pdf", "b.pdf", inline=True)
    assert "X-Amz-Signature" in url and "response-content-disposition=inline" in url and "X-Amz-Expires=300" in url
    for bad in ("../etc/passwd", "/abs", "a/../../b"):
        with pytest.raises(ValueError):
            s3.put(bad, b"x")


def test_presigned_upload_quarantine_and_download_redirect(client, designer, s3):
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "S3 upload"}).json()["id"]
    r = client.post(f"/api/v1/projects/{pid}/assets/presign", headers=designer, json={"filename": "room.png", "size": len(PNG), "content_type": "image/png"}).json()
    assert r["mode"] == "presigned" and r["key"].startswith(f"incoming/{pid}/") and r["headers"]["x-amz-server-side-encryption"] == "AES256"
    s3.s3.put_object(Bucket="renovara-test", Key=r["key"], Body=PNG, ContentType="image/png")  # what the browser PUT does
    a = client.post(f"/api/v1/projects/{pid}/assets/complete", headers=designer, json={"key": r["key"], "filename": "room.png", "content_type": "image/png"})
    assert a.status_code == 200, a.text
    assert a.json()["kind"] == "photo" and not s3.exists(r["key"])  # moved out of quarantine
    # a disguised file is rejected and removed from quarantine
    r2 = client.post(f"/api/v1/projects/{pid}/assets/presign", headers=designer, json={"filename": "plan.pdf", "size": 10, "content_type": "application/pdf"}).json()
    s3.s3.put_object(Bucket="renovara-test", Key=r2["key"], Body=PNG)
    bad = client.post(f"/api/v1/projects/{pid}/assets/complete", headers=designer, json={"key": r2["key"], "filename": "plan.pdf"})
    assert bad.status_code == 415 and not s3.exists(r2["key"])
    # another project's quarantine cannot be claimed
    assert client.post(f"/api/v1/projects/{pid}/assets/complete", headers=designer, json={"key": "incoming/other/x.png", "filename": "x.png"}).status_code == 422
    assert client.post(f"/api/v1/projects/{pid}/assets/presign", headers=designer, json={"filename": "x.exe", "size": 10}).status_code == 415
    # download: our HMAC link → 302 to a short-lived presigned S3 URL
    url = a.json()["url"]
    d = client.get(url[url.index("/api/v1/files/"):], follow_redirects=False)
    assert d.status_code == 302 and "X-Amz-Signature" in d.headers["location"]


def test_local_storage_falls_back_to_multipart(client, designer):
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "Local upload"}).json()["id"]
    assert client.post(f"/api/v1/projects/{pid}/assets/presign", headers=designer, json={"filename": "a.png", "size": 10}).json() == {"mode": "multipart"}


def test_probes_and_request_id(client):
    assert client.get("/api/live").json() == {"status": "alive"}
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.json()["checks"]["db"] == "ok" and r.json()["checks"]["storage"] == "ok"
    assert len(r.headers["x-request-id"]) == 16
    assert client.get("/api/health", headers={"X-Request-ID": "trace-abc-123"}).headers["x-request-id"] == "trace-abc-123"
    assert client.get("/api/health", headers={"X-Request-ID": "bad id\nwith newline"}).headers["x-request-id"] != "bad id\nwith newline"


def test_json_log_format_carries_request_id():
    from app.observability import JsonFormatter, request_id

    tok = request_id.set("req-42")
    try:
        rec = logging.LogRecord("forma.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
        out = json.loads(JsonFormatter().format(rec))
    finally:
        request_id.reset(tok)
    assert out["msg"] == "hello world" and out["request_id"] == "req-42" and out["level"] == "INFO"


def test_tracing_records_http_and_sql_spans():
    from fastapi import FastAPI
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from sqlalchemy import create_engine, text
    from starlette.testclient import TestClient

    from app.observability import setup_tracing

    probe = FastAPI()
    engine = create_engine("sqlite://")

    @probe.get("/ping")
    def ping():
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return {"ok": True}

    exporter = InMemorySpanExporter()
    assert setup_tracing(probe, engine, endpoint=None, service_name="test", exporter=exporter)
    TestClient(probe).get("/ping")
    names = [s.name for s in exporter.get_finished_spans()]
    assert any("GET /ping" in n for n in names) and any("SELECT" in n for n in names)


def test_retention_policy(tmp_path, monkeypatch):
    from app.config import get_settings
    from app.retention import apply_retention

    st = LocalStorage(tmp_path)
    monkeypatch.setattr(storage_mod, "_storage", st)
    old = time.time() - 40 * 86400
    st.put("incoming/p/stale.png", b"x")
    st.put("projects/p/assets/orphan.png", b"x")
    st.put("projects/p/assets/kept.png", b"x")
    for k in ("incoming/p/stale.png", "projects/p/assets/orphan.png", "projects/p/assets/kept.png"):
        os.utime(st.path(k), (old, old))
    st.put("incoming/p/fresh.png", b"x")
    with SessionLocal() as db:
        proj = db.query(m.Project).first()
        db.add(m.SourceAsset(project_id=proj.id, kind="photo", filename="kept.png", mime="image/png", size=1, sha256="k" * 64, storage_key="projects/p/assets/kept.png"))
        db.commit()
        mail = get_settings().mail_dir
        mail.mkdir(parents=True, exist_ok=True)
        (mail / "0_old.eml").write_text("x")
        os.utime(mail / "0_old.eml", (old, old))
        out = apply_retention(db)
    assert out["incoming"] == 1 and out["orphans"] == 1 and out["mail"] >= 1
    assert st.exists("projects/p/assets/kept.png") and st.exists("incoming/p/fresh.png") and not st.exists("projects/p/assets/orphan.png")


def test_empty_env_values_fall_back_to_defaults(monkeypatch):
    """`.env.example` leaves optional values empty; the API must still start (regression found by CI)."""
    from app.config import Settings

    for k in ("MFA_ENFORCE", "CLAMAV_REQUIRED", "CLAMAV_HOST", "REDIS_URL", "S3_ENDPOINT", "OTEL_EXPORTER_OTLP_ENDPOINT"):
        monkeypatch.setenv(k, "")
    s = Settings()
    assert s.mfa_enforce is None and s.clamav_required is None and s.clamav_host is None and s.redis_url is None
