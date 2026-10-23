"""Platform charges: subscriptions and AI-credit packs paid by card (Ameriabank vPOS).

Money for marketplace orders never passes through here — the supplier remains the seller and is paid directly
(pricing v1.0 §5.1). A charge is applied exactly once: by the browser return, by the periodic sync, or by an
admin «sync» — whichever reaches GetPaymentDetails first; repeats are no-ops (status check + ledger idempotency)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..scheduler import periodic
from . import credits, ledger
from .ameriabank import VposClient, VposError, load_config, safe_details
from .tariffs import _aware, get_tariffs, plans_for

log = logging.getLogger("forma.billing")


class BillingError(Exception):
    def __init__(self, code: str, **params):
        super().__init__(code)
        self.code, self.params = code, params


def add_months(d: datetime, n: int) -> datetime:
    y, mo = divmod(d.month - 1 + n, 12)
    day = min(d.day, [31, 29 if (d.year + y) % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mo])
    return d.replace(year=d.year + y, month=mo + 1, day=day)


def price_of(db: Session, org: m.Organization, purpose: str, key: str, interval: str) -> tuple[int, str]:
    """Amount (AMD) and description; refuses contract-only plans and plans of the other organisation kind."""
    t = get_tariffs(db)
    if purpose == "plan":
        plan = next((p for p in plans_for(t, org.kind) if p.key == key), None)
        if not plan or plan.custom:
            raise BillingError("billing.not_purchasable")
        if interval == "year":
            if plan.price_amd_year is None:
                raise BillingError("billing.not_purchasable")
            return plan.price_amd_year, f"Renovara {plan.name} · 12 months"
        return plan.price_amd_month, f"Renovara {plan.name} · 1 month"
    if purpose == "credits":
        if org.kind == "supplier":
            raise BillingError("billing.not_purchasable")
        pack = next((c for c in t.credit_packs if c.key == key), None)
        if not pack:
            raise BillingError("billing.not_purchasable")
        return pack.price_amd, f"Renovara AI credits · {pack.credits}"
    raise BillingError("billing.not_purchasable")


def next_order_id(db: Session, offset: int) -> int:
    row = m.VposOrderSeq()
    db.add(row)
    db.flush()
    return offset + row.id


def checkout(db: Session, org: m.Organization, user: m.User, *, purpose: str, key: str, interval: str, back_url: str, lang: str,
             client: VposClient | None = None) -> m.BillingPayment:
    amount, description = price_of(db, org, purpose, key, interval)
    cfg = load_config(db)
    if not cfg.configured:
        raise BillingError("billing.not_configured")
    pay = m.BillingPayment(org_id=org.id, user_id=user.id, purpose=purpose, item_key=key, interval=interval if purpose == "plan" else "", amount_amd=amount)
    db.add(pay)
    db.flush()
    pay.order_id = next_order_id(db, cfg.order_id_offset)
    vc = client or VposClient(cfg)
    try:
        pay.provider_payment_id = vc.init_payment(order_id=pay.order_id, amount=amount, description=description, back_url=back_url, opaque=pay.id)
    except VposError as e:
        pay.status, pay.response_code = "error", e.code
        pay.details = {"error": e.message[:200]}
        db.commit()
        raise BillingError("billing.bank_error", code=e.code) from None
    pay.status = "redirected"
    pay.details = {"pay_url": vc.pay_url(pay.provider_payment_id, lang)}
    return pay


def apply_paid(db: Session, pay: m.BillingPayment, now: datetime | None = None) -> bool:
    """Activates what was bought. Idempotent: returns False when the payment was already applied."""
    if pay.status == "paid":
        return False
    now = now or datetime.now(timezone.utc)
    org = db.get(m.Organization, pay.org_id)
    t = get_tariffs(db)
    st = dict(org.settings or {})
    if pay.purpose == "plan":
        plan = next(p for p in plans_for(t, org.kind) if p.key == pay.item_key)
        current = _aware(st.get("paid_until")) if st.get("plan") == plan.key else None
        start = current if current and current > now else now
        st.update(plan=plan.key, interval=pay.interval, paid_until=add_months(start, 12 if pay.interval == "year" else 1).isoformat())
        org.settings = st
        db.flush()
        credits.grant_plan_month(db, org, now)
        if plan.commission_pct is not None:  # supplier plans set the commission rate (pricing v1.0 §2.4)
            for s in db.scalars(select(m.Supplier).where(m.Supplier.org_id == org.id)):
                s.commission_pct = plan.commission_pct
        stream = "subscription"
    else:
        pack = next(c for c in t.credit_packs if c.key == pay.item_key)
        credits.grant(db, org.id, pack.credits, "grant_pack", ref=pay.id, expires_at=add_months(now, pack.validity_months), idempotency_key=f"pack:{pay.id}")
        stream = "credits"
    ledger.post(db, stream, [("cash:acquirer", pay.amount_amd, 0), (f"revenue:{stream}", 0, pay.amount_amd)], idempotency_key=f"billing:{pay.id}",
                memo=f"vpos order {pay.order_id} · {org.name}")
    pay.status, pay.paid_at = "paid", now
    db.add(m.AuditEvent(org_id=org.id, user_id=pay.user_id, action="billing.paid", entity="billing_payment", entity_id=pay.id,
                        data={"purpose": pay.purpose, "item": pay.item_key, "amount_amd": pay.amount_amd}))
    return True


def sync(db: Session, pay: m.BillingPayment, client: VposClient | None = None) -> m.BillingPayment:
    """Reads the bank's status (GetPaymentDetails) and applies it."""
    if not pay.provider_payment_id or pay.status in ("paid", "refunded", "cancelled"):
        return pay
    vc = client or VposClient(load_config(db))
    try:
        d = vc.details(pay.provider_payment_id)
    except VposError as e:
        log.warning("vpos details %s: %s", pay.id, e)
        return pay
    status = str(d.get("OrderStatus", ""))
    pay.response_code = str(d.get("ResponseCode") or "")
    pay.details = {**(pay.details or {}), **safe_details(d)}
    if status == "1":  # pre-authorised (two-stage merchant): take the money
        try:
            vc.confirm(pay.provider_payment_id, pay.amount_amd)
            status = "2"
        except VposError as e:
            pay.details = {**pay.details, "confirm_error": e.code}
    if status == "2" and pay.response_code == "00":
        amount = float(d.get("Amount") or d.get("DepositedAmount") or 0)
        if round(amount) != pay.amount_amd:
            pay.status = "error"
            pay.details = {**pay.details, "error": "amount_mismatch"}
            db.add(m.AuditEvent(org_id=pay.org_id, action="billing.amount_mismatch", entity="billing_payment", entity_id=pay.id,
                                data={"expected": pay.amount_amd, "received": amount}))
        else:
            apply_paid(db, pay)
    elif status == "6":
        pay.status = "declined"
    elif status == "3":
        pay.status = "cancelled"
    elif status == "4":
        pay.status = "refunded"
    return pay


