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


def test_crm_funnel_and_project_link(client, designer, admin):
    boss = login(client, "bureau@forma.local")
    c = client.post("/api/v1/crm/clients", headers=designer, json={"name": "Арам Петросян", "phone": "+374 91 000000", "source": "instagram", "budget_amd": 8_000_000, "area_m2": 78}).json()
    assert c["stage"] == "lead" and c["owner_name"]
    assert client.post("/api/v1/crm/clients", headers=designer, json={"name": "X", "stage": "nope"}).status_code == 422
    c = client.patch(f"/api/v1/crm/clients/{c['id']}", headers=boss, json={"stage": "proposal", "next_action": "Отправить КП"}).json()
    assert c["stage"] == "proposal"
    d = client.post(f"/api/v1/crm/clients/{c['id']}/activities", headers=designer, json={"kind": "call", "body": "Обсудили бюджет"}).json()
    assert [a["kind"] for a in d["activities"]][:2] == ["call", "stage"]
    pid = client.post(f"/api/v1/crm/clients/{c['id']}/projects", headers=designer, json={"title": "Квартира Арама"}).json()["project_id"]
    proj = client.get(f"/api/v1/projects/{pid}", headers=designer).json()
    assert proj["client_name"] == "Арам Петросян"
    lst = client.get("/api/v1/crm/clients", headers=designer).json()
    row = next(x for x in lst["items"] if x["id"] == c["id"])
    assert row["stage"] == "in_work" and row["projects"] == 1 and lst["counts"]["in_work"] >= 1
    # other tenants and suppliers cannot see the client
    sh = login(client, "supplier@forma.local")
    assert client.get(f"/api/v1/crm/clients/{c['id']}", headers=sh).status_code == 404
    assert client.get("/api/v1/crm/clients", headers=sh).status_code == 403
    assert client.delete(f"/api/v1/crm/clients/{c['id']}", headers=designer).json()["ok"]
    assert client.get(f"/api/v1/projects/{pid}", headers=designer).status_code == 200  # the project stays
    client.delete(f"/api/v1/projects/{pid}", headers=designer)


def test_tasks_workload_and_notifications(client, designer):
    boss = login(client, "bureau@forma.local")
    me = client.get("/api/v1/auth/me", headers=designer).json()
    tl = client.get("/api/v1/tasks", headers=boss).json()
    assert any(x["id"] == me["id"] for x in tl["members"])
    t = client.post("/api/v1/tasks", headers=boss, json={"title": "Проверить спецификацию", "assignee_id": me["id"], "priority": "high", "estimate_h": 3,
                                                          "due_at": "2020-01-01T10:00:00+00:00"}).json()
    assert t["overdue"] and t["assignee_name"]
    notes = client.get("/api/v1/notifications", headers=designer).json()
    items = notes["items"] if isinstance(notes, dict) else notes
    assert any(n["kind"] == "task_assigned" for n in items)
    w = client.get("/api/v1/team/workload", headers=boss).json()
    row = next(x for x in w["members"] if x["user_id"] == me["id"])
    assert row["overdue"] >= 1 and row["planned_h"] >= 3
    assert client.post("/api/v1/tasks", headers=boss, json={"title": "x", "assignee_id": "nobody"}).status_code == 422
    done = client.patch(f"/api/v1/tasks/{t['id']}", headers=designer, json={"status": "done"}).json()
    assert done["status"] == "done" and done["done_at"] and not done["overdue"]
    mine = client.get("/api/v1/tasks", headers=designer, params={"assignee": "me"}).json()["items"]
    assert any(x["id"] == t["id"] for x in mine)
    assert client.patch(f"/api/v1/tasks/{t['id']}", headers=login(client, "supplier@forma.local"), json={"status": "todo"}).status_code == 404
    assert client.delete(f"/api/v1/tasks/{t['id']}", headers=boss).json()["ok"]


def test_project_chat_team_notes_stay_internal(client, designer):
    pid = client.post("/api/v1/projects", headers=designer, json={"title": "Чат"}).json()["id"]
    share = client.get(f"/api/v1/projects/{pid}", headers=designer).json()["share_token"]
    client.post(f"/api/v1/projects/{pid}/messages", headers=designer, json={"body": "Внутренняя заметка", "visibility": "team"})
    client.post(f"/api/v1/projects/{pid}/messages", headers=designer, json={"body": "Здравствуйте! Варианты готовы", "visibility": "client"})
    msgs = client.get(f"/api/v1/projects/{pid}/messages", headers=designer).json()
    assert [m["visibility"] for m in msgs] == ["team", "client"] and all(m["mine"] for m in msgs)
    r = client.get(f"/api/v1/client/{share}")
    assert r.status_code == 200
    bodies = [c["body"] for c in r.json()["comments"]]
    assert "Здравствуйте! Варианты готовы" in bodies and "Внутренняя заметка" not in bodies  # team notes never reach the client
    boss = login(client, "bureau@forma.local")
    box = client.get("/api/v1/messages/inbox", headers=boss).json()
    row = next(x for x in box["items"] if x["project_id"] == pid)
    assert row["unread"] == 2
    client.post(f"/api/v1/projects/{pid}/messages/read", headers=boss)
    assert next(x for x in client.get("/api/v1/messages/inbox", headers=boss).json()["items"] if x["project_id"] == pid)["unread"] == 0
    client.delete(f"/api/v1/projects/{pid}", headers=designer)


def test_analytics_scopes(client, designer, admin):
    a = client.get("/api/v1/analytics", headers=designer).json()
    assert a["scope"] == "bureau" and len(a["months"]) == 6 and a["projects"]["total"] >= 1 and a["crm"] is not None and "platform" not in a
    assert len(a["projects"]["by_month"]) == 6 and sum(a["projects"]["by_month"]) <= a["projects"]["total"]
    g = client.get("/api/v1/analytics", headers=admin, params={"months": 12}).json()
    assert g["scope"] == "platform" and len(g["months"]) == 12 and g["platform"]["orgs"]["bureau"] >= 1 and "subscription" in g["platform"]["revenue"]
    assert g["projects"]["total"] >= a["projects"]["total"]
    assert client.get("/api/v1/analytics", headers=login(client, "supplier@forma.local")).status_code == 403
