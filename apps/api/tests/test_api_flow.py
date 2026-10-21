"""End-to-end critical path through the HTTP API:
intake → geometry confirm → AI pipeline (external catalog) → 3 variants → AI change
command → manual edit → approval snapshot → RFQ → album + exports; plus tenant
isolation and the public client viewer."""
import io

from tests.conftest import login


def _demo_project(client, h):
    return next(p for p in client.get("/api/v1/projects", headers=h).json() if p["title"].startswith("Демо"))


def test_full_flow(client, designer):
    h = designer
    proj = _demo_project(client, h)
    pid = proj["id"]

    # intake: upload a plan image (validated by magic bytes), bad extension rejected
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 2000
    r = client.post(f"/api/v1/projects/{pid}/assets", headers=h, files={"file": ("план.png", io.BytesIO(png), "image/png")})
    assert r.status_code == 200 and r.json()["kind"] == "plan_image"
    r = client.post(f"/api/v1/projects/{pid}/assets", headers=h, files={"file": ("x.pdf", io.BytesIO(png), "application/pdf")})
    assert r.status_code == 415

    # geometry + control dimension + confirm
    g = client.get(f"/api/v1/projects/{pid}/geometry", headers=h).json()
    assert g["scene"]["walls"] and g["mask"]["summary"]["green"] > 0
    r = client.post(f"/api/v1/projects/{pid}/geometry/control-dimension", headers=h, json={"wall_id": "W1", "measured_mm": 9600})
    assert r.status_code == 200
    assert client.post(f"/api/v1/projects/{pid}/geometry/confirm", headers=h).json()["ok"]

    # AI pipeline with External Catalog (no live fetch → honest DEMO fallback, flagged)
    r = client.post(f"/api/v1/projects/{pid}/generate", headers=h, json={"preferences": {"budget_tier": "comfort"}, "product_source": "external",
                                                                        "external_settings": {"sources": ["domus", "vlv", "profal"], "allow_quote": True}})
    assert r.status_code == 200, r.text
    job = client.get(f"/api/v1/projects/{pid}/jobs/{r.json()['id']}", headers=h).json()
    assert job["status"] == "succeeded", job
    keys = [s["key"] for s in job["steps"]]
    assert keys[0] == "cat_needs" and "assemble" in keys
    assert all(s["status"] in ("done", "warning") for s in job["steps"])
    assert job["counters"]["rfq_needs"] >= 1  # Profal → quote_required, not an invented price

    variants = client.get(f"/api/v1/projects/{pid}/variants", headers=h).json()
    assert len(variants) == 3
    v = variants[0]
    vid = v["id"]
    detail = client.get(f"/api/v1/projects/{pid}/variants/{vid}", headers=h).json()
    est = detail["version"]["estimate"]
    assert est["totals"]["known"] > 0 and any("DEMO" in d for d in est["disclaimers"])

    # AI change command: preview, then apply → new version with diff
    cmd = "Сделай кухню светлее, замени диван на более компактный, добавь закрытый шкаф в коридоре и сократи бюджет на 700 000 AMD."
    prev = client.post(f"/api/v1/projects/{pid}/variants/{vid}/command", headers=h, json={"command": cmd}).json()
    assert prev["provider"] == "stub" and len(prev["plan"]["operations"]) == 4
    assert "version" not in prev
    applied = client.post(f"/api/v1/projects/{pid}/variants/{vid}/command", headers=h, json={"command": cmd, "apply": True, "plan": prev["plan"]}).json()
    assert applied["version"]["number"] == 2
    assert applied["total_after"] < est["totals"]["known"]

    # manual edit: lock + move an object → version 3, estimate recomputed
    cur = client.get(f"/api/v1/projects/{pid}/variants/{vid}", headers=h).json()["version"]
    objs = cur["scene"]["objects"]
    objs[0]["locked"] = True
    r = client.put(f"/api/v1/projects/{pid}/variants/{vid}/objects", headers=h, json={"objects": objs, "note": "lock"})
    assert r.status_code == 200 and r.json()["number"] == 3

    # alternatives + replacement
    oid = next(o["id"] for o in objs if o["category"] == "sofa")
    alts = client.get(f"/api/v1/projects/{pid}/variants/{vid}/objects/{oid}/alternatives", headers=h).json()
    other = next(a for a in alts["alternatives"] if not a["current"] and a["fits"])
    r = client.post(f"/api/v1/projects/{pid}/variants/{vid}/objects/{oid}/replace", headers=h, json={"ref": other["ref"]})
    assert r.status_code == 200

    versions = client.get(f"/api/v1/projects/{pid}/variants/{vid}/versions", headers=h).json()
    assert [x["number"] for x in versions][:2] == [4, 3]
    cmp = client.get(f"/api/v1/projects/{pid}/variants/{vid}/compare", headers=h, params={"a": versions[-1]["id"], "b": versions[0]["id"]}).json()
    assert "total_delta" in cmp

    # approval freezes a price snapshot
    issues = client.get(f"/api/v1/projects/{pid}/variants/{vid}", headers=h).json()["version"]["issues"]
    assert not [i for i in issues if i["severity"] == "block"], issues
    ap = client.post(f"/api/v1/projects/{pid}/variants/{vid}/approve", headers=h, json={"decision": "approved"})
    assert ap.status_code == 200 and ap.json()["estimate_snapshot_id"]
    r = client.put(f"/api/v1/projects/{pid}/variants/{vid}/objects", headers=h, json={"objects": objs})
    assert r.status_code == 409  # approved versions are immutable

    # RFQ per supplier; DEMO supplier cannot be sent to
    rfqs = client.post(f"/api/v1/projects/{pid}/rfqs", headers=h, json={"variant_id": vid}).json()
    assert rfqs
    assert client.post(f"/api/v1/projects/{pid}/rfqs/{rfqs[0]['id']}/send", headers=h).status_code == 409
    cart = client.post(f"/api/v1/projects/{pid}/cart", headers=h, json={"variant_id": vid}).json()
    assert cart and all("commission_platform" in o["totals"] for o in cart)

    # album + exports
    r = client.post(f"/api/v1/projects/{pid}/documents/album", headers=h, json={"variant_id": vid, "lang": "hy"})
    assert r.json()["status"] == "succeeded", r.json()
    docs = client.get(f"/api/v1/projects/{pid}/documents", headers=h).json()
    kinds = {d["kind"] for d in docs}
    assert {"album_pdf", "dxf", "xlsx", "csv", "glb", "json"} <= kinds
    album = next(d for d in docs if d["kind"] == "album_pdf")
    path = album["url"].split("http://localhost:8000")[1]
    f = client.get(path)
    assert f.status_code == 200 and f.content[:4] == b"%PDF"
    assert client.get(path.replace("sig=", "sig=x")).status_code == 403

    # DWG requires APS credentials → explicit 409, not a fake file
    assert client.post(f"/api/v1/projects/{pid}/documents/dwg", headers=h, json={"variant_id": vid}).status_code == 409

    # public client viewer by share token
    token = client.get(f"/api/v1/projects/{pid}", headers=h).json()["share_token"]
    cv = client.get(f"/api/v1/client/{token}").json()
    assert len(cv["variants"]) == 3
    assert client.post(f"/api/v1/client/{token}/comments", json={"name": "Анна", "body": "Нравится!", "variant_id": vid}).status_code == 200
    assert client.get("/api/v1/client/not-a-token").status_code == 404


