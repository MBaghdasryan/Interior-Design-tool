"""Autodesk Platform Services (APS) client.

Used for:
* importing professional source files (DWG/DXF/RVT/IFC) — OSS upload → Model
  Derivative translation (SVF2 for the APS Viewer) → property extraction (rooms,
  areas, levels) to seed the BuildingGraph;
* producing native DWG from our generated DXF — Design Automation for AutoCAD;
* viewing both in the browser with the APS Viewer (read-only viewer token).

Secrets stay on the server; the browser only receives a short-lived
`viewables:read` token."""
from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass

import httpx

from ..config import Settings, get_settings


class ApsError(Exception):
    pass


class ApsDisabled(ApsError):
    pass


def urn_of(object_id: str) -> str:
    return base64.urlsafe_b64encode(object_id.encode()).decode().rstrip("=")


@dataclass
class _Token:
    value: str
    expires_at: float


class ApsClient:
    INTERNAL_SCOPES = "data:read data:write data:create bucket:create bucket:read code:all"

    def __init__(self, settings: Settings | None = None, http: httpx.Client | None = None):
        self.s = settings or get_settings()
        self.http = http or httpx.Client(timeout=60.0)
        self._tokens: dict[str, _Token] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------ auth
    @property
    def enabled(self) -> bool:
        return self.s.aps_enabled

    def _require(self):
        if not self.enabled:
            raise ApsDisabled("APS не настроен: задайте APS_CLIENT_ID и APS_CLIENT_SECRET")

    def token(self, scopes: str | None = None) -> str:
        self._require()
        scopes = scopes or self.INTERNAL_SCOPES
        with self._lock:
            t = self._tokens.get(scopes)
            if t and t.expires_at - 60 > time.time():
                return t.value
            basic = base64.b64encode(f"{self.s.aps_client_id}:{self.s.aps_client_secret}".encode()).decode()
            r = self.http.post(f"{self.s.aps_base_url}/authentication/v2/token",
                               headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
                               data={"grant_type": "client_credentials", "scope": scopes})
            if r.status_code != 200:
                raise ApsError(f"APS auth failed {r.status_code}: {r.text[:200]}")
            j = r.json()
            self._tokens[scopes] = _Token(j["access_token"], time.time() + int(j.get("expires_in", 3600)))
            return j["access_token"]

    def viewer_token(self) -> dict:
        tok = self.token("viewables:read")
        return {"access_token": tok, "expires_in": int(self._tokens["viewables:read"].expires_at - time.time())}

    def _h(self, extra: dict | None = None) -> dict:
        return {"Authorization": f"Bearer {self.token()}", **(extra or {})}

    # ------------------------------------------------------------ OSS
    def ensure_bucket(self, bucket: str | None = None) -> str:
        bucket = bucket or self.s.aps_bucket
        r = self.http.post(f"{self.s.aps_base_url}/oss/v2/buckets", headers=self._h({"x-ads-region": self.s.aps_region}),
                           json={"bucketKey": bucket, "policyKey": "persistent"})
        if r.status_code not in (200, 409):
            raise ApsError(f"bucket create failed {r.status_code}: {r.text[:200]}")
        return bucket

    def signed_upload(self, object_key: str, bucket: str | None = None, minutes: int = 60) -> tuple[str, str]:
        bucket = bucket or self.s.aps_bucket
        r = self.http.get(f"{self.s.aps_base_url}/oss/v2/buckets/{bucket}/objects/{object_key}/signeds3upload",
                          params={"parts": 1, "minutesExpiration": minutes}, headers=self._h())
        if r.status_code != 200:
            raise ApsError(f"signeds3upload failed {r.status_code}: {r.text[:200]}")
        j = r.json()
        return j["urls"][0], j["uploadKey"]

    def complete_upload(self, object_key: str, upload_key: str, bucket: str | None = None) -> dict:
        bucket = bucket or self.s.aps_bucket
        r = self.http.post(f"{self.s.aps_base_url}/oss/v2/buckets/{bucket}/objects/{object_key}/signeds3upload",
                           headers=self._h({"Content-Type": "application/json"}), json={"uploadKey": upload_key})
        if r.status_code != 200:
            raise ApsError(f"complete upload failed {r.status_code}: {r.text[:200]}")
        return r.json()

    def upload(self, object_key: str, data: bytes, bucket: str | None = None) -> dict:
        bucket = self.ensure_bucket(bucket)
        url, key = self.signed_upload(object_key, bucket)
        put = self.http.put(url, content=data)
        if put.status_code not in (200, 201):
            raise ApsError(f"S3 PUT failed {put.status_code}")
        obj = self.complete_upload(object_key, key, bucket)
        return {"objectId": obj["objectId"], "objectKey": object_key, "bucketKey": bucket, "urn": urn_of(obj["objectId"]), "size": obj.get("size")}

    def signed_download(self, object_key: str, bucket: str | None = None, minutes: int = 60) -> str:
        bucket = bucket or self.s.aps_bucket
        r = self.http.get(f"{self.s.aps_base_url}/oss/v2/buckets/{bucket}/objects/{object_key}/signeds3download",
                          params={"minutesExpiration": minutes}, headers=self._h())
        if r.status_code != 200:
            raise ApsError(f"signeds3download failed {r.status_code}: {r.text[:200]}")
        return r.json()["url"]

    # ------------------------------------------------------------ Model Derivative
    def translate(self, urn: str, root_filename: str | None = None, views=("2d", "3d")) -> dict:
        body = {"input": {"urn": urn}, "output": {"destination": {"region": self.s.aps_region.lower()}, "formats": [{"type": "svf2", "views": list(views)}]}}
        if root_filename:
            body["input"].update({"compressedUrn": True, "rootFilename": root_filename})
        r = self.http.post(f"{self.s.aps_base_url}/modelderivative/v2/designdata/job", headers=self._h({"x-ads-force": "true"}), json=body)
        if r.status_code not in (200, 201):
            raise ApsError(f"translate failed {r.status_code}: {r.text[:300]}")
        return r.json()

    def manifest(self, urn: str) -> dict:
        r = self.http.get(f"{self.s.aps_base_url}/modelderivative/v2/designdata/{urn}/manifest", headers=self._h())
        if r.status_code == 404:
            return {"status": "pending", "progress": "0%"}
        if r.status_code != 200:
            raise ApsError(f"manifest failed {r.status_code}")
        return r.json()

    def metadata(self, urn: str) -> list[dict]:
        r = self.http.get(f"{self.s.aps_base_url}/modelderivative/v2/designdata/{urn}/metadata", headers=self._h())
        if r.status_code != 200:
            raise ApsError(f"metadata failed {r.status_code}")
        return r.json().get("data", {}).get("metadata", [])

    def properties(self, urn: str, guid: str) -> list[dict]:
        for _ in range(10):
            r = self.http.get(f"{self.s.aps_base_url}/modelderivative/v2/designdata/{urn}/metadata/{guid}/properties", headers=self._h())
            if r.status_code == 202:  # still being processed
                time.sleep(3)
                continue
            if r.status_code != 200:
                raise ApsError(f"properties failed {r.status_code}")
            return r.json().get("data", {}).get("collection", [])
        raise ApsError("properties not ready")

    def wait_translation(self, urn: str, timeout_s: int = 900, poll_s: float = 5.0, on_progress=None) -> dict:
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            m = self.manifest(urn)
            if on_progress:
                on_progress(m.get("progress", ""))
            if m.get("status") in ("success", "failed", "timeout"):
                return m
            time.sleep(poll_s)
        raise ApsError("translation timeout")

    # ------------------------------------------------------------ Design Automation (AutoCAD)
    @property
    def da_base(self) -> str:
        return f"{self.s.aps_base_url}/da/us-east/v3"

    @property
    def da_activity_id(self) -> str:
        nick = self.s.aps_da_nickname or self.s.aps_client_id
        return f"{nick}.FormaDxfToDwg+{self.s.aps_da_activity_alias}"

    def workitem_dxf_to_dwg(self, input_url: str, output_url: str) -> dict:
        body = {"activityId": self.da_activity_id,
                "arguments": {"inputFile": {"url": input_url, "verb": "get", "localName": "input.dxf"},
                              "outputDwg": {"url": output_url, "verb": "put"}}}
        r = self.http.post(f"{self.da_base}/workitems", headers=self._h({"Content-Type": "application/json"}), json=body)
        if r.status_code not in (200, 201):
            raise ApsError(f"workitem failed {r.status_code}: {r.text[:300]}")
        return r.json()

    def workitem_status(self, workitem_id: str) -> dict:
        r = self.http.get(f"{self.da_base}/workitems/{workitem_id}", headers=self._h())
        if r.status_code != 200:
            raise ApsError(f"workitem status failed {r.status_code}")
        return r.json()

    def activity_definition(self) -> dict:
        script = '(command "_.ZOOM" "_E")\n(command "_.SAVEAS" "2018" (strcat (getvar "DWGPREFIX") "result.dwg"))\n'
        return {
            "id": "FormaDxfToDwg",
            "commandLine": ['$(engine.path)\\accoreconsole.exe /i "$(args[inputFile].path)" /s "$(settings[script].path)"'],
            "parameters": {
                "inputFile": {"verb": "get", "description": "DXF exported by Renovara", "localName": "input.dxf", "required": True},
                "outputDwg": {"verb": "put", "description": "Converted DWG", "localName": "result.dwg", "required": True},
            },
            "engine": self.s.aps_da_engine,
            "settings": {"script": {"value": script}},
            "description": "Renovara — DXF to DWG (AutoCAD core console)",
        }

    def setup_design_automation(self) -> dict:
        """Idempotent: creates (or versions) the activity and points the alias at it."""
        base = self.da_base
        out = {}
        r = self.http.post(f"{base}/activities", headers=self._h({"Content-Type": "application/json"}), json=self.activity_definition())
        if r.status_code == 409:
            d = self.activity_definition()
            d.pop("id")
            r = self.http.post(f"{base}/activities/FormaDxfToDwg/versions", headers=self._h({"Content-Type": "application/json"}), json=d)
        if r.status_code not in (200, 201):
            raise ApsError(f"activity create failed {r.status_code}: {r.text[:300]}")
        version = r.json().get("version", 1)
        out["activity_version"] = version
        alias = self.s.aps_da_activity_alias
        r = self.http.post(f"{base}/activities/FormaDxfToDwg/aliases", headers=self._h({"Content-Type": "application/json"}), json={"id": alias, "version": version})
        if r.status_code == 409:
            r = self.http.patch(f"{base}/activities/FormaDxfToDwg/aliases/{alias}", headers=self._h({"Content-Type": "application/json"}), json={"version": version})
        if r.status_code not in (200, 201):
            raise ApsError(f"alias failed {r.status_code}: {r.text[:300]}")
        out["activity_id"] = self.da_activity_id
        return out


