"""P1-4: MFA (TOTP + backup codes, enforcement), ClamAV INSTREAM scanning with
quarantine, personal-data export / deletion / consents, photo & audit retention."""
import io
import json
import socket
import socketserver
import struct
import threading
import zipfile
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient

from app import models as m
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.ratelimit import backend

pytestmark = pytest.mark.usefixtures("client")
PW = "Correct-Horse-42"
PNG = b"\x89PNG\r\n\x1a\n" + b"7" * 3000


@pytest.fixture(autouse=True)
def _limits():
    backend().reset()
    yield


def new_user(email: str, kind: str = "bureau") -> tuple[TestClient, dict]:
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": email, "password": PW, "name": "Privacy User", "org_name": f"Org {email}",
                                              "org_kind": kind, "locale": "en", "accept_terms": True})
    assert r.status_code == 200, r.text
    return c, {"X-CSRF-Token": c.cookies.get("forma_csrf")}


# ------------------------------------------------------------------ MFA
def test_mfa_enrol_login_backup_codes_disable():
    c, h = new_user("mfa.user@example.com")
    setup = c.post("/api/v1/auth/mfa/setup", headers=h).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/") and "<svg" in setup["qr_svg"]
    assert c.post("/api/v1/auth/mfa/enable", headers=h, json={"code": "000000"}).json()["code"] == "auth.mfa_invalid"
    totp = pyotp.TOTP(setup["secret"])
    codes = c.post("/api/v1/auth/mfa/enable", headers=h, json={"code": totp.now()}).json()["backup_codes"]
    assert len(codes) == 10
    with SessionLocal() as db:
        u = db.query(m.User).filter_by(email="mfa.user@example.com").one()
        assert u.mfa_secret_enc and setup["secret"] not in u.mfa_secret_enc  # encrypted at rest
        assert codes[0] not in json.dumps(u.mfa_backup_codes)  # only hashes stored
    # password alone no longer opens a session
    anon = TestClient(app)
    step1 = anon.post("/api/v1/auth/login", json={"email": "mfa.user@example.com", "password": PW}).json()
    assert step1["mfa_required"] and "token" not in step1 and not anon.cookies.get("forma_session")
    assert anon.post("/api/v1/auth/mfa/verify", json={"mfa_token": step1["mfa_token"], "code": "123456"}).json()["code"] == "auth.mfa_invalid"
    ok = anon.post("/api/v1/auth/mfa/verify", json={"mfa_token": step1["mfa_token"], "code": totp.now()})
    assert ok.status_code == 200 and anon.cookies.get("forma_session")
    # a backup code works exactly once
    b = TestClient(app)
    t2 = b.post("/api/v1/auth/login", json={"email": "mfa.user@example.com", "password": PW}).json()["mfa_token"]
    assert b.post("/api/v1/auth/mfa/verify", json={"mfa_token": t2, "backup_code": codes[0]}).status_code == 200
    t3 = TestClient(app).post("/api/v1/auth/login", json={"email": "mfa.user@example.com", "password": PW}).json()["mfa_token"]
    assert TestClient(app).post("/api/v1/auth/mfa/verify", json={"mfa_token": t3, "backup_code": codes[0]}).status_code == 401
    assert TestClient(app).post("/api/v1/auth/mfa/verify", json={"mfa_token": "forged.token", "code": totp.now()}).status_code == 401
    # disabling needs a second factor
    assert c.post("/api/v1/auth/mfa/disable", headers=h, json={"code": "111111"}).status_code == 422
    assert c.post("/api/v1/auth/mfa/disable", headers=h, json={"backup_code": codes[1]}).json()["mfa_enabled"] is False


def test_mfa_enforced_for_admin_roles(monkeypatch, client):
    monkeypatch.setattr(get_settings(), "mfa_enforce", True)
    bureau = TestClient(app)
    bureau.post("/api/v1/auth/login", json={"email": "bureau@forma.local", "password": "demo1234"})
    me = bureau.get("/api/v1/auth/me").json()
    assert me["mfa_required"] and me["mfa_enrollment_required"]
    r = bureau.get("/api/v1/projects")
    assert r.status_code == 403 and r.json()["code"] == "auth.mfa_enrollment_required"
    assert bureau.post("/api/v1/auth/mfa/setup", headers={"X-CSRF-Token": bureau.cookies.get("forma_csrf")}).status_code == 200  # enrolment allowed
    designer = TestClient(app)
    designer.post("/api/v1/auth/login", json={"email": "designer@forma.local", "password": "demo1234"})
    assert designer.get("/api/v1/projects").status_code == 200  # role without the requirement


# ------------------------------------------------------------------ ClamAV
class _FakeClamd(socketserver.BaseRequestHandler):
    def handle(self):
        assert self.request.recv(10) == b"zINSTREAM\0"
        data = b""
        while True:
            size = struct.unpack("!I", self.request.recv(4, socket.MSG_WAITALL))[0]
            if not size:
                break
            data += self.request.recv(size, socket.MSG_WAITALL)
        self.request.sendall(b"stream: Win.Test.FAKE FOUND\0" if b"VIRUS" in data else b"stream: OK\0")


@pytest.fixture()
def clamd(monkeypatch):
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _FakeClamd)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    s = get_settings()
    monkeypatch.setattr(s, "clamav_host", "127.0.0.1")
    monkeypatch.setattr(s, "clamav_port", srv.server_address[1])
    yield srv
    srv.shutdown()
    srv.server_close()


