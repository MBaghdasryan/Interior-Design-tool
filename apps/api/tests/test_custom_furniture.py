"""P2-5: custom furniture configurator — module ranges and production constraints, cut list,
pricing only from manufacturer rates (otherwise «on request»), spec versions, DXF/PDF drawings,
ordering only for Production Ready projects (then the normal order flow incl. price re-check)."""
import ezdxf
import pytest

from app import models as m
from app.custom import engine
from app.db import SessionLocal

pytestmark = pytest.mark.usefixtures("client")
KITCHEN = [{"type": "kitchen_base", "w": 600, "h": 720, "d": 560, "body": "ldsp16", "front": "mdf_paint"},
           {"type": "kitchen_drawer_base", "w": 800, "h": 720, "d": 560, "body": "ldsp16", "front": "mdf_paint"},
           {"type": "kitchen_wall", "w": 600, "h": 720, "d": 320, "body": "ldsp16", "front": "mdf_paint"}]
RATES = {"body": {"ldsp16": 9000}, "front": {"mdf_paint": 38000}, "back": 3000, "edge_per_m": 450,
         "hardware": {"hinge_softclose": 2500, "runner_full": 9000}, "assembly_pct": 12, "lead_time_days": 21}


def test_constraints_cut_list_and_pricing():
    spec = {"family": "kitchen", "available_length_mm": 1200, "modules": KITCHEN + [{"type": "wardrobe_hinged", "w": 455, "h": 2800, "d": 560, "body": "x"}]}
    codes = {i["code"] for i in engine.validate(spec)}
    assert {"custom.run_too_long", "custom.wrong_family", "custom.step", "custom.range", "custom.material"} <= codes
    ok = {"family": "kitchen", "modules": KITCHEN}
    assert engine.validate(ok) == []
    parts = {(r["module"], r["part"]) for r in engine.cut_list(ok)}
    assert (1, "drawer_front") in parts and (0, "door") in parts and (2, "back") in parts
    assert engine.price(ok, None)["status"] == "quote_required"  # no rates → no invented price
    partial = engine.price(ok, {**RATES, "front": {}})
    assert partial["status"] == "quote_required" and "front:mdf_paint" in partial["missing"]
    p = engine.price(ok, RATES)
    assert p["status"] == "priced" and p["total_amd"] == sum(x["amount"] for x in p["breakdown"]) and p["lead_time_days"] == 21


def test_configurator_flow_versions_drawings_and_production_gate(client, designer):
    from tests.test_auth import STRONG, register

    # a verified manufacturer with its own rates
    register(client, "factory@example.com", kind="supplier", org_name="Mebel Factory")
    client.cookies.clear()
    fh = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'factory@example.com', 'password': STRONG}).json()['token']}"}
    client.cookies.clear()
    sid = client.put("/api/v1/supplier/onboarding/profile", headers=fh, json={"name": "Mebel Factory", "kind": "manufacturer"}).json()["supplier"]["id"]
    assert client.put("/api/v1/supplier/custom-rates", headers=fh, json={**RATES, "body": {"plywood": 1}}).status_code == 422
    assert client.put("/api/v1/supplier/custom-rates", headers=fh, json=RATES).json()["rates"]["lead_time_days"] == 21
    with SessionLocal() as db:
        db.get(m.Supplier, sid).verification = "verified"
        proj = db.query(m.Project).filter(m.Project.title.like("Демо%")).first()
        pid, level = proj.id, proj.accuracy_level
        db.commit()
    lib = client.get("/api/v1/custom/library", headers=designer).json()
    assert "kitchen_base" in lib["modules"] and sid in [x["id"] for x in lib["manufacturers"]]
    base = f"/api/v1/projects/{pid}/custom"
    c = client.post(base, headers=designer, json={"name": "Kitchen", "family": "kitchen", "modules": KITCHEN}).json()
    assert c["status"] == "valid" and c["pricing"]["status"] == "quote_required" and c["spec_version"] == 1
    c = client.put(f"{base}/{c['id']}", headers=designer, json={"name": "Kitchen", "family": "kitchen", "supplier_id": sid, "modules": KITCHEN}).json()
    assert c["spec_version"] == 2 and c["pricing"]["status"] == "priced" and c["pricing"]["total_amd"] > 0
    assert [v["version"] for v in client.get(f"{base}/{c['id']}/versions", headers=designer).json()] == [2, 1]
    dxf = client.get(f"{base}/{c['id']}/drawing.dxf", headers=designer)
    assert dxf.status_code == 200
    import io
    doc = ezdxf.read(io.StringIO(dxf.content.decode()))
    assert {"MODULES", "FRONTS", "DIMS"} <= {lay.dxf.name for lay in doc.layers}
    assert client.get(f"{base}/{c['id']}/drawing.pdf?lang=hy", headers=designer).content[:5] == b"%PDF-"
    bad = client.put(f"{base}/{c['id']}", headers=designer, json={"name": "K", "family": "kitchen", "supplier_id": sid, "modules": [{**KITCHEN[0], "w": 2000}]}).json()
    assert bad["status"] == "draft" and bad["issues"] and client.get(f"{base}/{c['id']}/drawing.dxf", headers=designer).status_code == 409
    client.put(f"{base}/{c['id']}", headers=designer, json={"name": "Kitchen", "family": "kitchen", "supplier_id": sid, "modules": KITCHEN})
    tmp = client.post(base, headers=designer, json={"name": "tmp", "family": "tv", "modules": []}).json()
    assert tmp["issues"][0]["code"] == "custom.empty" and client.delete(f"{base}/{tmp['id']}", headers=designer).json()["ok"]

    # ordering: refused below Production Ready, then a normal order with price re-check
    with SessionLocal() as db:
        db.get(m.Project, pid).accuracy_level = "verified"
        db.commit()
    assert client.post(f"{base}/{c['id']}/order", headers=designer).json()["code"] == "order.made_to_measure_requires_production"
    with SessionLocal() as db:
        db.get(m.Project, pid).accuracy_level = "production"
        db.commit()
    try:
        oid = client.post(f"{base}/{c['id']}/order", headers=designer).json()["order_id"]
        assert client.put(f"{base}/{c['id']}", headers=designer, json={"name": "K", "family": "kitchen", "modules": KITCHEN}).json()["code"] == "custom.ordered_locked"
        with SessionLocal() as db:
            cart_id = db.get(m.Order, oid).cart_id
            from app.commerce import orders as svc

            r = svc.recheck_cart(db, db.get(m.Cart, cart_id))
            db.commit()
        assert r["changed"] == [] and r["unavailable"] == []
    finally:
        with SessionLocal() as db:
            db.get(m.Project, pid).accuracy_level = level
            db.query(m.Order).filter(m.Order.project_id == pid, m.Order.supplier_id == sid).delete()
            db.query(m.CustomConfig).filter_by(project_id=pid).delete()
            db.commit()
