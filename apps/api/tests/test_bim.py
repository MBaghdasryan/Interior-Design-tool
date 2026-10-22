"""P2-6: IFC4 export → editable import round trip (IfcOpenShell), project IFC import as a draft
base scene, Apple RoomPlan CapturedRoom JSON import."""
import json
import math

import pytest

from app import models as m
from app.bim import ifc_io, roomplan
from app.db import SessionLocal
from app.scene.demo import demo_base_scene
from app.scene.geometry import polygon_area

pytestmark = pytest.mark.usefixtures("client")


def _abs_openings(sc):
    out = []
    for o in sc.openings:
        w = sc.wall(o.wall_id)
        L = math.dist(w.a, w.b)
        mid = o.offset + o.width / 2
        out.append((round(w.a[0] + (w.b[0] - w.a[0]) * mid / L), round(w.a[1] + (w.b[1] - w.a[1]) * mid / L), round(o.width), o.type))
    return sorted(out)


def test_ifc_round_trip_is_exact():
    sc = demo_base_scene()
    data = ifc_io.to_ifc(sc, "Demo")
    assert data.startswith(b"ISO-10303-21") and b"IFCWALL" in data and b"IFCSPACE" in data and b"IFCDOOR" in data
    back, stats = ifc_io.from_ifc(data)
    assert stats["schema"] == "IFC4" and stats["walls"] == len(sc.walls) and stats["rooms"] == len(sc.rooms) and stats["skipped"] == 0
    for w0, w1 in zip(sc.walls, back.walls, strict=True):
        ends = min(math.dist(w1.a, w0.a) + math.dist(w1.b, w0.b), math.dist(w1.a, w0.b) + math.dist(w1.b, w0.a))
        assert ends < 1 and abs(w1.thickness - w0.thickness) < 1 and w1.source == "imported"
    assert sorted(round(polygon_area(r.polygon) / 1e4) for r in back.rooms) == sorted(round(polygon_area(r.polygon) / 1e4) for r in sc.rooms)
    assert {r.name for r in back.rooms} == {r.name for r in sc.rooms}
    assert _abs_openings(back) == _abs_openings(sc)  # same position, width and type (wall direction may flip)


def test_project_ifc_import_and_export_endpoints(client, designer):
    with SessionLocal() as db:
        proj = db.query(m.Project).filter(m.Project.title.like("Демо%")).first()
        pid = proj.id
        before = db.query(m.BaseScene).filter_by(project_id=pid).count()
    ifc = client.get(f"/api/v1/projects/{pid}/geometry.ifc", headers=designer)
    assert ifc.status_code == 200 and ifc.content.startswith(b"ISO-10303-21")
    up = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("model.ifc", ifc.content, "application/x-step")})
    assert up.status_code == 200, up.text
    r = client.post(f"/api/v1/projects/{pid}/assets/{up.json()['id']}/import-ifc", headers=designer).json()
    assert r["walls"] > 0 and r["rooms"] > 0
    with SessionLocal() as db:
        last = db.query(m.BaseScene).filter_by(project_id=pid).order_by(m.BaseScene.version.desc()).first()
        assert db.query(m.BaseScene).filter_by(project_id=pid).count() == before + 1 and not last.confirmed
        # keep the shared demo project as it was
        db.delete(last)
        db.query(m.SourceAsset).filter_by(id=up.json()["id"]).delete()
        db.commit()


def _surface(cx, cz, w, h, dx=1.0, dz=0.0, cy=None, conf="high"):
    return {"dimensions": [w, h, 0], "transform": [dx, 0, dz, 0, 0, 1, 0, 0, -dz, 0, dx, 0, cx, cy if cy is not None else h / 2, cz, 1], "confidence": {conf: {}}}


def roomplan_doc(with_floor=True):
    walls = [_surface(2.0, 0.0, 4.0, 2.7), _surface(4.0, 1.5, 3.0, 2.7, dx=0, dz=1), _surface(2.0, 3.0, 4.0, 2.7), _surface(0.0, 1.5, 3.0, 2.7, dx=0, dz=1)]
    doc = {"walls": walls, "doors": [_surface(1.0, 0.0, 0.9, 2.1, cy=1.05)], "windows": [_surface(4.0, 1.5, 1.2, 1.4, dx=0, dz=1, cy=1.6, conf="medium")],
           "openings": [], "objects": [{"category": {"sofa": {}}}]}
    if with_floor:
        doc["floors"] = [{"polygonCorners": [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]], "transform": [1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1]}]
    return json.dumps(doc).encode()


def test_roomplan_import():
    sc, stats = roomplan.parse(roomplan_doc())
    assert stats == {"walls": 4, "openings": 2, "rooms": 1, "objects_ignored": 1}
    assert abs(polygon_area(sc.rooms[0].polygon) / 1e6 - 12.0) < 0.01 and sc.rooms[0].source == "measured"
    win = next(o for o in sc.openings if o.type == "window")
    assert win.wall_id == "W2" and abs(win.sill - 900) < 1 and abs(win.width - 1200) < 1 and win.confidence == 0.8
    door = next(o for o in sc.openings if o.type == "door")
    assert door.wall_id == "W1" and abs(door.offset - 550) < 1
    sc2, _ = roomplan.parse(roomplan_doc(with_floor=False))
    assert sc2.rooms[0].source == "assumed" and any(a.key == "roomplan_outline" for a in sc2.assumptions)
    for bad, code in ((b"not json", "roomplan.not_json"), (b"{}", "roomplan.no_walls"), (json.dumps({"walls": [{"transform": [1]}]}).encode(), "roomplan.bad_surface")):
        with pytest.raises(roomplan.RoomPlanError) as e:
            roomplan.parse(bad)
        assert str(e.value) == code


def test_roomplan_endpoint(client, designer):
    with SessionLocal() as db:
        pid = db.query(m.Project).filter(m.Project.title.like("Демо%")).first().id
    r = client.post(f"/api/v1/projects/{pid}/import/roomplan", headers=designer, files={"file": ("room.json", roomplan_doc(), "application/json")}).json()
    assert r["walls"] == 4 and r["version"] >= 1
    assert client.post(f"/api/v1/projects/{pid}/import/roomplan", headers=designer, files={"file": ("x.json", b"[]", "application/json")}).json()["code"] == "roomplan.no_walls"
    with SessionLocal() as db:
        last = db.query(m.BaseScene).filter_by(project_id=pid).order_by(m.BaseScene.version.desc()).first()
        db.delete(last)
        db.query(m.SourceAsset).filter_by(project_id=pid, kind="scan").delete()
        db.commit()
