"""Scene geometry, layout, rules, estimator, AI command parsing, exports, album."""
import json

import pytest

from app.ai import stub
from app.ai.orchestrator import Orchestrator
from app.ai.providers import LLMProvider, ProviderError, StubProvider
from app.album.draw import AlbumMeta
from app.album.sheets import AlbumBuilder
from app.catalog.candidates import Candidate
from app.catalog.demo_seed import DEMO_SUPPLIERS, demo_products
from app.catalog.discovery import build_needs
from app.design.engine import all_candidates, ground_engineering, select_products, variant_plans
from app.estimate.estimator import estimate
from app.exports.files import to_dxf, to_glb
from app.scene.demo import demo_base_scene
from app.scene.geometry import footprint, room_area_m2, scale_scene, wall_length
from app.scene.layout import apply_finishes, furnish
from app.scene.model import SceneObject
from app.scene.rules import run_rules, summarize


@pytest.fixture(scope="module")
def pool():
    out = {}
    for p in demo_products():
        for v in p["variants"]:
            c = Candidate(ref=f"pv:{v['sku']}", category=p["category"], name=p["name_ru"], supplier_name=p["supplier"], supplier_key=p["supplier"],
                          price_amd=v["price"], price_status=v["price_status"], unit=p.get("unit", "pcs"), package_coverage_m2=p.get("package_coverage_m2"),
                          waste_pct=p.get("waste_pct", 0), w=v.get("width_mm", 0), d=v.get("depth_mm", 0), h=v.get("height_mm", 0), color_hex=v["color_hex"],
                          styles=[v["style"]], tier=p["tier"], stock=v["stock_status"], sku=v["sku"], is_demo=True, item_type=p["item_type"], parametric=p.get("parametric", {}))
            out.setdefault(p["category"], []).append(c)
    return out


@pytest.fixture(scope="module")
def designed(pool):
    base = demo_base_scene()
    brief = {"budget_tier": "comfort"}
    plan = variant_plans(brief)[0]
    chosen, _ = select_products(build_needs(base, brief), pool, {}, style=plan.style, tier=plan.tier, concept=False)
    res = furnish(base, chosen, tier=plan.tier)
    apply_finishes(res.scene, chosen)
    ground_engineering(res.scene, chosen)
    sup = {s[0]: {"delivery": s[3], "installation": s[4], "is_demo": True} for s in DEMO_SUPPLIERS}
    return base, res, chosen, estimate(res.scene, all_candidates(chosen), sup)


def test_demo_geometry_areas():
    sc = demo_base_scene()
    total = sum(room_area_m2(r) for r in sc.rooms if r.type != "balcony")
    assert 60 < total < 70
    assert {r.type for r in sc.rooms} >= {"hallway", "bathroom", "bedroom", "kitchen_living", "kids"}


def test_control_dimension_rescale():
    sc = demo_base_scene()
    w = sc.wall("W1")
    s2 = scale_scene(sc, 9500 / wall_length(w))
    assert abs(wall_length(s2.wall("W1")) - 9500) < 1


def test_layout_has_no_blocking_issues(designed):
    _, res, _, _ = designed
    issues = run_rules(res.scene, {})
    s = summarize(issues)
    assert s["block"] == 0, [i for i in issues if i["severity"] == "block"]
    cats = {o.category for o in res.scene.objects}
    assert {"bed", "sofa", "kitchen_run", "fridge", "toilet", "vanity", "dining_table"} <= cats
    # every placed object is grounded on a catalogue reference
    assert all(o.product_variant_id for o in res.scene.objects)


def test_rules_detect_collision(designed):
    _, res, _, _ = designed
    sc = res.scene.model_copy(deep=True)
    sofa = next(o for o in sc.objects if o.category == "sofa")
    clone = SceneObject(**{**sofa.model_dump(), "id": "X1", "category": "armchair", "w": 800, "d": 800})
    sc.objects.append(clone)
    assert any(i["rule"] == "collisions" and i["severity"] == "block" for i in run_rules(sc, {}))


