"""TOTP multi-factor authentication (RFC 6238, 30 s, 6 digits) with one-time backup codes.

* Secrets are encrypted at rest (Fernet, key derived from SECRET_KEY — rotating the key
  requires users to re-enrol MFA; see RUNBOOK §7).
* Backup codes: 10 × 10 characters, shown once, stored as SHA-256, single use.
* Login with MFA: password → short-lived signed `mfa_token` (5 min) → code → session.
* Enforcement: roles in MFA_REQUIRED_ROLES must enrol before using the API (production
  default; MFA_ENFORCE=true turns it on elsewhere)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import secrets
import time

import pyotp
from cryptography.fernet import Fernet, InvalidToken

from . import models as m
from .config import get_settings

ISSUER = "Renovara"
ENROLMENT_ALLOWED_PATHS = ("/api/v1/auth/me", "/api/v1/auth/mfa/", "/api/v1/auth/logout", "/api/v1/auth/sessions")


def _fernet() -> Fernet:
    key = hashlib.sha256(b"renovara-mfa:" + get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def required_for(roles: set[str]) -> bool:
    s = get_settings()
    if not (s.mfa_enforce if s.mfa_enforce is not None else s.is_production):
        return False
    return bool(roles & {r.strip() for r in s.mfa_required_roles.split(",") if r.strip()})


def start_setup(user: m.User) -> dict:
    secret = pyotp.random_base32()
    user.mfa_pending_enc = encrypt(secret)
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=get_settings().brand_name or ISSUER)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": qr_svg(uri)}


def qr_svg(data: str) -> str:
    import qrcode
    import qrcode.image.svg

    buf = io.BytesIO()
    qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=8).save(buf)
    return buf.getvalue().decode()


def verify_totp(secret: str | None, code: str) -> bool:
    code = (code or "").replace(" ", "")
    return bool(secret and code.isdigit() and pyotp.TOTP(secret).verify(code, valid_window=1))


def new_backup_codes() -> tuple[list[str], list[str]]:
    plain = [secrets.token_hex(5) for _ in range(10)]
    return plain, [hashlib.sha256(c.encode()).hexdigest() for c in plain]


def use_backup_code(user: m.User, code: str) -> bool:
    h = hashlib.sha256((code or "").strip().lower().encode()).hexdigest()
    codes = list(user.mfa_backup_codes or [])
    if h in codes:
        codes.remove(h)
        user.mfa_backup_codes = codes
        return True
    return False


def check_second_factor(user: m.User, code: str | None, backup_code: str | None) -> bool:
    if code and verify_totp(decrypt(user.mfa_secret_enc), code):
        return True
    return bool(backup_code and use_backup_code(user, backup_code))


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def issue_mfa_token(user_id: str, ttl_s: int = 300) -> str:
    payload = _b64(json.dumps({"sub": user_id, "exp": int(time.time()) + ttl_s, "purpose": "mfa"}).encode())
    sig = _b64(hmac.new(get_settings().secret_key.encode(), f"mfa.{payload}".encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def read_mfa_token(token: str) -> str | None:
    try:
        payload, sig = token.split(".")
        good = _b64(hmac.new(get_settings().secret_key.encode(), f"mfa.{payload}".encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(good, sig):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    return data["sub"] if data.get("purpose") == "mfa" and data.get("exp", 0) > time.time() else None