def test_tenant_isolation(client, designer):
    pid = _demo_project(client, designer)["id"]
    supplier = login(client, "supplier@forma.local")
    assert client.get(f"/api/v1/projects/{pid}", headers=supplier).status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/v1/projects", headers=supplier).json())
    assert client.get("/api/v1/projects").status_code == 401


def test_admin_sources_and_permissions(client, admin, designer):
    srcs = client.get("/api/v1/admin/sources", headers=admin).json()
    assert {s["key"] for s in srcs} == {"domus", "idealsystem", "nortun", "effectgroup", "lideria", "profal", "vlv", "vega"}
    domus = next(s for s in srcs if s["key"] == "domus")
    assert domus["policy"]["search_disallowed"] is True
    r = client.patch(f"/api/v1/admin/sources/{domus['id']}", headers=admin, json={"enabled": False})
    assert r.json()["enabled"] is False
    client.patch(f"/api/v1/admin/sources/{domus['id']}", headers=admin, json={"enabled": True})
    assert client.get("/api/v1/admin/sources", headers=designer).status_code == 403
    t = client.post(f"/api/v1/admin/sources/{domus['id']}/test", headers=admin).json()
    assert t["status"] in ("ok", "needs_audit")


def test_catalog_import_preview_and_guard(client, admin):
    csv_data = "Артикул;Название;Категория;Цена;Ширина;Глубина;Высота\nS-1;Диван угловой;sofa;650 000 ֏;2400;950;820\nS-2;;sofa;100;1;1;1\n"
    r = client.post("/api/v1/catalog/import/preview", headers=admin, files={"file": ("p.csv", io.BytesIO(csv_data.encode()), "text/csv")})
    body = r.json()
    assert body["mapping"]["sku"] == "Артикул" and body["valid_in_preview"] == 1
    import json

    r = client.post("/api/v1/catalog/import/commit", headers=admin, files={"file": ("p.csv", io.BytesIO(csv_data.encode()), "text/csv")},
                    data={"supplier_name": "Test Store", "mapping": json.dumps(body["mapping"])})
    assert r.json()["created"] == 1 and r.json()["rejected"] == 1
    # mass price jump is rejected by the guard
    bad = csv_data.replace("650 000", "9 650 000")
    r = client.post("/api/v1/catalog/import/commit", headers=admin, files={"file": ("p.csv", io.BytesIO(bad.encode()), "text/csv")},
                    data={"supplier_name": "Test Store", "mapping": json.dumps(body["mapping"])})
    assert r.status_code == 409
