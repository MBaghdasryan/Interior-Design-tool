import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="forma-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_tmp}/test.db")
os.environ.setdefault("STORAGE_DIR", f"{_tmp}/storage")
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("ENV", "test")
os.environ.setdefault("AI_DEFAULT_PROVIDER", "stub")
os.environ.setdefault("EXTERNAL_FETCH_LIVE", "false")
os.environ.setdefault("FORMA_JOBS_SYNC", "1")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client, email="designer@forma.local"):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "demo1234"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="session")
def designer(client):
    return login(client)


@pytest.fixture(scope="session")
def admin(client):
    return login(client, "admin@forma.local")
