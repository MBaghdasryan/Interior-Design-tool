"""Validation of supplier asset files by content, not by extension (P2-3).

kind         formats                                   limit
model3d      .glb (binary glTF 2.0), .gltf (JSON 2.0)  100 MB
texture      .png .jpg .jpeg .webp (≤ 8192 px)         30 MB   PBR channel guessed from the name
bim_cad      .ifc (ISO-10303-21) .dwg (AC10xx) .dxf .rvt   200 MB
certificate  .pdf                                      20 MB
"""
from __future__ import annotations

import io
import json
import struct
from pathlib import Path

LIMITS = {"model3d": 100 << 20, "texture": 30 << 20, "bim_cad": 200 << 20, "certificate": 20 << 20}
EXTS = {"model3d": {".glb", ".gltf"}, "texture": {".png", ".jpg", ".jpeg", ".webp"}, "bim_cad": {".ifc", ".dwg", ".dxf", ".rvt"}, "certificate": {".pdf"}}
MIME = {".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".ifc": "application/x-step", ".dwg": "image/vnd.dwg", ".dxf": "application/dxf", ".rvt": "application/octet-stream", ".pdf": "application/pdf"}
PBR = (("basecolor", "base_color"), ("albedo", "base_color"), ("diffuse", "base_color"), ("normal", "normal"), ("rough", "roughness"),
       ("metal", "metallic"), ("ao", "ambient_occlusion"), ("occlusion", "ambient_occlusion"), ("height", "height"), ("disp", "height"))


class AssetInvalid(ValueError):
    """`code` is a stable reason shown to the supplier (i18n: asset.<code>)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _glb(data: bytes) -> dict:
    if len(data) < 20 or data[:4] != b"glTF":
        raise AssetInvalid("not_glb")
    version, length = struct.unpack_from("<II", data, 4)
    if version != 2:
        raise AssetInvalid("gltf_version")
    if length != len(data):
        raise AssetInvalid("glb_truncated")
    chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:  # "JSON"
        raise AssetInvalid("glb_no_json")
    return _gltf_meta(json.loads(data[20:20 + chunk_len]))


def _gltf_meta(doc: dict) -> dict:
    if str(doc.get("asset", {}).get("version", "")).split(".")[0] != "2":
        raise AssetInvalid("gltf_version")
    if not doc.get("meshes"):
        raise AssetInvalid("gltf_no_mesh")
    return {"format": "gltf2", "meshes": len(doc["meshes"]), "materials": len(doc.get("materials", [])), "textures": len(doc.get("textures", [])),
            "generator": str(doc.get("asset", {}).get("generator", ""))[:80]}


def validate(kind: str, filename: str, data: bytes) -> tuple[str, dict]:
    """→ (mime, meta). Raises AssetInvalid."""
    if kind not in LIMITS:
        raise AssetInvalid("kind")
    ext = Path(filename).suffix.lower()
    if ext not in EXTS[kind]:
        raise AssetInvalid("extension")
    if not data:
        raise AssetInvalid("empty")
    if len(data) > LIMITS[kind]:
        raise AssetInvalid("too_large")
    meta: dict = {"ext": ext}
    if ext == ".glb":
        meta |= _glb(data)
    elif ext == ".gltf":
        try:
            meta |= _gltf_meta(json.loads(data))
        except (ValueError, UnicodeDecodeError):
            raise AssetInvalid("not_gltf") from None
    elif kind == "texture":
        from PIL import Image

        try:
            im = Image.open(io.BytesIO(data))
            im.verify()
        except Exception:  # noqa: BLE001 - any decoder error means "not an image"
            raise AssetInvalid("not_image") from None
        if max(im.size) > 8192:
            raise AssetInvalid("image_too_big")
        name = Path(filename).stem.lower()
        meta |= {"width": im.size[0], "height": im.size[1], "format": im.format, "pbr_channel": next((ch for k, ch in PBR if k in name), "base_color")}
    elif ext == ".pdf":
        if not data.startswith(b"%PDF"):
            raise AssetInvalid("not_pdf")
    elif ext == ".ifc":
        if not data.lstrip()[:12] == b"ISO-10303-21":
            raise AssetInvalid("not_ifc")
        meta["schema"] = next((s for s in ("IFC4X3", "IFC4", "IFC2X3") if s.encode() in data[:4000]), "unknown")
    elif ext == ".dwg":
        if not data.startswith(b"AC10"):
            raise AssetInvalid("not_dwg")
        meta["dwg_version"] = data[:6].decode("ascii", "replace")
    elif ext == ".dxf":
        if b"SECTION" not in data[:2000]:
            raise AssetInvalid("not_dxf")
    elif ext == ".rvt":
        if not data.startswith(b"\xd0\xcf\x11\xe0"):  # Revit files are OLE compound documents
            raise AssetInvalid("not_rvt")
    return MIME[ext], meta
