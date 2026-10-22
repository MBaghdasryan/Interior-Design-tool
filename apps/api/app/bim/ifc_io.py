"""IFC4 export and editable import of walls, openings and spaces (P2-6, IfcOpenShell).

Coordinates: the scene is a plan with Y pointing down (sheet orientation); IFC is Z-up with Y
pointing up, so plan (X, Y) ↔ IFC (x, −y). Units: millimetres in both (IfcSIUnit MILLI METRE).

Export: IfcProject → IfcSite → IfcBuilding → IfcBuildingStorey; IfcWall (swept rectangle along the
wall axis), IfcOpeningElement voiding the wall + IfcDoor / IfcWindow filling it, IfcSpace per room
(extruded footprint, name, net floor area quantity).
Import: any IFC2X3/IFC4 file — wall axis and thickness from the element's geometry footprint
(principal direction of the XY vertices), doors/windows located on their host wall through
IfcRelFillsElement/IfcRelVoidsElement (fallback: nearest wall), spaces from their footprint.
The result is a draft base scene (source="imported") the designer reviews and confirms."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import numpy as np

from ..scene.geometry import polygon_area
from ..scene.model import Opening, Room, Scene, Wall


# ------------------------------------------------------------------ export
def to_ifc(scene: Scene, project_name: str = "Renovara") -> bytes:
    import ifcopenshell.api as api

    f = api.run("project.create_file", version="IFC4")
    project = api.run("root.create_entity", f, ifc_class="IfcProject", name=project_name or "Renovara")
    length = api.run("unit.add_si_unit", f, unit_type="LENGTHUNIT", prefix="MILLI")
    area = api.run("unit.add_si_unit", f, unit_type="AREAUNIT")
    api.run("unit.assign_unit", f, units=[length, area])
    model = api.run("context.add_context", f, context_type="Model")
    body = api.run("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model)
    site = api.run("root.create_entity", f, ifc_class="IfcSite", name="Site")
    building = api.run("root.create_entity", f, ifc_class="IfcBuilding", name=scene.name or "Building")
    storey = api.run("root.create_entity", f, ifc_class="IfcBuildingStorey", name="Level 0")
    api.run("aggregate.assign_object", f, relating_object=project, products=[site])
    api.run("aggregate.assign_object", f, relating_object=site, products=[building])
    api.run("aggregate.assign_object", f, relating_object=building, products=[storey])

    def place(el, x, y, z, angle):
        c, s = math.cos(angle), math.sin(angle)
        mat = np.array([[c, -s, 0, x], [s, c, 0, -y], [0, 0, 1, z], [0, 0, 0, 1]], dtype=float)
        api.run("geometry.edit_object_placement", f, product=el, matrix=mat, is_si=False)

    walls = {}
    for w in scene.walls:
        (ax, ay), (bx, by) = w.a, w.b
        length = math.hypot(bx - ax, by - ay)
        if length < 1:
            continue
        height = w.height or scene.ceiling_height
        ang = math.atan2(-(by - ay), bx - ax)  # IFC y is flipped
        el = api.run("root.create_entity", f, ifc_class="IfcWall", name=w.id)
        # axis-centred wall: shift the placement by half the thickness perpendicular to the axis
        nx, ny = -math.sin(ang) * w.thickness / 2, math.cos(ang) * w.thickness / 2
        place(el, ax - nx, ay + ny, 0, ang)
        rep = api.run("geometry.add_wall_representation", f, context=body, length=length / 1000, height=height / 1000, thickness=w.thickness / 1000)  # API takes SI metres
        api.run("geometry.assign_representation", f, product=el, representation=rep)
        api.run("spatial.assign_container", f, relating_structure=storey, products=[el])
        pset = api.run("pset.add_pset", f, product=el, name="Pset_WallCommon")
        api.run("pset.edit_pset", f, pset=pset, properties={"LoadBearing": bool(w.load_bearing), "IsExternal": w.kind == "exterior"})
        walls[w.id] = (el, w, ang, length)
    for o in scene.openings:
        host = walls.get(o.wall_id)
        if not host:
            continue
        wel, w, ang, length = host
        (ax, ay) = w.a
        ux, uy = (w.b[0] - ax) / length, (w.b[1] - ay) / length
        sx, sy = ax + ux * o.offset, ay + uy * o.offset
        nx, ny = -math.sin(ang) * (w.thickness / 2 + 5), math.cos(ang) * (w.thickness / 2 + 5)
        op = api.run("root.create_entity", f, ifc_class="IfcOpeningElement", name=f"{o.id}-void")
        place(op, sx - nx, sy + ny, o.sill, ang)
        orep = api.run("geometry.add_wall_representation", f, context=body, length=o.width / 1000, height=o.height / 1000, thickness=(w.thickness + 10) / 1000)
        api.run("geometry.assign_representation", f, product=op, representation=orep)
        api.run("feature.add_feature", f, feature=op, element=wel)
        cls = "IfcWindow" if o.type == "window" else "IfcDoor"
        fill = api.run("root.create_entity", f, ifc_class=cls, name=o.id)
        fill.OverallWidth, fill.OverallHeight = float(o.width), float(o.height)
        fill.ObjectType = o.type  # keeps entrance / balcony / sliding doors and plain openings on re-import
        place(fill, sx - nx, sy + ny, o.sill, ang)
        api.run("feature.add_filling", f, opening=op, element=fill)
        api.run("spatial.assign_container", f, relating_structure=storey, products=[fill])
    for r in scene.rooms:
        if len(r.polygon) < 3:
            continue
        sp = api.run("root.create_entity", f, ifc_class="IfcSpace", name=r.name or r.type)
        sp.LongName = r.type
        place(sp, 0, 0, 0, 0)
        poly = [(float(x), float(-y)) for x, y in r.polygon]
        prof = f.createIfcArbitraryClosedProfileDef("AREA", None, f.createIfcPolyline([f.createIfcCartesianPoint(p) for p in [*poly, poly[0]]]))
        solid = f.createIfcExtrudedAreaSolid(prof, f.createIfcAxis2Placement3D(f.createIfcCartesianPoint((0.0, 0.0, 0.0))), f.createIfcDirection((0.0, 0.0, 1.0)), float(r.ceiling_height))
        rep = f.createIfcShapeRepresentation(body, "Body", "SweptSolid", [solid])
        sp.Representation = f.createIfcProductDefinitionShape(None, None, [rep])
        api.run("aggregate.assign_object", f, relating_object=storey, products=[sp])
        qto = api.run("pset.add_qto", f, product=sp, name="Qto_SpaceBaseQuantities")
        api.run("pset.edit_qto", f, qto=qto, properties={"NetFloorArea": round(polygon_area(r.polygon) / 1e6, 3)})
    with tempfile.NamedTemporaryFile(suffix=".ifc") as tmp:
        f.write(tmp.name)
        return Path(tmp.name).read_bytes()


# ------------------------------------------------------------------ import
ROOM_WORDS = {"living": ("living", "гост", "հյուրասենյակ"), "kitchen": ("kitchen", "кух", "խոհանոց"), "bedroom": ("bed", "спал", "ննջ"),
              "bathroom": ("bath", "ванн", "сануз", "լոգ", "սանհանգ"), "wc": ("wc", "toilet", "туал", "զուգ"), "hallway": ("hall", "corridor", "прих", "корид", "նախասենյակ"),
              "kids": ("kid", "child", "детск", "մանկ"), "balcony": ("balcon", "loggia", "балк", "лодж", "պատշգամբ"), "storage": ("storage", "клад", "պահեստ")}


def _room_type(name: str) -> str:
    low = (name or "").lower()
    return next((t for t, words in ROOM_WORDS.items() if any(w in low for w in words)), "living")



def from_ifc(data: bytes) -> tuple[Scene, dict]:
    import ifcopenshell
    import ifcopenshell.geom
    import ifcopenshell.util.element as uel
    import ifcopenshell.util.placement
    import ifcopenshell.util.unit as uunit
    from shapely.geometry import MultiPoint, Polygon
    from shapely.ops import unary_union

    with tempfile.NamedTemporaryFile(suffix=".ifc") as tmp:
        Path(tmp.name).write_bytes(data)
        f = ifcopenshell.open(tmp.name)
    to_mm = uunit.calculate_unit_scale(f) * 1000  # file length unit → mm
    st = ifcopenshell.geom.settings()
    st.set("use-world-coords", True)

    import ifcopenshell.util.shape as ushape

    faces_of: dict[int, np.ndarray] = {}

    def verts(el) -> np.ndarray | None:
        try:
            shape = ifcopenshell.geom.create_shape(st, el)
        except Exception:  # noqa: BLE001 - elements without body geometry are skipped
            return None
        faces_of[el.id()] = np.asarray(ushape.get_faces(shape.geometry), dtype=int).reshape(-1, 3)
        return np.asarray(ushape.get_vertices(shape.geometry), dtype=float).reshape(-1, 3) * 1000  # geometry engine works in metres

    scene = Scene(name="IFC import")
    stats = {"walls": 0, "openings": 0, "rooms": 0, "skipped": 0, "schema": f.schema, "unit_mm": to_mm}
    wall_axes = {}
    for i, el in enumerate(f.by_type("IfcWall"), start=1):
        v = verts(el)
        if v is None or len(v) < 4:
            stats["skipped"] += 1
            continue
        xy = v[:, :2]
        c = xy.mean(axis=0)
        cov = np.cov((xy - c).T)
        vals, vecs = np.linalg.eigh(cov)
        d = vecs[:, int(np.argmax(vals))]
        n = np.array([-d[1], d[0]])
        t = (xy - c) @ d
        s = (xy - c) @ n
        a, b = c + d * t.min() + n * (s.max() + s.min()) / 2, c + d * t.max() + n * (s.max() + s.min()) / 2
        thickness = float(s.max() - s.min())
        height = float(v[:, 2].max() - v[:, 2].min())
        pset = uel.get_pset(el, "Pset_WallCommon") or {}
        wid = f"W{i}"
        scene.walls.append(Wall(id=wid, a=(round(a[0], 1), round(-a[1], 1)), b=(round(b[0], 1), round(-b[1], 1)), thickness=round(thickness, 1), height=round(height, 1),
                                kind="exterior" if pset.get("IsExternal") else "interior", load_bearing=bool(pset.get("LoadBearing")), source="imported", confidence=0.9))
        wall_axes[el.id()] = (wid, a, b)
        stats["walls"] += 1
    for k, el in enumerate([*f.by_type("IfcDoor"), *f.by_type("IfcWindow")], start=1):
        host = None
        for rel in getattr(el, "FillsVoids", []) or []:
            voids = getattr(rel.RelatingOpeningElement, "VoidsElements", []) or []
            if voids and voids[0].RelatingBuildingElement.id() in wall_axes:
                host = wall_axes[voids[0].RelatingBuildingElement.id()]
        v = verts(el)
        if v is None:
            mat = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement) if el.ObjectPlacement else np.eye(4)
            centre = np.array([mat[0][3], mat[1][3]]) * to_mm
            zmin = mat[2][3] * to_mm
        else:
            centre = v[:, :2].mean(axis=0)
            zmin = float(v[:, 2].min())
        if host is None and wall_axes:  # nearest wall axis
            def dist(ax, centre=centre):
                _, a, b = ax
                ab = b - a
                tt = np.clip(((centre - a) @ ab) / (ab @ ab), 0, 1)
                return np.linalg.norm(a + ab * tt - centre)
            host = min(wall_axes.values(), key=dist)
        if host is None:
            stats["skipped"] += 1
            continue
        wid, a, b = host
        ab = b - a
        L = float(np.linalg.norm(ab))
        width = float((el.OverallWidth or 0) * to_mm) or (float(np.ptp((v[:, :2] - a) @ (ab / L))) if v is not None else 900.0)
        height = float((el.OverallHeight or 0) * to_mm) or (float(np.ptp(v[:, 2])) if v is not None else 2100.0)
        along = float((centre - a) @ (ab / L))
        is_window = el.is_a("IfcWindow")
        if v is not None:
            offset = along - width / 2
        else:  # placement point = the leaf's start corner; if the leaf runs against the imported axis, it is its end
            mat = ifcopenshell.util.placement.get_local_placement(el.ObjectPlacement)
            offset = along - width if float(np.array([mat[0][0], mat[1][0]]) @ ab) < 0 else along
        kinds = ("door", "window", "opening", "balcony_door", "entrance_door", "sliding_door")
        otype = el.ObjectType if el.ObjectType in kinds else ("window" if is_window else "door")
        scene.openings.append(Opening(id=f"O{k}", wall_id=wid, type=otype, offset=round(max(0.0, min(offset, L - width)), 1),
                                      width=round(width, 1), height=round(height, 1), sill=round(max(0.0, zmin), 1) if is_window else 0, source="imported", confidence=0.85))
        stats["openings"] += 1
    for j, el in enumerate(f.by_type("IfcSpace"), start=1):
        v = verts(el)
        if v is None:
            stats["skipped"] += 1
            continue
        tri = faces_of.get(el.id(), np.zeros((0, 3), dtype=int))
        polys = [Polygon(v[t][:, :2]) for t in tri if Polygon(v[t][:, :2]).area > 1]
        shape = unary_union(polys) if polys else MultiPoint(v[:, :2]).convex_hull
        if shape.geom_type == "MultiPolygon":
            shape = max(shape.geoms, key=lambda g: g.area)
        shape = shape.simplify(5)
        pts = [(round(x, 1), round(-y, 1)) for x, y in list(shape.exterior.coords)[:-1]]
        name = el.Name or el.LongName or f"Space {j}"
        scene.rooms.append(Room(id=f"R{j}", number=j, type=_room_type(f"{el.Name or ''} {el.LongName or ''}"), name=name, polygon=pts,
                                ceiling_height=round(float(np.ptp(v[:, 2])), 1) or 2700, source="imported", confidence=0.9))
        stats["rooms"] += 1
    if scene.walls:
        scene.ceiling_height = round(max(w.height or 0 for w in scene.walls), 1) or 2700
    return scene, stats
