"""Autodesk APS client against a mock transport (no network)."""
import json

import httpx

from app.aps.client import ApsClient, extract_rooms, urn_of
from app.config import Settings


def make_client(log):
    def handler(req: httpx.Request):
        log.append((req.method, req.url.path))
        p = req.url.path
        if p == "/authentication/v2/token":
            assert req.headers["Authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "T", "expires_in": 3599})
        if p == "/oss/v2/buckets":
            return httpx.Response(409, json={})  # already exists is fine
        if p.endswith("/signeds3upload") and req.method == "GET":
            return httpx.Response(200, json={"uploadKey": "UK", "urls": ["https://s3.example/put"]})
        if req.url.host == "s3.example":
            return httpx.Response(200)
        if p.endswith("/signeds3upload") and req.method == "POST":
            assert json.loads(req.content)["uploadKey"] == "UK"
            return httpx.Response(200, json={"objectId": "urn:adsk.objects:os.object:b/k.dxf", "size": 10})
        if p == "/modelderivative/v2/designdata/job":
            body = json.loads(req.content)
            assert body["output"]["formats"][0]["type"] == "svf2"
            return httpx.Response(200, json={"result": "created", "urn": body["input"]["urn"]})
        if p.endswith("/manifest"):
            return httpx.Response(200, json={"status": "success", "progress": "complete"})
        if p.endswith("/workitems"):
            body = json.loads(req.content)
            assert body["activityId"].endswith("FormaDxfToDwg+prod")
            assert body["arguments"]["outputDwg"]["verb"] == "put"
            return httpx.Response(200, json={"id": "WI1", "status": "pending"})
        return httpx.Response(404)

    s = Settings(aps_client_id="CID", aps_client_secret="SEC", aps_bucket_key="b")
    return ApsClient(settings=s, http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_urn_encoding():
    assert urn_of("urn:adsk.objects:os.object:b/k.dxf") == "dXJuOmFkc2sub2JqZWN0czpvcy5vYmplY3Q6Yi9rLmR4Zg"


def test_upload_translate_workitem_flow():
    log = []
    c = make_client(log)
    up = c.upload("k.dxf", b"0\nEOF\n")
    assert up["urn"] == urn_of(up["objectId"])
    c.translate(up["urn"])
    assert c.wait_translation(up["urn"], poll_s=0)["status"] == "success"
    wi = c.workitem_dxf_to_dwg("https://in", "https://out")
    assert wi["id"] == "WI1"
    # token is cached: a single auth call for the whole flow
    assert sum(1 for m, p in log if p == "/authentication/v2/token") == 1


def test_disabled_without_credentials():
    import pytest

    from app.aps.client import ApsDisabled

    c = ApsClient(settings=Settings(aps_client_id=None, aps_client_secret=None))
    with pytest.raises(ApsDisabled):
        c.token()


def test_extract_rooms_from_properties():
    props = [
        {"objectid": 1, "name": "Room 101", "externalId": "e1", "properties": {"Identity Data": {"Name": "Кухня", "Number": "101", "Category": "Revit Rooms"},
                                                                              "Dimensions": {"Area": "11.37 m^2"}, "Constraints": {"Level": "Level 16"}}},
        {"objectid": 2, "name": "Wall", "properties": {"Identity Data": {"Category": "Revit Walls"}}},
        {"objectid": 3, "name": "IfcSpace", "properties": {"Item": {"Category": "IfcSpace", "Name": "Bedroom"}, "Quantities": {"NetFloorArea": "15.2"}}},
    ]
    rooms = extract_rooms(props)
    assert [r["name"] for r in rooms] == ["Кухня", "Bedroom"]
    assert rooms[0]["area_m2"] == 11.37 and rooms[1]["area_m2"] == 15.2


def test_activity_definition_shape():
    c = ApsClient(settings=Settings(aps_client_id="CID", aps_client_secret="S"))
    a = c.activity_definition()
    assert "accoreconsole.exe" in a["commandLine"][0]
    assert set(a["parameters"]) == {"inputFile", "outputDwg"}


def test_capability_labels_are_honest(client, designer):
    caps = {c["key"]: c for c in client.get("/api/v1/aps/status", headers=designer).json()["capabilities"]}
    assert set(caps) == {"view", "metadata", "editable_import", "ifc_export", "dwg_export"}
    assert caps["editable_import"]["status"] == caps["ifc_export"]["status"] == "in_development"
    assert caps["view"]["status"] in ("supported", "needs_keys")  # never "supported" without APS keys
    assert not any(caps[k]["live_verified"] for k in ("view", "metadata", "editable_import", "ifc_export"))  # no real bureau RVT/IFC run yet
