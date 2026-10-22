"""P2-3: supplier onboarding (profile → agreement → catalogue → submit → platform verification),
unverified suppliers hidden from the catalogue, asset validation by content, category mapping,
warehouses / delivery options / services."""
import io
import json
import struct

import pytest
from PIL import Image

from app import models as m
from app.catalog.assets import AssetInvalid, validate
from app.db import SessionLocal

pytestmark = pytest.mark.usefixtures("client")


def glb(doc: dict | None = None) -> bytes:
    js = json.dumps(doc or {"asset": {"version": "2.0", "generator": "test"}, "meshes": [{"primitives": []}]}).encode()
    js += b" " * (-len(js) % 4)
    return b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js)) + struct.pack("<II", len(js), 0x4E4F534A) + js


def png(name_size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", name_size, (120, 90, 60)).save(buf, "PNG")
    return buf.getvalue()


def test_asset_validation_by_content():
    assert validate("model3d", "chair.glb", glb())[1]["meshes"] == 1
    for kind, name, data, code in [("model3d", "chair.glb", png(), "not_glb"), ("model3d", "x.glb", glb({"asset": {"version": "1.0"}, "meshes": [{}]}), "gltf_version"),
                                   ("model3d", "x.glb", glb()[:-4], "glb_truncated"), ("model3d", "x.glb", glb({"asset": {"version": "2.0"}}), "gltf_no_mesh"),
                                   ("texture", "a.png", b"not an image", "not_image"), ("certificate", "c.pdf", b"<html>", "not_pdf"),
                                   ("bim_cad", "m.ifc", b"hello", "not_ifc"), ("bim_cad", "m.dwg", b"MZ\x90", "not_dwg"), ("texture", "a.exe", b"MZ", "extension"),
                                   ("model3d", "a.glb", b"", "empty"), ("video", "a.mp4", b"x", "kind")]:
        with pytest.raises(AssetInvalid) as e:
            validate(kind, name, data)
        assert e.value.code == code, (name, code)
    assert validate("texture", "Oak_Roughness_2k.png", png())[1]["pbr_channel"] == "roughness"
    assert validate("bim_cad", "w.ifc", b"ISO-10303-21;\nHEADER;FILE_SCHEMA(('IFC4'));")[1]["schema"] == "IFC4"
    assert validate("bim_cad", "w.dwg", b"AC1032" + b"\0" * 20)[1]["dwg_version"] == "AC1032"


def test_onboarding_to_verification_and_catalogue_visibility(client, admin):
    from tests.test_auth import STRONG, register

    r = register(client, "new.store@example.com", kind="supplier", org_name="New Store LLC")
    assert r.status_code == 200, r.text
    client.cookies.clear()
    h = {"Authorization": f"Bearer {client.post('/api/v1/auth/login', json={'email': 'new.store@example.com', 'password': STRONG}).json()['token']}"}
    client.cookies.clear()
    st = client.get("/api/v1/supplier/onboarding", headers=h).json()
    assert st["verification"] == "not_started" and not st["steps"]["profile"]
    st = client.put("/api/v1/supplier/onboarding/profile", headers=h, json={"name": "New Store", "website": "https://newstore.example", "tax_id": "01234567"}).json()
    assert st["verification"] == "pending" and st["steps"]["profile"]
    sid = st["supplier"]["id"]
    assert client.post("/api/v1/supplier/onboarding/submit", headers=h).json()["code"] == "supplier.onboarding_incomplete"
    assert client.post("/api/v1/supplier/onboarding/agreement", headers=h, json={"version": "1999", "accept": True}).status_code == 422
    assert client.post("/api/v1/supplier/onboarding/agreement", headers=h, json={"version": st["agreement_version"], "accept": True}).json()["steps"]["agreement"]
    # category mapping is applied when the price list is imported
    assert client.put("/api/v1/supplier/category-map", headers=h, json={"mapping": {"Диваны": "not_a_category"}}).status_code == 422
    assert client.put("/api/v1/supplier/category-map", headers=h, json={"mapping": {"Մեր բազմոցներ": "sofa"}}).json()["mapping"] == {"մեր բազմոցներ": "sofa"}
    with SessionLocal() as db:
        from app.catalog.pricelist import apply_price_list

        sup = db.get(m.Supplier, sid)
        r = apply_price_list(db, sup, [{"sku": "NS-1", "name": "Model Lumen", "category": "Մեր բազմոցներ", "price": "350000"}],
                             {"sku": "sku", "name": "name", "category": "category", "price": "price"})
        db.commit()
        assert r["created"] == 1
        vid = db.query(m.ProductVariant).filter_by(sku="NS-1").one().id
    # pending supplier: invisible in catalogue search
    assert not client.get("/api/v1/catalog/products", headers=admin, params={"q": "lumen"}).json()["items"]
    st = client.post("/api/v1/supplier/onboarding/submit", headers=h).json()
    assert st["steps"]["submitted"] and st["steps"]["category_map"]
    pending = client.get("/api/v1/admin/suppliers", headers=admin, params={"verification": "pending"}).json()
    assert sid in [x["supplier"]["id"] for x in pending]
    assert client.post(f"/api/v1/admin/suppliers/{sid}/verification", headers=h, json={"decision": "verified"}).status_code == 403
    assert client.post(f"/api/v1/admin/suppliers/{sid}/verification", headers=admin, json={"decision": "verified", "note": "docs ok"}).json()["verification"] == "verified"
    items = client.get("/api/v1/catalog/products", headers=admin, params={"q": "lumen"}).json()["items"]
    assert items and items[0]["category"] == "sofa"

    # assets: 3D model linked to the SKU, texture with PBR channel, certificate; content validated
    files = {"file": ("lumen.glb", glb(), "model/gltf-binary")}
    a = client.post("/api/v1/supplier/assets", headers=h, files=files, data={"kind": "model3d", "variant_id": vid}).json()
    assert a["meta"]["format"] == "gltf2" and a["url"].startswith("http")
    with SessionLocal() as db:
        assert db.get(m.ProductVariant, vid).model3d_url.endswith("lumen.glb")
    bad = client.post("/api/v1/supplier/assets", headers=h, files={"file": ("fake.glb", png(), "model/gltf-binary")}, data={"kind": "model3d"})
    assert bad.status_code == 422 and bad.json()["code"] == "asset.not_glb"
    t = client.post("/api/v1/supplier/assets", headers=h, files={"file": ("fabric_normal.png", png(), "image/png")}, data={"kind": "texture"}).json()
    assert t["meta"]["pbr_channel"] == "normal"
    eicar = b"%PDF-1.4 X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
    assert client.post("/api/v1/supplier/assets", headers=h, files={"file": ("cert.pdf", eicar, "application/pdf")}, data={"kind": "certificate"}).json()["code"] == "file.malware"
    assert len(client.get("/api/v1/supplier/assets", headers=h).json()) == 2
    from tests.conftest import login

    other = login(client, "supplier@forma.local")
    assert client.delete(f"/api/v1/supplier/assets/{a['id']}", headers=other).status_code == 404  # another supplier's asset
    assert client.delete(f"/api/v1/supplier/assets/{a['id']}", headers=h).json()["ok"]
    with SessionLocal() as db:
        assert db.get(m.ProductVariant, vid).model3d_url == ""

    # warehouses, delivery options, installation services
    assert client.post("/api/v1/supplier/locations", headers=h, json={"name": "Main warehouse", "address": "Arshakunyats 10"}).status_code == 200
    assert client.post("/api/v1/supplier/delivery-options", headers=h, json={"name": "Yerevan", "fee_amd": 5000, "days_min": 3, "days_max": 1}).status_code == 422
    d = client.post("/api/v1/supplier/delivery-options", headers=h, json={"name": "Yerevan", "regions": ["Yerevan"], "fee_amd": 5000, "days_min": 1, "days_max": 2}).json()
    assert client.post("/api/v1/supplier/services", headers=h, json={"name": "Sofa assembly", "category": "sofa", "price_amd": 8000}).status_code == 200
    pdata = client.get("/api/v1/supplier/partner-data", headers=h).json()
    assert len(pdata["locations"]) == 1 and pdata["delivery-options"][0]["fee_amd"] == 5000 and pdata["services"][0]["category"] == "sofa"
    assert client.delete(f"/api/v1/supplier/delivery-options/{d['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/v1/supplier/delivery-options/{d['id']}", headers=h).json()["ok"]
