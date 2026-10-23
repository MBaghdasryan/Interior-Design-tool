"""Ameriabank vPOS 3.1 (REST) — card payments for platform charges (subscriptions, AI-credit packs).

Flow (spec «AmeriaBank vPOS 3.1 API Protocol Description»):
InitPayment → redirect the browser to /Payments/Pay?id=…&lang=… → the bank returns to BackURL with orderID, paymentID,
resposneCode → GetPaymentDetails is the source of truth (ResponseCode "00", OrderStatus 2 = deposited). A two-stage
merchant receives OrderStatus 1 (pre-authorised) and must ConfirmPayment. CancelPayment works within 72 h of
initialisation; RefundPayment returns part or all of a deposited amount.

Credentials (ClientID, Username, Password) are entered in the platform admin and stored encrypted; they are never
returned to the browser. Card data never touches Renovara: the card form is the bank's page."""
from __future__ import annotations

from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from .. import models as m

TEST_BASE = "https://servicestest.ameriabank.am/VPOS"
LIVE_BASE = "https://services.ameriabank.am/VPOS"  # production host to be confirmed by the bank at contract signing
CURRENCY = {"AMD": "051", "EUR": "978", "USD": "840", "RUB": "643"}
LANG = {"hy": "am", "ru": "ru", "en": "en"}
# Table 2 of the spec: OrderStatus code → payment state
ORDER_STATUS = {"0": "payment_started", "1": "payment_approved", "2": "payment_deposited", "3": "payment_void", "4": "payment_refunded",
                "5": "payment_autoauthorized", "6": "payment_declined"}
SETTING_KEY = "vpos"


class VposError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


@dataclass
class VposConfig:
    client_id: str = ""
    username: str = ""
    password: str = ""
    mode: str = "test"  # test | live
    base_url: str = ""  # optional override
    order_id_offset: int = 0  # banks often assign an OrderID range per merchant (e.g. 2 000 000 in test)
    timeout_s: int = 1200  # payment session; the spec caps it at 1200 s

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.username and self.password)

    @property
    def base(self) -> str:
        return (self.base_url or (LIVE_BASE if self.mode == "live" else TEST_BASE)).rstrip("/")


def load_config(db: Session) -> VposConfig:
    from ..mfa import decrypt

    row = db.get(m.PlatformSetting, SETTING_KEY)
    v = dict(row.value) if row and row.value else {}
    return VposConfig(client_id=v.get("client_id", ""), username=v.get("username", ""), password=decrypt(v.get("password_enc")) or "",
                      mode=v.get("mode", "test"), base_url=v.get("base_url", ""), order_id_offset=int(v.get("order_id_offset", 0)),
                      timeout_s=int(v.get("timeout_s", 1200)))


def save_config(db: Session, *, client_id: str, username: str, password: str | None, mode: str, base_url: str, order_id_offset: int) -> None:
    from ..mfa import encrypt

    row = db.get(m.PlatformSetting, SETTING_KEY) or m.PlatformSetting(key=SETTING_KEY, value={})
    v = dict(row.value or {})
    v.update(client_id=client_id.strip(), username=username.strip(), mode=mode, base_url=base_url.strip(), order_id_offset=order_id_offset)
    if password:  # empty = keep the stored password
        v["password_enc"] = encrypt(password)
    row.value = v
    db.merge(row)


def public_config(db: Session) -> dict:
    row = db.get(m.PlatformSetting, SETTING_KEY)
    v = dict(row.value) if row and row.value else {}
    cfg = load_config(db)
    return {"client_id": cfg.client_id, "username": cfg.username, "password_set": bool(v.get("password_enc")), "mode": cfg.mode,
            "base_url": cfg.base_url, "effective_base": cfg.base, "order_id_offset": cfg.order_id_offset, "configured": cfg.configured}


def _http() -> httpx.Client:  # replaced in tests by a client with a mock transport
    return httpx.Client(timeout=30)


class VposClient:
    def __init__(self, cfg: VposConfig, client: httpx.Client | None = None):
        self.cfg = cfg
        self.http = client or _http()

    def _post(self, op: str, body: dict) -> dict:
        try:
            r = self.http.post(f"{self.cfg.base}/api/VPOS/{op}", json=body, headers={"Accept": "application/json"})
        except httpx.HTTPError as e:
            raise VposError("network", str(e)[:200]) from None
        if r.status_code >= 400:
            raise VposError(f"http_{r.status_code}", r.text[:200])
        try:
            return r.json()
        except ValueError:
            raise VposError("bad_response", r.text[:200]) from None

    def _auth(self) -> dict:
        return {"Username": self.cfg.username, "Password": self.cfg.password}

    def init_payment(self, *, order_id: int, amount: float, description: str, back_url: str, opaque: str = "", currency: str = "AMD") -> str:
        data = self._post("InitPayment", {"ClientID": self.cfg.client_id, **self._auth(), "Currency": CURRENCY.get(currency, "051"), "Description": description[:120],
                                          "OrderID": order_id, "Amount": amount, "BackURL": back_url, "Opaque": opaque, "Timeout": min(self.cfg.timeout_s, 1200)})
        if str(data.get("ResponseCode")) != "1" or not data.get("PaymentID"):  # InitPayment success is 1 (not "00")
            raise VposError(str(data.get("ResponseCode")), str(data.get("ResponseMessage") or ""))
        return str(data["PaymentID"])

    def pay_url(self, payment_id: str, lang: str = "hy") -> str:
        return f"{self.cfg.base}/Payments/Pay?id={payment_id}&lang={LANG.get(lang, 'am')}"

    def details(self, payment_id: str) -> dict:
        return self._post("GetPaymentDetails", {"PaymentID": payment_id, **self._auth()})

    def confirm(self, payment_id: str, amount: float) -> dict:
        return self._expect_ok(self._post("ConfirmPayment", {"PaymentID": payment_id, **self._auth(), "Amount": amount}))

    def cancel(self, payment_id: str) -> dict:
        return self._expect_ok(self._post("CancelPayment", {"PaymentID": payment_id, **self._auth()}))

    def refund(self, payment_id: str, amount: float) -> dict:
        return self._expect_ok(self._post("RefundPayment", {"PaymentID": payment_id, **self._auth(), "Amount": amount}))

    @staticmethod
    def _expect_ok(data: dict) -> dict:
        if str(data.get("ResponseCode")) != "00":
            raise VposError(str(data.get("ResponseCode")), str(data.get("ResponseMessage") or ""))
        return data


def safe_details(d: dict) -> dict:
    """What we keep from GetPaymentDetails: masked card and references — no card holder e-mail, no expiry date."""
    return {k: d.get(k) for k in ("CardNumber", "ApprovalCode", "rrn", "PaymentType", "PaymentState", "OrderStatus", "Amount", "DepositedAmount",
                                  "RefundedAmount", "Currency", "DateTime", "ResponseCode", "MDOrderID") if d.get(k) not in (None, "")}
