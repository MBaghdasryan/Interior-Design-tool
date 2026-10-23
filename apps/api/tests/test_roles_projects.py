"""Role clean-up (no client / surveyor accounts, narrow catalogue operator), project deletion, supplier demand view."""
import pytest

from app import models as m
from app.db import SessionLocal
from app.security import ROLE_PERMISSIONS
from tests.conftest import login

pytestmark = pytest.mark.usefixtures("client")


def test_retired_roles_cannot_be_granted(client, admin):
    assert "client" not in ROLE_PERMISSIONS and "verifier" not in ROLE_PERMISSIONS
    boss = login(client, "bureau@forma.local")
    for role in ("client", "verifier"):
        r = client.post("/api/v1/team/invite", headers=boss, json={"email": f"{role}@x.am", "name": "X", "role": role})
        assert r.status_code == 422
    assert set(client.get("/api/v1/team", headers=boss).json()["roles"]) == {"bureau_admin", "designer", "collaborator"}


def test_catalogue_operator_is_limited_to_the_catalogue(client, designer):
    ops = login(client, "ops@forma.local")
    assert client.get("/api/v1/projects", headers=ops).json() == []  # no client projects
    pid = client.get("/api/v1/projects", headers=designer).json()[0]["id"]
    assert client.get(f"/api/v1/projects/{pid}", headers=ops).status_code == 404
    for path in ("/api/v1/admin/users", "/api/v1/admin/organizations", "/api/v1/admin/audit", "/api/v1/admin/ledger", "/api/v1/admin/ai", "/api/v1/admin/ai/costs"):
        assert client.get(path, headers=ops).status_code in (403, 404), path
    assert client.get("/api/v1/admin/sources", headers=ops).status_code == 200
    assert client.get("/api/v1/catalog/external/review", headers=ops).status_code == 200


def test_project_deletion(client, designer):
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "Удаляемый"}).json()["id"]
    other = login(client, "supplier@forma.local")
    assert client.delete(f"/api/v1/projects/{pid}", headers=other).status_code == 404  # another tenant
    assert client.delete(f"/api/v1/projects/{pid}", headers=designer).json()["ok"]
    assert client.get(f"/api/v1/projects/{pid}", headers=designer).status_code == 404
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "С заказом"}).json()["id"]
    with SessionLocal() as db:
        db.add(m.Order(project_id=pid, supplier_name="X", status="requested", items=[], totals={}))
        db.commit()
    assert client.delete(f"/api/v1/projects/{pid}", headers=designer).json()["code"] == "project.has_orders"


def test_supplier_demand_hides_client_data(client, designer):
    sh = login(client, "supplier@forma.local")
    d = client.get("/api/v1/supplier/demand", headers=sh).json()
    assert set(d) == {"usage", "requests", "counts"}
    titles = [p["title"] for p in client.get("/api/v1/projects", headers=designer).json()]
    blob = str(d["usage"])
    assert not any(t and t in blob for t in titles)
    for row in d["usage"]:
        assert row["ref"].startswith("P-") and row["stage"] in ("design", "request", "order") and row["items"]
