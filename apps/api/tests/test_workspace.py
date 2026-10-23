"""Cross-project sections: order registry scoped per tenant."""
import pytest

from app import models as m
from app.db import SessionLocal
from tests.conftest import login

pytestmark = pytest.mark.usefixtures("client")


def test_order_registry_is_tenant_scoped(client, designer, admin):
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "Реестр"}).json()["id"]
    with SessionLocal() as db:
        sup = db.query(m.Supplier).filter(m.Supplier.org_id.isnot(None)).first()
        o = m.Order(project_id=pid, supplier_id=sup.id, supplier_name=sup.name, status="in_production", items=[], totals={"goods": 100000, "delivery": 5000, "installation": 0},
                    history=[{"at": "2026-10-20T10:00:00+00:00", "from": "requested", "to": "confirmed", "by": "s"}, {"at": "2026-10-21T10:00:00+00:00", "from": "confirmed", "to": "in_production", "by": "s"}])
        db.add(o)
        db.commit()
        oid, sup_org = o.id, sup.org_id
    r = client.get("/api/v1/orders", headers=designer).json()
    row = next(x for x in r["items"] if x["id"] == oid)
    assert row["project_title"] == "Реестр" and row["amount_amd"] == 105000 and r["kpi"]["in_production"] >= 1
    assert [s["state"] for s in row["stages"]] == ["done", "done", "current", "planned", "planned"]
    assert any(x["id"] == oid for x in client.get("/api/v1/orders", headers=admin).json()["items"])
    assert not any(x["id"] == oid for x in client.get("/api/v1/orders", headers=login(client, "ops@forma.local")).json()["items"])
    # another bureau sees nothing of it
    other = client.post("/api/v1/admin/organizations", headers=admin, json={"name": "Other bureau", "kind": "bureau"}).json()
    from app.security import hash_password
    with SessionLocal() as db:
        u = m.User(email="other.head@bureau.am", name="Other", password_hash=hash_password("demo1234"))
        db.add(u)
        db.flush()
        db.add(m.Membership(user_id=u.id, org_id=other["id"], role="bureau_admin"))
        db.commit()
        assert sup_org
    assert not any(x["id"] == oid for x in client.get("/api/v1/orders", headers=login(client, "other.head@bureau.am")).json()["items"])