def refund(db: Session, pay: m.BillingPayment, amount: int | None, *, client: VposClient | None = None) -> m.BillingPayment:
    if pay.status != "paid":
        raise BillingError("billing.not_refundable")
    left = pay.amount_amd - pay.refunded_amd
    amount = left if amount is None else amount
    if amount <= 0 or amount > left:
        raise BillingError("billing.refund_amount", max=left)
    vc = client or VposClient(load_config(db))
    try:
        vc.refund(pay.provider_payment_id, amount)
    except VposError as e:
        raise BillingError("billing.bank_error", code=e.code) from None
    pay.refunded_amd += amount
    stream = "subscription" if pay.purpose == "plan" else "credits"
    ledger.post(db, "refund", [(f"revenue:{stream}", amount, 0), ("cash:acquirer", 0, amount)], idempotency_key=f"billing-refund:{pay.id}:{pay.refunded_amd}",
                memo=f"vpos refund order {pay.order_id}")
    if pay.refunded_amd >= pay.amount_amd:
        pay.status = "refunded"
        org = db.get(m.Organization, pay.org_id)
        if pay.purpose == "plan":
            org.settings = {**(org.settings or {}), "paid_until": datetime.now(timezone.utc).isoformat()}
        else:
            pack = next((c for c in get_tariffs(db).credit_packs if c.key == pay.item_key), None)
            if pack:
                db.add(m.CreditEntry(org_id=org.id, delta=-min(pack.credits, credits.balance(db, org.id)), reason="revoke", ref=pay.id))
    return pay


def cancel(db: Session, pay: m.BillingPayment, *, client: VposClient | None = None) -> m.BillingPayment:
    """CancelPayment (available 72 h after initialisation): voids an unpaid or same-day payment."""
    vc = client or VposClient(load_config(db))
    try:
        vc.cancel(pay.provider_payment_id)
    except VposError as e:
        raise BillingError("billing.bank_error", code=e.code) from None
    if pay.status == "paid":
        pay.refunded_amd = pay.amount_amd
        stream = "subscription" if pay.purpose == "plan" else "credits"
        ledger.post(db, "refund", [(f"revenue:{stream}", pay.amount_amd, 0), ("cash:acquirer", 0, pay.amount_amd)], idempotency_key=f"billing-cancel:{pay.id}",
                    memo=f"vpos cancel order {pay.order_id}")
    pay.status = "cancelled"
    return pay


def start_trial(db: Session, org: m.Organization, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    st = dict(org.settings or {})
    if st.get("trial_used"):
        raise BillingError("billing.trial_used")
    t = get_tariffs(db)
    until = now + timedelta(days=t.trial.days)
    st.update(trial_used=True, trial_until=until.isoformat(), plan=st.get("plan") or "free")
    org.settings = st
    credits.grant(db, org.id, t.trial.credits, "grant_trial", expires_at=until, idempotency_key=f"trial:{org.id}")


def assign_plan(db: Session, org: m.Organization, key: str | None) -> None:
    """Platform assignment (invoice, pilot agreement): no paid period; Free also grants its one-off credits."""
    st = {k: v for k, v in (org.settings or {}).items() if k not in ("paid_until", "interval")}
    st["plan"] = key
    org.settings = st
    plan = next((p for p in plans_for(get_tariffs(db), org.kind) if p.key == key), None) if key else None
    if plan and plan.ai_credits_once:
        credits.grant(db, org.id, plan.ai_credits_once, "grant_free", idempotency_key=f"free:{org.id}")
    if plan and plan.commission_pct is not None:
        for s in db.scalars(select(m.Supplier).where(m.Supplier.org_id == org.id)):
            s.commission_pct = plan.commission_pct


_last: dict[str, float] = {}


@periodic("billing_sync")
def scheduled_sync(db: Session) -> bool:
    """Every 5 minutes: settles payments whose browser never came back; daily-idempotent monthly plan credits."""
    import time

    if time.time() - _last.get("sync", 0) < 300:
        return False
    _last["sync"] = time.time()
    if load_config(db).configured:
        since = datetime.now(timezone.utc) - timedelta(days=1)
        for pay in db.scalars(select(m.BillingPayment).where(m.BillingPayment.status == "redirected", m.BillingPayment.created_at >= since)):
            sync(db, pay)
    for org in db.scalars(select(m.Organization).where(m.Organization.kind.in_(("bureau", "supplier")))):
        if (org.settings or {}).get("plan"):
            credits.grant_plan_month(db, org)
    db.commit()
    return True
