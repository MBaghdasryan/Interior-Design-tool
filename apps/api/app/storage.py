"""Object-storage abstraction: `LocalStorage` (development) and `S3Storage`
(S3 / MinIO, server-side encryption, presigned URLs) behind one interface.
Download links are always our own HMAC-signed `/api/v1/files/...` URLs; for S3 the
endpoint redirects to a short-lived presigned URL, so access control stays here."""
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

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
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

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def move(self, src: str, dst: str) -> None:
        d = self._path(dst)
        d.parent.mkdir(parents=True, exist_ok=True)
        self._path(src).replace(d)

    def list(self, prefix: str = "") -> list[tuple[str, float]]:
        """(key, mtime) of stored objects under `prefix` — used by the retention task."""
        base = self.root.resolve()
        start = self._path(prefix) if prefix else base
        if not start.exists():
            return []
        files = [start] if start.is_file() else [p for p in start.rglob("*") if p.is_file()]
        return [(str(p.relative_to(base)), p.stat().st_mtime) for p in files]

    def presigned_get(self, key: str, filename: str, inline: bool, ttl_s: int = 300) -> str | None:
        return None  # served directly by the API

    def presigned_put(self, key: str, content_type: str, ttl_s: int = 900) -> str | None:
        return None  # browser uploads go through the API (multipart)

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


MEDIA_TYPES = {"pdf": "application/pdf", "dxf": "application/dxf", "dwg": "image/vnd.dwg", "csv": "text/csv", "glb": "model/gltf-binary",
               "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "json": "application/json", "png": "image/png",
               "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp", "mp4": "video/mp4", "mov": "video/quicktime", "ifc": "application/x-step"}
INLINE_EXT = {"pdf", "png", "jpg", "jpeg", "webp", "mp4", "glb"}


def media_type(name: str) -> str:
    return MEDIA_TYPES.get(name.rsplit(".", 1)[-1].lower(), "application/octet-stream")


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


class S3Storage(LocalStorage):
    """S3 / MinIO driver. Objects are written with SSE (`S3_SSE`, default AES256)
    and their content type; presigned URLs are generated against the public endpoint
    (`S3_PUBLIC_ENDPOINT`), which may differ from the internal one (`S3_ENDPOINT`)."""

    def __init__(self, bucket: str, endpoint: str | None, public_endpoint: str | None, region: str, access_key: str | None, secret_key: str | None,
                 sse: str | None = "AES256", client=None, public_client=None):
        import boto3
        from botocore.config import Config

        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"}, retries={"max_attempts": 3})
        kw = {"region_name": region, "aws_access_key_id": access_key, "aws_secret_access_key": secret_key, "config": cfg}
        self.bucket, self.sse = bucket, (sse or None)
        self.s3 = client or boto3.client("s3", endpoint_url=endpoint, **kw)
        self.public = public_client or (boto3.client("s3", endpoint_url=public_endpoint, **kw) if public_endpoint and public_endpoint != endpoint else self.s3)

    def ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError

        try:
            self.s3.head_bucket(Bucket=self.bucket)
        except ClientError:
            self.s3.create_bucket(Bucket=self.bucket)

    def _check(self, key: str) -> str:
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise ValueError("invalid storage key")
        return key

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        extra = {"ServerSideEncryption": self.sse} if self.sse else {}
        self.s3.put_object(Bucket=self.bucket, Key=self._check(key), Body=data, ContentType=content_type, **extra)
        return key

    def get(self, key: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket, Key=self._check(key))["Body"].read()

    def path(self, key: str) -> Path:  # pragma: no cover - S3 objects have no local path
        raise NotImplementedError("S3Storage has no local paths; use presigned_get")

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.s3.head_object(Bucket=self.bucket, Key=self._check(key))
            return True
        except ClientError:
            return False

    def delete(self, key: str) -> None:
        self.s3.delete_object(Bucket=self.bucket, Key=self._check(key))

    def move(self, src: str, dst: str) -> None:
        extra = {"ServerSideEncryption": self.sse} if self.sse else {}
        self.s3.copy_object(Bucket=self.bucket, Key=self._check(dst), CopySource={"Bucket": self.bucket, "Key": self._check(src)}, **extra)
        self.delete(src)

    def list(self, prefix: str = "") -> list[tuple[str, float]]:
        out = []
        for page in self.s3.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
            out += [(o["Key"], o["LastModified"].timestamp()) for o in page.get("Contents", [])]
        return out

    def presigned_get(self, key: str, filename: str, inline: bool, ttl_s: int = 300) -> str | None:
        disp = f'{"inline" if inline else "attachment"}; filename="{filename}"'
        return self.public.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": self._check(key), "ResponseContentDisposition": disp},
                                                  ExpiresIn=ttl_s)

    def presigned_put(self, key: str, content_type: str, ttl_s: int = 900) -> str | None:
        params = {"Bucket": self.bucket, "Key": self._check(key), "ContentType": content_type}
        if self.sse:
            params["ServerSideEncryption"] = self.sse
        return self.public.generate_presigned_url("put_object", Params=params, ExpiresIn=ttl_s)


_storage: LocalStorage | None = None


def get_storage() -> LocalStorage:
    global _storage
    if _storage is None:
        s = get_settings()
        if s.storage_backend == "s3":
            _storage = S3Storage(s.s3_bucket, s.s3_endpoint, s.s3_public_endpoint, s.s3_region, s.s3_access_key, s.s3_secret_key, s.s3_sse)
        else:
            _storage = LocalStorage(s.storage_dir)
    return _storage
