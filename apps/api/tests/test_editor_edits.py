"""Manual editor: adding catalogue products, finishes per surface, room name and ceiling height — validated server-side."""
import pytest

from tests.conftest import login

pytestmark = pytest.mark.usefixtures("client")


def _variant(client, h):
    pid = client.post("/api/v1/projects", headers=h, json={"title": "Editor test"}).json()["id"]
    client.post(f"/api/v1/projects/{pid}/use-demo-geometry", headers=h)
    client.post(f"/api/v1/projects/{pid}/geometry/control-dimension", headers=h, json={"wall_id": "W1", "measured_mm": 9600})
    assert client.post(f"/api/v1/projects/{pid}/geometry/confirm", headers=h).json()["ok"]
    r = client.post(f"/api/v1/projects/{pid}/generate", headers=h, json={"preferences": {"budget_tier": "comfort", "styles": ["japandi"], "colors": ["#a68a64"]},
                                                                        "product_source": "external", "external_settings": {"sources": ["domus"]}})
    assert r.status_code == 200, r.text
    v = client.get(f"/api/v1/projects/{pid}/variants", headers=h).json()[0]
    return pid, client.get(f"/api/v1/projects/{pid}/variants/{v['id']}", headers=h).json()


def test_add_product_finish_and_room_props(client):
    h = login(client, "designer@forma.local")
    pid, v = _variant(client, h)
    sc = v["version"]["scene"]
    room = sc["rooms"][0]
    item = client.get("/api/v1/catalog/products", headers=h, params={"category": "armchair", "include_external": "false"}).json()["items"][0]
    cx = sum(p[0] for p in room["polygon"]) / len(room["polygon"])
    cy = sum(p[1] for p in room["polygon"]) / len(room["polygon"])
    new = {"id": "N-test", "room_id": room["id"], "category": "sofa", "name": "spoofed", "product_variant_id": item["ref"], "x": cx, "y": cy, "w": 1, "d": 1, "h": 1}
    paint = client.get("/api/v1/catalog/products", headers=h, params={"category": "wall_paint", "include_external": "false"}).json()["items"][0]
    finishes = [f for f in sc["finishes"] if not (f["room_id"] == room["id"] and f["surface"] == "ceiling")]
    finishes.append({"room_id": room["id"], "surface": "ceiling", "product_variant_id": paint["ref"]})
    url = f"/api/v1/projects/{pid}/variants/{v['id']}/objects"
    ver = client.put(url, headers=h, json={"objects": sc["objects"] + [new], "finishes": finishes,
                                           "rooms": [{"id": room["id"], "name": "Гостиная-кухня", "ceiling_height": 3000}]}).json()
    o = next(x for x in ver["scene"]["objects"] if x["id"] == "N-test")
    assert o["category"] == "armchair" and o["name"] != "spoofed" and o["w"] > 1 and o["code"].startswith("Н-")  # product data, not client data
    r = next(x for x in ver["scene"]["rooms"] if x["id"] == room["id"])
    assert r["name"] == "Гостиная-кухня" and r["ceiling_height"] == 3000
    assert any(f["surface"] == "ceiling" and f["product_variant_id"] == paint["ref"] for f in ver["scene"]["finishes"])
    assert any(ln.get("ref") == item["ref"] for ln in ver["estimate"]["lines"])  # the added product is costed
    bad = [{"room_id": room["id"], "surface": "floor", "product_variant_id": paint["ref"]}]
    assert client.put(url, headers=h, json={"objects": ver["scene"]["objects"], "finishes": bad}).json()["code"] == "catalog.same_category_only"
    assert client.put(url, headers=h, json={"objects": ver["scene"]["objects"], "rooms": [{"id": "nope", "name": "x"}]}).status_code == 422
    client.delete(f"/api/v1/projects/{pid}", headers=h)
