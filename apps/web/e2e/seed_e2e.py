"""Prepares a fresh stack for the E2E suites: generates variants for the demo project
(deterministic stub AI, cached/DEMO catalogue — no network) so every route has data.
Env: API (default http://localhost:8000)."""
import json
import os
import sys
import time
import urllib.request

API = os.environ.get("API", "http://localhost:8000") + "/api/v1"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    return json.loads(urllib.request.urlopen(req, timeout=600).read())


for _ in range(60):
    try:
        if call("GET", "/config"):
            break
    except Exception:  # noqa: BLE001
        time.sleep(3)
tok = call("POST", "/auth/login", {"email": "designer@forma.local", "password": "demo1234"})["token"]
demo = next(p for p in call("GET", "/projects", token=tok) if p["title"].startswith("Демо"))
if not call("GET", f"/projects/{demo['id']}/variants", token=tok):
    job = call("POST", f"/projects/{demo['id']}/generate", {"product_source": "external", "external_settings": {"sources": ["domus", "vlv"]}}, tok)
    for _ in range(200):
        job = call("GET", f"/projects/{demo['id']}/jobs/{job['id']}", token=tok)
        if job["status"] in ("succeeded", "failed"):
            break
        time.sleep(2)
    print("generation:", job["status"], job.get("error") or "")
    if job["status"] != "succeeded":
        sys.exit(1)
print("variants:", len(call("GET", f"/projects/{demo['id']}/variants", token=tok)))
