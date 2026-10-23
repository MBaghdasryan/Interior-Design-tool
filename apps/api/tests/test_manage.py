"""Administration: users, organisations, suppliers; organisation teams; manual product management;
platform staff opening bureau / supplier cabinets. Permissions checked for every role involved."""
import email
import email.policy
import io
import os
from pathlib import Path

import pytest

from app import models as m
from app.db import SessionLocal
from tests.conftest import login

pytestmark = pytest.mark.usefixtures("client")


def _last_mail(to: str) -> str:
    d = Path(os.environ["MAIL_DIR"])
    safe = "".join(ch if ch.isalnum() else "_" for ch in to)[:60]
    files = sorted(d.glob(f"*_{safe}.eml"))
    if not files:
        return ""
    msg = email.message_from_bytes(files[-1].read_bytes(), policy=email.policy.default)
    return "\n".join(part.get_content() for part in msg.walk() if part.get_content_maintype() == "text")


def test_platform_user_and_org_management(client, admin, designer):
    assert client.get("/api/v1/admin/users", headers=designer).status_code == 403
    orgs = client.get("/api/v1/admin/organizations", headers=admin).json()
    assert any(o["kind"] == "bureau" and o["users"] and o["projects"] for o in orgs)
    org = client.post("/api/v1/admin/organizations", headers=admin, json={"name": "Studio North", "kind": "bureau"}).json()
    assert client.post("/api/v1/admin/users", headers=admin, json={"email": "x@ex.am", "name": "X", "org_id": org["id"], "role": "supplier_admin"}).status_code == 422
    u = client.post("/api/v1/admin/users", headers=admin, json={"email": "new.designer@example.am", "name": "Nare", "org_id": org["id"], "role": "designer"}).json()
    assert u["memberships"][0]["role"] == "designer" and "reset-password?token=" in _last_mail("new.designer@example.am")
    assert client.post("/api/v1/admin/users", headers=admin, json={"email": "new.designer@example.am", "name": "N", "org_id": org["id"], "role": "designer"}).json()["code"] == "user.exists"
    u = client.post(f"/api/v1/admin/users/{u['id']}/memberships", headers=admin, json={"org_id": org["id"], "role": "bureau_admin"}).json()
    assert {x["role"] for x in u["memberships"]} == {"designer", "bureau_admin"}
    found = client.get("/api/v1/admin/users", headers=admin, params={"q": "nare"}).json()["items"]
    assert [x["email"] for x in found] == ["new.designer@example.am"]
    # suspension signs out and blocks the account
    s = client.patch(f"/api/v1/admin/users/{u['id']}", headers=admin, json={"status": "suspended"}).json()
    assert s["status"] == "suspended"
    assert client.post("/api/v1/auth/login", json={"email": "new.designer@example.am", "password": "whatever-123"}).status_code in (401, 403)
    client.patch(f"/api/v1/admin/users/{u['id']}", headers=admin, json={"status": "active"})
    me = client.get("/api/v1/auth/me", headers=admin).json()
    assert client.patch(f"/api/v1/admin/users/{me['id']}", headers=admin, json={"status": "suspended"}).json()["code"] == "user.self_action"
    pm = next(x for x in me["memberships"] if x["role"] == "platform_admin")
    with SessionLocal() as db:
        mid = db.query(m.Membership).filter_by(user_id=me["id"], org_id=pm["org_id"], role="platform_admin").one().id
    assert client.delete(f"/api/v1/admin/users/{me['id']}/memberships/{mid}", headers=admin).json()["code"] == "user.last_admin"
    assert client.post(f"/api/v1/admin/users/{u['id']}/reset-password", headers=admin).json()["ok"]
    assert client.delete(f"/api/v1/admin/users/{u['id']}", headers=admin).json()["status"] == "deletion_pending"
    with SessionLocal() as db:  # keep the shared database clean for the privacy purge test
        x = db.get(m.User, u["id"])
        x.status, x.deletion_due_at = "active", None
        db.commit()
    # organisation suspension: its roles stop working
    assert client.patch(f"/api/v1/admin/organizations/{org['id']}", headers=admin, json={"status": "suspended"}).json()["status"] == "suspended"
    assert client.patch(f"/api/v1/admin/organizations/{pm['org_id']}", headers=admin, json={"status": "suspended"}).json()["code"] == "org.platform_locked"


