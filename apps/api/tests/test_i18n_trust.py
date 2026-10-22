"""Localisation contract (stable error codes, coded rule/step messages, locale
persistence) and the three reliability levels."""
import re
from pathlib import Path

from tests.conftest import login

WEB_DICT = Path(__file__).resolve().parents[2] / "web" / "src" / "i18n" / "dict" / "system.ts"


def test_error_codes_are_stable_and_translated(client, designer):
    r = client.post("/api/v1/auth/login", json={"email": "designer@forma.local", "password": "wrong"})
    assert r.status_code == 401 and r.json()["code"] == "auth.bad_credentials"
    r = client.get("/api/v1/projects/does-not-exist", headers=designer)
    assert r.status_code == 404 and r.json()["code"] == "project.not_found"
    r = client.get("/api/v1/projects")
    assert r.json()["code"] == "auth.required"
    r = client.patch("/api/v1/auth/me", headers=designer, json={"locale": "de"})
    assert r.status_code == 422 and r.json()["code"] == "validation"


def test_every_server_error_code_has_web_translations():
    from app.errors import MESSAGES

    if not WEB_DICT.exists():  # web sources not mounted in this environment
        return
    text = WEB_DICT.read_text(encoding="utf-8")
    keys = set(re.findall(r'"errors\.([a-z_.]+)":', text))
    assert set(MESSAGES) <= keys, set(MESSAGES) - keys


def test_locale_is_persisted_in_profile(client):
    h = login(client, "client@forma.local")
    assert client.patch("/api/v1/auth/me", headers=h, json={"locale": "hy"}).json()["locale"] == "hy"
    # a new session (new token) sees the saved language
    assert client.get("/api/v1/auth/me", headers=login(client, "client@forma.local")).json()["locale"] == "hy"


def test_rules_and_steps_carry_codes(client, designer):
    pid = next(p for p in client.get("/api/v1/projects", headers=designer).json() if p["title"].startswith("Демо"))["id"]
    variants = client.get(f"/api/v1/projects/{pid}/variants", headers=designer).json()
    if not variants:  # flow test creates them; generate here when run in isolation
        client.post(f"/api/v1/projects/{pid}/geometry/control-dimension", headers=designer, json={"wall_id": "W1", "measured_mm": 9600})
        assert client.post(f"/api/v1/projects/{pid}/geometry/confirm", headers=designer).status_code == 200
        assert client.post(f"/api/v1/projects/{pid}/generate", headers=designer, json={"product_source": "external", "external_settings": {"sources": ["domus"]}}).status_code == 200
        variants = client.get(f"/api/v1/projects/{pid}/variants", headers=designer).json()
    v = client.get(f"/api/v1/projects/{pid}/variants/{variants[0]['id']}", headers=designer).json()
    issues = v["version"]["issues"]
    assert issues and all(i["code"] for i in issues)
    est = v["version"]["estimate"]
    assert {n["code"] for n in est["notices"]} >= {"prices_public_sources", "engineering_preliminary"}
    jobs = client.get(f"/api/v1/projects/{pid}/jobs?kind=pipeline", headers=designer).json()
    steps = {s["key"]: s for s in jobs[0]["steps"]}
    assert steps["rooms"]["params"]["n"] >= 5 and "area" in steps["rooms"]["params"]


def test_trust_levels_checklist_and_gating(client, designer):
    h = designer
    proj = client.post("/api/v1/projects", headers=h, json={"title": "Trust test"}).json()
    pid = proj["id"]
    tr = client.get(f"/api/v1/projects/{pid}/trust", headers=h).json()
    assert tr["level"] == "concept" and tr["next"] == "verified"
    assert tr["exports"]["dwg"] == "blocked" and "engineering_preliminary" in tr["limitations"]
    r = client.post(f"/api/v1/projects/{pid}/trust/advance", headers=h)
    assert r.status_code == 409 and r.json()["code"] == "trust.requirements_missing"
    assert "control_dimension" in r.json()["params"]["missing"]
    # demo geometry + control dimension + confirmation → verified
    client.post(f"/api/v1/projects/{pid}/use-demo-geometry", headers=h)
    client.post(f"/api/v1/projects/{pid}/geometry/control-dimension", headers=h, json={"wall_id": "W1", "measured_mm": 9600})
    client.post(f"/api/v1/projects/{pid}/geometry/confirm", headers=h)
    tr = client.get(f"/api/v1/projects/{pid}/trust", headers=h).json()
    assert tr["level"] == "verified" and tr["next"] == "production"
    # production needs a specialist sign-off: designers may not sign off
    assert client.post(f"/api/v1/projects/{pid}/trust/signoff", headers=h, json={}).status_code == 403
    v = login(client, "verifier@forma.local")
    assert client.post(f"/api/v1/projects/{pid}/trust/signoff", headers=v, json={"note": "site survey"}).status_code == 200
    tr = client.get(f"/api/v1/projects/{pid}/trust", headers=h).json()
    assert next(c for c in tr["checklist"] if c["code"] == "specialist_signoff")["ok"]


