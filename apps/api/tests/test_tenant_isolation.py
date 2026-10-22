"""P1-9: tenant isolation over the whole OpenAPI surface. A user of another bureau calls every
parameterised route with the victim's ids — both under the victim's project and under their own
project (child-object checks) — and must never get a 2xx or a 5xx. Request bodies are generated
from the OpenAPI schema so the access check is reached, not just body validation."""
import re

import pytest

from app import models as m
from app.db import SessionLocal
from app.main import app

pytestmark = pytest.mark.usefixtures("client")
PUBLIC_BY_TOKEN = ("/api/v1/client/{token}",)  # capability links: checked separately with a wrong token
DUMMY = "0" * 32


def _victim_ids(db) -> dict[str, str]:
    proj = db.query(m.Project).filter(m.Project.title.like("Демо%")).first()
    v = db.query(m.DesignVariant).filter_by(project_id=proj.id).first()
    created = []
    if not v or not v.current_version_id:
        v = m.DesignVariant(project_id=proj.id, key="iso", title="ISO", style="modern", tier="comfort")
        db.add(v)
        db.flush()
        ver = m.DesignVersion(variant_id=v.id, number=1, scene={})
        db.add(ver)
        db.flush()
        v.current_version_id = ver.id
        created.append(v)
    job = m.GenerationJob(project_id=proj.id, kind="pipeline", status="succeeded")
    com = m.Comment(project_id=proj.id, author_name="victim", body="secret")
    doc = m.Document(project_id=proj.id, kind="album", filename="a.pdf", storage_key=f"projects/{proj.id}/a.pdf", size=1)
    asset = m.SourceAsset(project_id=proj.id, kind="plan", filename="p.png", mime="image/png", storage_key=f"projects/{proj.id}/p.png", size=1, sha256="x")
    rfq = m.RFQ(project_id=proj.id, supplier_name="X", items=[], status="sent")
    owner = db.get(m.User, proj.owner_id)
    note = m.Notification(user_id=owner.id, kind="job_done", params={})
    sess = db.query(m.AuthSession).filter_by(user_id=owner.id).first()
    db.add_all([job, com, doc, asset, rfq, note])
    db.commit()
    created += [job, com, doc, asset, rfq, note]
    return created, {"pid": proj.id, "vid": v.id, "ver_id": v.current_version_id, "jid": job.id, "cid": com.id, "did": doc.id, "aid": asset.id,
            "rid": rfq.id, "oid": DUMMY, "nid": note.id, "sid": sess.id if sess else DUMMY, "key": doc.storage_key, "token": "not-a-token"}


def _value(schema: dict, comps: dict):
    if "$ref" in schema:
        return _value(comps[schema["$ref"].split("/")[-1]], comps)
    for k in ("anyOf", "oneOf", "allOf"):
        if k in schema:
            return _value(next((s for s in schema[k] if s.get("type") != "null"), schema[k][0]), comps)
    if "enum" in schema:
        return schema["enum"][0]
    if "default" in schema:
        return schema["default"]
    t = schema.get("type")
    if t == "object":
        return {p: _value(s, comps) for p, s in schema.get("properties", {}).items() if p in schema.get("required", [])}
    if t == "array":
        return [_value(schema.get("items", {}), comps) for _ in range(schema.get("minItems", 0))]
    if t in ("integer", "number"):
        return max(schema.get("minimum", 1), schema.get("exclusiveMinimum", 0) + 1, 1)
    if t == "boolean":
        return True
    if schema.get("pattern"):
        alt = re.fullmatch(r"\^\(([a-z_]+)(?:\|[a-z_|]+)?\)\$", schema["pattern"])  # ^(a|b|c)$ → a
        return alt.group(1) if alt else "x"
    return "x" * max(schema.get("minLength", 2), 2)


def _body(op: dict, comps: dict):
    content = (op.get("requestBody") or {}).get("content", {})
    if "application/json" in content:
        return {"json": _value(content["application/json"]["schema"], comps)}
    if "multipart/form-data" in content:
        return {"files": {"file": ("x.png", b"\x89PNG\r\n\x1a\n", "image/png")}, "data": {"kind": "plan"}}
    return {}


def _attacker(client):
    from tests.test_auth import STRONG, register

    email = "intruder@example.com"
    r = register(client, email)
    assert r.status_code in (200, 409), r.text
    client.cookies.clear()
    tok = client.post("/api/v1/auth/login", json={"email": email, "password": STRONG}).json().get("token")
    client.cookies.clear()
    h = {"Authorization": f"Bearer {tok}"}
    own = client.post("/api/v1/projects", headers=h, json={"title": "Intruder flat"})
    assert own.status_code == 200, own.text
    return h, own.json()["id"]


def test_no_route_leaks_across_tenants(client):
    h, own_pid = _attacker(client)
    with SessionLocal() as db:
        created, ids = _victim_ids(db)
    spec = app.openapi()
    comps = spec.get("components", {}).get("schemas", {})
    leaks, errors, checked = [], [], 0
    for path, ops in spec["paths"].items():
        params = re.findall(r"{(\w+)(?::\w+)?}", path)
        if not params or path.startswith(PUBLIC_BY_TOKEN):
            continue
        for method, op in ops.items():
            if path.startswith("/api/v1/admin/sources") or path.startswith("/api/v1/catalog/external/review"):
                continue  # platform-wide objects, guarded by role (asserted below)
            for pid in (ids["pid"], own_pid):
                if pid == own_pid and ("pid" not in params or len(params) == 1):
                    continue  # own project with only its own id is legitimate; with victim child ids it is not
                url = re.sub(r"{(\w+)(?::\w+)?}", lambda mm, pid=pid: pid if mm.group(1) == "pid" else ids.get(mm.group(1), DUMMY), path)
                query = {q["name"]: ids["ver_id"] if q["name"] in ("a", "b") else _value(q.get("schema", {}), comps)
                         for q in op.get("parameters", []) if q["in"] == "query" and q.get("required")}
                r = client.request(method.upper(), url, headers=h, params=query, **_body(op, comps))
                checked += 1
                if 200 <= r.status_code < 300:
                    leaks.append(f"{method.upper()} {path} [{'victim' if pid == ids['pid'] else 'own'} project] → {r.status_code}")
                elif r.status_code >= 500 or r.status_code == 422:
                    errors.append(f"{method.upper()} {path} → {r.status_code} {r.text[:120]}")
    assert checked > 60
    assert not leaks, "\n".join(leaks)
    assert not errors, "\n".join(errors)  # 422 would mean validation ran before (or instead of) the access check
    for path in ("/api/v1/admin/sources", "/api/v1/admin/jobs", "/api/v1/admin/audit"):
        assert client.get(path, headers=h).status_code == 403, path
    # moderation of platform-wide external records is a platform role, not any catalogue writer (suppliers)
    from tests.conftest import login

    sup = login(client, "supplier@forma.local")
    assert client.post(f"/api/v1/catalog/external/review/{DUMMY}", headers=sup, json={"decision": "approved"}).status_code == 403
    assert client.get("/api/v1/client/not-a-token").status_code == 404
    with SessionLocal() as db:  # leave the shared demo project as it was
        for obj in created:
            row = db.get(type(obj), obj.id)
            if row:
                db.delete(row)
        db.commit()