def test_bureau_admin_manages_the_team(client, designer):
    boss = login(client, "bureau@forma.local")
    t = client.get("/api/v1/team", headers=boss).json()
    assert t["org"]["kind"] == "bureau" and "designer" in t["roles"]
    assert client.get("/api/v1/team", headers=designer).status_code == 403  # a designer is not a team admin
    mem = client.post("/api/v1/team/invite", headers=boss, json={"email": "intern@studio.am", "name": "Intern", "role": "designer"}).json()
    assert mem["role"] == "designer" and "reset-password?token=" in _last_mail("intern@studio.am")
    assert client.post("/api/v1/team/invite", headers=boss, json={"email": "intern@studio.am", "name": "Intern", "role": "designer"}).json()["code"] == "team.already_member"
    assert client.post("/api/v1/team/invite", headers=boss, json={"email": "a@b.am", "name": "A", "role": "platform_admin"}).status_code == 422
    assert client.patch(f"/api/v1/team/{mem['membership_id']}", headers=boss, json={"role": "collaborator"}).json()["role"] == "collaborator"
    own = next(x for x in client.get("/api/v1/team", headers=boss).json()["members"] if x["email"] == "bureau@forma.local")
    assert client.delete(f"/api/v1/team/{own['membership_id']}", headers=boss).json()["code"] == "user.last_admin"
    assert client.delete(f"/api/v1/team/{mem['membership_id']}", headers=boss).json()["ok"]


def test_supplier_management_and_manual_products(client, admin, designer):
    s = client.post("/api/v1/admin/suppliers", headers=admin, json={"name": "Hand Made Store", "commission_pct": 7, "phone": "+374 10 000000"}).json()
    assert s["verification"] == "verified" and s["products"] == 0
    s = client.patch(f"/api/v1/admin/suppliers/{s['id']}", headers=admin, json={"city": "Gyumri", "commission_pct": 8}).json()
    assert s["city"] == "Gyumri" and s["commission_pct"] == 8
    body = {"supplier_id": s["id"], "category": "sofa", "name_ru": "Диван Ручной", "name_hy": "Բազմոց", "name_en": "Hand sofa", "styles": ["warm_minimal"],
            "variants": [{"sku": "HM-1", "price": 500000, "width_mm": 2200, "depth_mm": 900, "height_mm": 800, "stock_status": "in_stock"}]}
    assert client.post("/api/v1/catalog/products", headers=designer, json=body).status_code == 403
    prod = client.post("/api/v1/catalog/products", headers=admin, json=body).json()
    assert prod["variants"][0]["price_status"] == "confirmed" and prod["status"] == "active"
    items = client.get("/api/v1/catalog/products", headers=designer, params={"q": "hm-1"}).json()["items"]  # SQLite lower() is ASCII-only
    assert items and items[0]["price_amd"] == 500000
    pv = prod["variants"][0]["id"]
    assert client.get(f"/api/v1/catalog/variants/{pv}/product", headers=admin).json()["can_edit"] is True
    assert client.get(f"/api/v1/catalog/variants/{pv}/product", headers=designer).json()["can_edit"] is False
    prod = client.patch(f"/api/v1/catalog/variants/{pv}", headers=admin, json={"price": 450000}).json()
    assert prod["variants"][0]["price"] == 450000
    with SessionLocal() as db:
        assert db.query(m.PriceHistory).filter_by(variant_id=pv, source="manual").count() == 2  # created + changed
    prod = client.post(f"/api/v1/catalog/products/{prod['id']}/variants", headers=admin, json={"sku": "HM-2", "color": "grey", "price": 470000}).json()
    assert len(prod["variants"]) == 2
    assert client.post(f"/api/v1/catalog/products/{prod['id']}/variants", headers=admin, json={"sku": "HM-2"}).json()["code"] == "product.sku_exists"
    v2 = next(v["id"] for v in prod["variants"] if v["sku"] == "HM-2")
    assert len(client.delete(f"/api/v1/catalog/variants/{v2}", headers=admin).json()["variants"]) == 1
    assert client.delete(f"/api/v1/catalog/variants/{pv}", headers=admin).json()["code"] == "product.last_variant"
    assert client.patch(f"/api/v1/catalog/products/{prod['id']}", headers=admin, json={"name_ru": "Диван Ручной Plus"}).json()["name_ru"] == "Диван Ручной Plus"
    assert client.delete(f"/api/v1/catalog/products/{prod['id']}", headers=admin).json()["status"] == "archived"
    assert not client.get("/api/v1/catalog/products", headers=designer, params={"q": "hm-1"}).json()["items"]  # archived → hidden
    assert client.delete(f"/api/v1/admin/suppliers/{s['id']}", headers=admin).json()["ok"]