def test_shared_dictionary_covers_server_codes():
    """Codes the server emits (rules, notices, works, groups) must exist in i18n_shared.json in all three languages."""
    import json
    import re
    from pathlib import Path

    from app.estimate.estimator import DEFAULT_WORK_RATES

    app_dir = Path(__file__).resolve().parent.parent / "app"
    shared = json.loads((app_dir / "i18n_shared.json").read_text(encoding="utf-8"))
    rule_codes = set(re.findall(r'RuleResult\([^\n]*?, "(\w+)", \{', (app_dir / "scene" / "rules.py").read_text(encoding="utf-8")))
    notice_codes = set(re.findall(r'\{"code": "(\w+)"', (app_dir / "estimate" / "estimator.py").read_text(encoding="utf-8")))
    assert len(rule_codes) >= 10 and len(notice_codes) == 5
    need = [f"rules.{c}" for c in rule_codes] + [f"notice.{c}" for c in notice_codes] + [f"works.{c}" for c in DEFAULT_WORK_RATES]
    need += [f"enum.group.{g}" for g in ("furniture", "lighting", "plumbing", "finishing", "doors", "appliances", "decor", "custom", "works", "delivery", "installation", "contingency")]
    missing = [k for k in need if k not in shared or not all(shared[k].get(lang) for lang in ("hy", "ru", "en"))]
    assert not missing, missing


def test_n99_pilot_workspace(client, designer):
    """N99 is created empty (no fake inputs); manual items can be ticked; it is never 'validated' without real data."""
    from app.db import SessionLocal
    from app.pilot import ensure_workspace

    with SessionLocal() as db:
        proj, created = ensure_workspace(db)
        again, created2 = ensure_workspace(db)
        assert again.id == proj.id and not created2
    st = client.get(f"/api/v1/projects/{proj.id}/pilot", headers=designer).json()
    assert st["code"] == "N99" and not st["validated"] and st["progress"] == 0
    assert [s["code"] for s in st["flow"]][-1] == "specialist_qa"
    st = client.post(f"/api/v1/projects/{proj.id}/pilot/mark", headers=designer, json={"code": "family_scenarios", "ok": True}).json()
    assert next(i for i in st["manifest"] if i["code"] == "family_scenarios")["ok"] and not st["validated"]
    # auto items cannot be ticked by hand
    assert client.post(f"/api/v1/projects/{proj.id}/pilot/mark", headers=designer, json={"code": "plan_and_dims", "ok": True}).status_code == 422
    # a non-pilot project has no pilot endpoint
    demo = next(p for p in client.get("/api/v1/projects", headers=designer).json() if p["title"].startswith("Демо"))
    assert client.get(f"/api/v1/projects/{demo['id']}/pilot", headers=designer).status_code == 404


def test_n99_manifest_upload_and_report(client, designer):
    """Files are filed under manifest items; the report (JSON/PDF in 3 languages) states the honest status."""
    import io

    import pymupdf

    from app.db import SessionLocal
    from app.pilot import ensure_workspace

    with SessionLocal() as db:
        proj, _ = ensure_workspace(db)
    pid = proj.id
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 4000
    r = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("living.png", io.BytesIO(png), "image/png")}, data={"manifest_item": "photos_video"})
    assert r.status_code == 200, r.text
    bad = client.post(f"/api/v1/projects/{pid}/assets", headers=designer, files={"file": ("x.png", io.BytesIO(png + b"1"), "image/png")}, data={"manifest_item": "nonsense"})
    assert bad.status_code == 422
    st = client.get(f"/api/v1/projects/{pid}/pilot", headers=designer).json()
    item = next(i for i in st["manifest"] if i["code"] == "photos_video")
    assert item["files"] == 1 and item["ok"]  # auto item: a photo exists now
    rep = client.get(f"/api/v1/projects/{pid}/pilot/report", headers=designer).json()
    assert rep["validated"] is False and rep["statement"] == "real_world_validation_pending"
    assert next(i for i in rep["manifest"] if i["code"] == "photos_video")["file_names"] == ["living.png"]
    for lang, word in (("hy", "Պիլոտի"), ("ru", "Отчёт о валидации"), ("en", "Pilot validation report")):
        pdf = client.get(f"/api/v1/projects/{pid}/pilot/report?format=pdf&lang={lang}", headers=designer)
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
        doc = pymupdf.open(stream=pdf.content, filetype="pdf")
        assert word in doc[0].get_text()
        assert all(f[1] != "n/a" for page in doc for f in page.get_fonts())  # fonts embedded