def extract_rooms(properties: list[dict]) -> list[dict]:
    """Pulls room/space names and areas from Model Derivative properties (Revit
    'Rooms', IFC 'IfcSpace', AutoCAD Architecture spaces). Areas are returned in m²."""
    rooms = []
    for obj in properties:
        props = obj.get("properties", {})
        flat = {k.lower(): v for grp in props.values() if isinstance(grp, dict) for k, v in grp.items()}
        name = obj.get("name", "")
        category = str(flat.get("category", "")).lower()
        if not ("room" in category or "ifcspace" in category or name.lower().startswith(("room", "ifcspace")) or "space" in category):
            continue
        area_raw = flat.get("area") or flat.get("netfloorarea") or flat.get("grossfloorarea")
        area = None
        if area_raw is not None:
            try:
                txt = str(area_raw).replace(",", ".").split()[0]
                area = float(txt)
                if "ft" in str(area_raw):
                    area *= 0.092903
            except ValueError:
                area = None
        rooms.append({"name": flat.get("name") or name, "number": flat.get("number"), "area_m2": round(area, 2) if area else None,
                      "level": flat.get("level"), "external_id": obj.get("externalId"), "object_id": obj.get("objectid")})
    return rooms


_client: ApsClient | None = None


def get_aps() -> ApsClient:
    global _client
    if _client is None:
        _client = ApsClient()
    return _client