def test_supplier_staff_manage_only_their_products_and_admin_opens_cabinets(client, admin):
    sh = login(client, "supplier@forma.local")
    ov = client.get("/api/v1/supplier/overview", headers=sh).json()
    own = ov["supplier"]["id"]
    body = {"supplier_id": own, "category": "pendant_light", "name_ru": "Светильник Луна", "variants": [{"sku": "LUNA-1", "price": 120000}]}
    prod = client.post("/api/v1/catalog/products", headers=sh, json=body).json()
    assert prod["supplier_id"] == own
    other = client.post("/api/v1/admin/suppliers", headers=admin, json={"name": "Other Shop"}).json()
    assert client.post("/api/v1/catalog/products", headers=sh, json={**body, "supplier_id": other["id"]}).status_code == 403
    assert client.patch(f"/api/v1/catalog/products/{prod['id']}", headers=sh, json={"brand": "Ardoma"}).json()["brand"] == "Ardoma"
    assert any(x["sku"] == "LUNA-1" for x in client.get("/api/v1/supplier/products", headers=sh).json())
    # platform admin opens any supplier / bureau cabinet
    assert client.get("/api/v1/supplier/overview", headers=admin, params={"supplier_id": own}).json()["supplier"]["id"] == own
    assert any(x["sku"] == "LUNA-1" for x in client.get("/api/v1/supplier/products", headers=admin, params={"supplier_id": own}).json())
    bureau = next(o for o in client.get("/api/v1/admin/organizations", headers=admin, params={"kind": "bureau"}).json() if o["projects"])
    assert client.get("/api/v1/bureau/overview", headers=admin, params={"org_id": bureau["id"]}).json()["org"]["id"] == bureau["id"]
    assert client.get("/api/v1/bureau/overview", headers=sh, params={"org_id": bureau["id"]}).status_code == 404  # only platform staff may pick
    client.delete(f"/api/v1/catalog/products/{prod['id']}", headers=sh)
    client.delete(f"/api/v1/admin/suppliers/{other['id']}", headers=admin)


def test_platform_admin_edits_a_supplier_cabinet_and_bureau_settings(client, admin):
    sh = login(client, "supplier@forma.local")
    sid = client.get("/api/v1/supplier/overview", headers=sh).json()["supplier"]["id"]
    q = {"supplier_id": sid}
    row = client.post("/api/v1/supplier/locations", headers=admin, params=q, json={"name": "Склад Админ", "address": "Арагацотн 1", "kind": "warehouse"}).json()
    assert any(x["id"] == row["id"] for x in client.get("/api/v1/supplier/partner-data", headers=sh).json()["locations"])  # landed in that supplier
    assert client.delete(f"/api/v1/supplier/locations/{row['id']}", headers=admin, params=q).json()["ok"]
    assert client.put("/api/v1/supplier/feed", headers=admin, params=q, json={"enabled": False, "url": "", "interval_h": 24, "max_price_change_pct": 60}).status_code == 200
    assert client.get("/api/v1/supplier/category-map", headers=admin, params=q).status_code == 200
    # a supplier cannot reach another supplier through the parameter
    other = client.post("/api/v1/admin/suppliers", headers=admin, json={"name": "Third Shop"}).json()
    r = client.post("/api/v1/supplier/locations", headers=sh, params={"supplier_id": other["id"]}, json={"name": "X", "address": "", "kind": "warehouse"}).json()
    assert any(x["id"] == r["id"] for x in client.get("/api/v1/supplier/partner-data", headers=sh).json()["locations"])  # parameter ignored
    assert not client.get("/api/v1/supplier/partner-data", headers=admin, params={"supplier_id": other["id"]}).json()["locations"]
    client.delete(f"/api/v1/supplier/locations/{r['id']}", headers=sh)
    client.delete(f"/api/v1/admin/suppliers/{other['id']}", headers=admin)
    bureau = next(o for o in client.get("/api/v1/admin/organizations", headers=admin, params={"kind": "bureau"}).json() if o["projects"])
    tb = {"company": "Studio X"}
    assert client.put("/api/v1/bureau/settings", headers=admin, params={"org_id": bureau["id"]}, json={"title_block": tb}).json()["title_block"] == tb
    assert client.get("/api/v1/bureau/overview", headers=admin, params={"org_id": bureau["id"]}).json()["org"]["settings"]["title_block"] == tb


def test_price_list_import_cannot_target_another_supplier(client, admin):
    sh = login(client, "supplier@forma.local")
    other = client.post("/api/v1/admin/suppliers", headers=admin, json={"name": "Foreign Store"}).json()
    csv = "sku,name,category,price\nFS-1,Диван,sofa,100000\n"
    mapping = '{"sku":"sku","name":"name","category":"category","price":"price"}'
    by_name = client.post("/api/v1/catalog/import/commit", headers=sh, files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
                          data={"supplier_name": "Foreign Store", "mapping": mapping})
    assert by_name.status_code == 403
    by_id = client.post("/api/v1/catalog/import/commit", headers=sh, files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
                        data={"supplier_id": other["id"], "mapping": mapping})
    assert by_id.status_code == 403
    ok = client.post("/api/v1/catalog/import/commit", headers=admin, files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
                     data={"supplier_id": other["id"], "mapping": mapping})
    assert ok.status_code == 200 and ok.json()["created"] == 1
    client.delete(f"/api/v1/admin/suppliers/{other['id']}", headers=admin)
