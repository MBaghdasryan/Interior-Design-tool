"""E2E (P2-3): a store registers, fills the partner profile, accepts the agreement, uploads a GLB
model (3D preview renders) and a PBR texture; submitting without a catalogue is refused honestly.
Run against the compose stack."""
import json
import os
import struct
import sys
import time

from playwright.sync_api import sync_playwright

B = os.environ.get("BASE", "http://localhost:8085")
OUT = os.environ.get("OUT", "/tmp")
EMAIL = f"store.{int(time.time())}@example.com"
failures: list[str] = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def glb() -> bytes:
    # one triangle, so the preview has something to draw
    pos = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    doc = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
           "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}], "buffers": [{"byteLength": len(pos)}],
           "bufferViews": [{"buffer": 0, "byteOffset": 0, "byteLength": len(pos)}],
           "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    total = 12 + 8 + len(js) + 8 + len(pos)
    return b"glTF" + struct.pack("<II", 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(pos), 0x004E4942) + pos


with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 1366, "height": 900})
    pg = ctx.new_page()
    errs: list[str] = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    r = ctx.request.post(B + "/api/v1/auth/register", data={"email": EMAIL, "password": "E2e-Strong-Pass-1", "name": "Store Owner", "org_name": "E2E Store",
                                                          "org_kind": "supplier", "locale": "en", "accept_terms": True})
    check(r.status == 200, "store registered")
    csrf = next(c["value"] for c in ctx.cookies() if c["name"] == "forma_csrf")
    ctx.request.post(B + "/api/v1/auth/onboarding", data={"done": True}, headers={"X-CSRF-Token": csrf})  # account wizard (covered by auth_e2e)
    pg.goto(B + "/app/supplier")
    pg.wait_for_selector("#onb-h")
    check("Not started" in pg.inner_text("body"), "onboarding starts at «not started»")
    pg.get_by_role("textbox", name="Organisation name").fill("E2E Store")
    pg.get_by_role("button", name="Save profile").click()
    pg.wait_for_selector("text=Awaiting verification")
    check(True, "profile saved → pending verification")
    pg.wait_for_selector("[role=tablist]")  # with a supplier row the full cabinet replaces the onboarding-only view
    pg.get_by_role("checkbox").check()
    pg.get_by_role("button", name="Accept", exact=True).click()
    pg.wait_for_timeout(800)
    pg.get_by_role("button", name="Submit for verification").click()
    pg.wait_for_timeout(800)
    check("Onboarding is incomplete" in pg.inner_text("body"), "submit without a catalogue is refused")
    pg.goto(B + "/app/supplier")  # with a supplier row the full cabinet renders
    pg.get_by_role("tab", name="Feed, files and verification").click()
    pg.wait_for_selector("#sas-h")
    pg.locator("input[type=file][aria-label='Upload']").set_input_files({"name": "chair.glb", "mimeType": "model/gltf-binary", "buffer": glb()})
    pg.wait_for_selector("text=chair.glb")
    pg.get_by_role("button", name="3D preview").click()
    pg.wait_for_selector(".modal canvas", timeout=15000)
    check(pg.locator(".modal canvas").count() == 1, "GLB 3D preview renders")
    pg.screenshot(path=f"{OUT}/supplier_assets.png")
    pg.keyboard.press("Escape")
    pg.locator(".modal").click(position={"x": 5, "y": 5})
    pg.get_by_role("combobox", name="File type").select_option("model3d")
    pg.locator("input[type=file][aria-label='Upload']").set_input_files({"name": "fake.glb", "mimeType": "model/gltf-binary", "buffer": b"\x89PNG not a model"})
    pg.wait_for_timeout(800)
    check("This is not a binary glTF" in pg.inner_text("body"), "a renamed file is rejected by content")
    check(not errs, f"no JS errors {errs[:2]}")
    b.close()
print("FAILURES:", failures) if failures else print("ALL PASS")
sys.exit(1 if failures else 0)
