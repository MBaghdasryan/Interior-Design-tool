"""Object-storage abstraction. Local filesystem driver for development; an S3
driver plugs in behind the same interface (see docs/ARCHITECTURE.md)."""
from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

from .config import get_settings

ALLOWED_UPLOADS = {
    "image/jpeg": "photo", "image/png": "photo", "image/webp": "photo", "image/heic": "photo",
    "video/mp4": "video", "video/quicktime": "video",
    "application/pdf": "plan_pdf",
    "image/vnd.dwg": "dwg", "application/acad": "dwg", "application/x-dwg": "dwg",
    "image/vnd.dxf": "dxf", "application/dxf": "dxf",
    "application/x-step": "ifc", "application/ifc": "ifc",
    "application/octet-stream": "binary",
}
EXT_KIND = {".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".webp": "photo", ".heic": "photo", ".mp4": "video", ".mov": "video",
            ".pdf": "plan_pdf", ".dwg": "dwg", ".dxf": "dxf", ".ifc": "ifc", ".rvt": "rvt", ".usdz": "lidar", ".obj": "lidar"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAGIC = {b"%PDF": "plan_pdf", b"\x89PNG": "photo", b"\xff\xd8\xff": "photo", b"AC10": "dwg", b"ISO-10303-21": "ifc"}


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def path(self, key: str) -> Path:
        return self._path(key)

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def signed_url(self, key: str, ttl_s: int = 3600) -> str:
        """Signed, expiring media URL (served by /api/v1/files/{key})."""
        s = get_settings()
        exp = int(time.time()) + ttl_s
        sig = hmac.new(s.secret_key.encode(), f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"{s.api_base_url}/api/v1/files/{key}?exp={exp}&sig={sig}"

    @staticmethod
    def verify(key: str, exp: int, sig: str) -> bool:
        s = get_settings()
        if exp < time.time():
            return False
        good = hmac.new(s.secret_key.encode(), f"{key}:{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(good, sig)


def detect_kind(filename: str, mime: str, head: bytes) -> str | None:
    ext = Path(filename).suffix.lower()
    kind = EXT_KIND.get(ext)
    if kind is None:
        return None
    sniffed = next((k for magic, k in MAGIC.items() if head.startswith(magic)), None)
    if sniffed and sniffed != kind:
        return None  # content does not match the extension (e.g. a PNG renamed to .pdf)
    if kind == "photo" and filename.lower().startswith(("plan", "план", "հատակագիծ")):
        return "plan_image"
    return kind


def scan_for_malware(data: bytes) -> bool:
    """Malware-scanning hook. Wire ClamAV (clamd INSTREAM) here in production.
    Development: rejects the EICAR test signature only."""
    return b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" not in data


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        _storage = LocalStorage(get_settings().storage_dir)
    return _storage