def test_clamav_scan_quarantine_and_fail_closed(client, designer, clamd, monkeypatch):
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "AV check"}).json()["id"]
    ok = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("room.png", io.BytesIO(PNG), "image/png")})
    assert ok.status_code == 200 and ok.json()["scan_status"] == "clean"
    bad = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("bad.png", io.BytesIO(PNG + b"VIRUS"), "image/png")})
    assert bad.status_code == 422 and bad.json()["code"] == "file.malware" and bad.json()["params"]["signature"] == "Win.Test.FAKE"
    from app.storage import get_storage

    assert any(k.startswith(f"quarantine/{pid}/") for k, _ in get_storage().list("quarantine/"))
    with SessionLocal() as db:
        ev = db.query(m.AuditEvent).filter_by(action="asset.quarantined", project_id=pid).one()
        assert ev.data["signature"] == "Win.Test.FAKE" and len(ev.data["sha256"]) == 64
    assert all(a["filename"] != "bad.png" for a in client.get(f"/api/v1/projects/{pid}", headers=designer).json()["assets"])
    # clamd down: refused when required (production default), accepted as not_scanned otherwise
    monkeypatch.setattr(get_settings(), "clamav_port", 1)
    monkeypatch.setattr(get_settings(), "clamav_required", True)
    down = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("r2.png", io.BytesIO(PNG + b"2"), "image/png")})
    assert down.status_code == 503 and down.json()["code"] == "file.scan_unavailable"
    monkeypatch.setattr(get_settings(), "clamav_required", False)
    soft = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("r3.png", io.BytesIO(PNG + b"3"), "image/png")})
    assert soft.status_code == 200 and soft.json()["scan_status"] == "not_scanned"


# ------------------------------------------------------------------ personal data
def test_export_contains_personal_and_project_data():
    c, h = new_user("export.me@example.com")
    pid = c.post("/api/v1/projects", headers=h, json={"title": "My flat"}).json()["id"]
    c.post(f"/api/v1/projects/{pid}/assets", headers=h, files={"file": ("living.png", io.BytesIO(PNG + b"e"), "image/png")})
    r = c.get("/api/v1/auth/me/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = z.namelist()
    assert {"profile.json", "sessions.json", "activity.json", "README.txt"} <= set(names)
    assert f"projects/{pid}/files/living.png" in names and f"projects/{pid}/project.json" in names
    profile = json.loads(z.read("profile.json"))
    assert profile["email"] == "export.me@example.com" and profile["consents"]["terms"]["version"]
    assert "password_hash" not in json.dumps(profile) and "mfa_secret" not in json.dumps(profile)


def test_consents_history():
    c, h = new_user("consent.me@example.com")
    c.put("/api/v1/auth/me/consents", headers=h, json={"marketing_emails": True})
    out = c.put("/api/v1/auth/me/consents", headers=h, json={"marketing_emails": False, "product_analytics": True}).json()
    assert out["marketing_emails"]["granted"] is False and out["product_analytics"]["granted"] is True
    assert [x["key"] for x in out["history"]] == ["marketing_emails", "marketing_emails", "product_analytics"]


def test_deletion_grace_cancel_and_purge():
    c, h = new_user("delete.me@example.com")
    other = TestClient(app)
    other.post("/api/v1/auth/login", json={"email": "delete.me@example.com", "password": PW})
    pid = c.post("/api/v1/projects", headers=h, json={"title": "To be erased"}).json()["id"]
    c.post(f"/api/v1/projects/{pid}/assets", headers=h, files={"file": ("p.png", io.BytesIO(PNG + b"d"), "image/png")})
    assert c.post("/api/v1/auth/me/delete", headers=h, json={"password": "wrong"}).status_code == 401
    me = c.post("/api/v1/auth/me/delete", headers=h, json={"password": PW}).json()
    assert me["deletion_due_at"] and other.get("/api/v1/auth/me").status_code == 401  # other sessions revoked
    assert c.post("/api/v1/auth/me/delete/cancel", headers=h).json()["deletion_due_at"] is None
    c.post("/api/v1/auth/me/delete", headers=h, json={"password": PW})
    from app.privacy import purge_due_accounts
    from app.storage import get_storage

    with SessionLocal() as db:
        assert purge_due_accounts(db) == 0  # still in the grace period
        assert purge_due_accounts(db, now=datetime.now(timezone.utc) + timedelta(days=15)) == 1
        u = db.query(m.User).filter(m.User.email.like("deleted+%")).one()
        assert u.status == "deleted" and u.name == "—" and u.password_hash == "!" and not u.memberships
        assert db.get(m.Project, pid) is None  # sole-member organisation: projects erased
    assert get_storage().list(f"projects/{pid}/") == []
    r = TestClient(app).post("/api/v1/auth/login", json={"email": "delete.me@example.com", "password": PW})
    assert r.status_code == 401


def test_photo_and_audit_retention(client, designer, monkeypatch):
    from app.retention import apply_retention

    pid = client.post("/api/v1/projects", headers=designer, json={"title": "Old photos"}).json()["id"]
    a = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("old.png", io.BytesIO(PNG + b"o"), "image/png")}).json()
    with SessionLocal() as db:
        db.get(m.Project, pid).updated_at = datetime.now(timezone.utc) - timedelta(days=400)
        db.add(m.AuditEvent(action="test.old", entity="x", created_at=datetime.now(timezone.utc) - timedelta(days=800)))
        db.commit()
        out = apply_retention(db)
        assert out["photos"] >= 1 and out["audit"] >= 1
        assert db.get(m.SourceAsset, a["id"]).scan_status == "purged"
    asset = next(x for x in client.get(f"/api/v1/projects/{pid}", headers=designer).json()["assets"] if x["id"] == a["id"])
    assert asset["url"] is None and asset["scan_status"] == "purged"
