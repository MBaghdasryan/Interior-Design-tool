"""Object-storage backup/restore through the storage abstraction (works for local and S3):

    python -m app.backup_storage export /backup/objects.tar.gz
    python -m app.backup_storage import /backup/objects.tar.gz      # restores missing/changed objects
    python -m app.backup_storage verify /backup/objects.tar.gz      # counts + sha256 manifest check

The archive contains every object plus MANIFEST.json (key, size, sha256)."""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile
import time

from .storage import get_storage, media_type


def export(path: str) -> dict:
    st = get_storage()
    manifest = []
    with tarfile.open(path, "w:gz") as tar:
        for key, _ in st.list(""):
            if key.startswith("cache/"):
                continue  # derived data (sitemap cache) is rebuilt automatically
            data = st.get(key)
            info = tarfile.TarInfo(f"objects/{key}")
            info.size, info.mtime = len(data), int(time.time())
            tar.addfile(info, io.BytesIO(data))
            manifest.append({"key": key, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        raw = json.dumps({"created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "objects": manifest}, indent=1).encode()
        info = tarfile.TarInfo("MANIFEST.json")
        info.size = len(raw)
        tar.addfile(info, io.BytesIO(raw))
    return {"objects": len(manifest), "bytes": sum(o["size"] for o in manifest)}


def _read(path: str):
    with tarfile.open(path, "r:gz") as tar:
        manifest = json.load(tar.extractfile("MANIFEST.json"))
        for o in manifest["objects"]:
            yield o, tar.extractfile(f"objects/{o['key']}").read()


def verify(path: str) -> dict:
    n = bad = 0
    for o, data in _read(path):
        n += 1
        bad += hashlib.sha256(data).hexdigest() != o["sha256"]
    return {"objects": n, "corrupt": bad}


def restore(path: str) -> dict:
    st = get_storage()
    put = skipped = 0
    for o, data in _read(path):
        if hashlib.sha256(data).hexdigest() != o["sha256"]:
            raise SystemExit(f"corrupt object in archive: {o['key']}")
        if st.exists(o["key"]) and hashlib.sha256(st.get(o["key"])).hexdigest() == o["sha256"]:
            skipped += 1
            continue
        st.put(o["key"], data, media_type(o["key"]))
        put += 1
    return {"restored": put, "unchanged": skipped}


if __name__ == "__main__":
    cmd, arg = sys.argv[1], sys.argv[2]
    print(json.dumps({"export": export, "import": restore, "verify": verify}[cmd](arg)))