def test_engineering_derived(designed):
    _, res, _, _ = designed
    sc = res.scene
    assert len(sc.electrical) >= 20 and len(sc.lights) >= 15
    assert any(e.type == "cooktop" for e in sc.electrical)
    assert any(f.surface == "wet_walls" for f in sc.finishes)


def test_estimate_deterministic(designed):
    _, res, chosen, est = designed
    sup = {s[0]: {"delivery": s[3], "installation": s[4], "is_demo": True} for s in DEMO_SUPPLIERS}
    again = estimate(res.scene, all_candidates(chosen), sup)
    assert again["totals"] == est["totals"]
    assert est["totals"]["known"] == sum(ln["total"] for ln in est["lines"] if ln["total"] is not None)
    assert any("DEMO" in d for d in est["disclaimers"])


def test_quote_required_widens_range(designed):
    _, res, chosen, _ = designed
    cands = all_candidates(chosen)
    door = next(c for c in cands.values() if c.category == "door_interior")
    door.price_amd, door.price_status = None, "quote_required"
    est = estimate(res.scene, cands, {})
    assert est["totals"]["quote_required_lines"] >= 1
    assert est["totals"]["range_high"] > est["totals"]["range_low"]
    assert all(ln["total"] is None for ln in est["lines"] if ln.get("price_status") == "quote_required")


def test_stub_change_command_from_prompt_example():
    from app.ai.providers import LLMRequest

    cmd = "Сделай кухню светлее, замени диван на более компактный, добавь закрытый шкаф в коридоре и сократи бюджет на 700 000 AMD."
    req = LLMRequest(task="change_command", system="", user=json.dumps({"command": cmd, "room_types": ["kitchen_living", "hallway"]}), schema_name="", json_schema={})
    plan = stub.change_command(req)
    ops = {o["op"]: o for o in plan["operations"]}
    assert ops["lighter"]["room_type"] == "kitchen_living"
    assert ops["make_compact"]["category"] == "sofa"
    assert ops["add_object"]["category"] == "hallway_wardrobe" and ops["add_object"]["params"]["closed_storage"]
    assert ops["budget_delta"]["params"]["delta_amd"] == -700000


class _Broken(LLMProvider):
    name = "openai"

    @property
    def model(self):
        return "broken"

    def available(self):
        return True

    def complete_json(self, req):
        raise ProviderError("boom")


def test_orchestrator_falls_back_to_stub(monkeypatch):
    orch = Orchestrator(providers={"openai": _Broken(), "stub": StubProvider(stub.HANDLERS)})
    orch.sleep = lambda s: None
    monkeypatch.setattr(orch.s, "ai_default_provider", "auto")
    plan, provider = orch.run("change_command", {"command": "убери ковёр в спальне", "room_types": ["bedroom"]})
    assert provider == "stub"
    assert plan.operations[0].op == "remove_object"


def test_exports(designed):
    _, res, _, _ = designed
    dxf = to_dxf(res.scene, "demo")
    assert b"A-WALL" in dxf and b"I-FURN" in dxf
    glb = to_glb(res.scene)
    assert glb[:4] == b"glTF" and len(glb) > 10_000


def test_album_builds_all_sections(designed):
    base, res, _, est = designed
    meta = AlbumMeta(lang="ru", company="Studio", tagline="t", phone="", address="", email="", project_address="Demo", client="", designer="", accuracy_label="Verified Design")
    pdf, sheets = AlbumBuilder(res.scene, base, est, run_rules(res.scene, {}), meta, project={"confidence": 0.9}, variant={"title": "V", "style": "warm_minimal"},
                               viewer_url="http://x/client/t", approvals=[]).build()
    assert pdf[:4] == b"%PDF"
    assert {s["section"] for s in sheets} == {1, 2, 3, 4, 5}
    assert len(sheets) >= 30
    codes = [s["code"] for s in sheets]
    assert codes[0] == "ДП1.1" and "ДП2.2" in codes


def test_footprint_rotation():
    o = SceneObject(id="a", room_id="r", category="sofa", x=1000, y=1000, w=2000, d=1000, rotation=90)
    fp = footprint(o)
    assert (fp.w, fp.h) == (1000, 2000)
