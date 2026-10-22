"""Orders: cart per supplier → price re-check → request → supplier confirmation (quote,
commissions) → production → delivery → installation → closed; cancel, dispute, refund.
Money is recorded only from verified provider events (payments.py) into the ledger."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from ..errors import ApiError
from . import ledger

# status → {next status: side allowed to move it}; "platform" can always resolve disputes
TRANSITIONS: dict[str, dict[str, str]] = {
    "cart": {"requested": "bureau", "cancelled": "bureau"},
    "requested": {"confirmed": "supplier", "cancelled": "any"},
    "confirmed": {"in_production": "supplier", "cancelled": "bureau", "disputed": "bureau"},
    "in_production": {"delivering": "supplier", "disputed": "bureau"},
    "delivering": {"installing": "supplier", "closed": "bureau", "disputed": "bureau"},
    "installing": {"closed": "bureau", "disputed": "bureau"},
    "disputed": {"closed": "platform", "refunded": "platform", "in_production": "platform", "delivering": "platform"},
}
FINAL = {"closed", "cancelled", "refunded"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


def commerce_settings(db: Session) -> dict:
    row = db.get(m.PlatformSetting, "commerce")
    return {"tax_rate_pct": 0.0, "designer_commission_pct": 0.0, **(row.value if row else {})}


# ------------------------------------------------------------------ cart
def build_cart(db: Session, proj: m.Project, variant: m.DesignVariant, estimate: dict) -> tuple[m.Cart, list[m.Order]]:
    if db.scalar(select(m.Order.id).where(m.Order.project_id == proj.id, m.Order.status.notin_(("cart", "cancelled"))).limit(1)):
        raise ApiError(409, "cart.orders_in_progress")  # a new cart would duplicate orders already sent to suppliers
    for old in db.scalars(select(m.Order).where(m.Order.project_id == proj.id, m.Order.status == "cart")):
        db.delete(old)
    for c in db.scalars(select(m.Cart).where(m.Cart.project_id == proj.id, m.Cart.status == "open")):
        c.status = "abandoned"
    cart = m.Cart(project_id=proj.id, variant_id=variant.id)
    db.add(cart)
    db.flush()
    groups: dict[str, list[dict]] = defaultdict(list)
    for ln in estimate.get("lines", []):
        if ln.get("supplier_key") and ln.get("group") not in ("works", "contingency"):
            groups[ln["supplier_key"]].append(ln)
    orders = []
    for key, lines in groups.items():
        goods = [x for x in lines if x["group"] not in ("delivery", "installation")]
        sup = db.scalar(select(m.Supplier).where(m.Supplier.slug == key))
        o = m.Order(project_id=proj.id, cart_id=cart.id, supplier_id=sup.id if sup else None, supplier_name=lines[0].get("supplier") or key, status="cart",
                    items=[{k: x.get(k) for k in ("id", "ref", "name", "sku", "qty", "unit", "unit_price", "total", "price_status", "url", "lead_days")} for x in goods],
                    delivery=(sup.delivery if sup else {}), installation=(sup.installation if sup else {}))
        db.add(o)
        db.flush()
        for x in goods:
            db.add(m.OrderItem(order_id=o.id, ref=x.get("ref") or x.get("id") or "", name=(x.get("name") or "")[:300], sku=x.get("sku") or "", qty=x.get("qty") or 1,
                               unit=x.get("unit") or "pcs", unit_price=x.get("unit_price"), total=x.get("total"), price_status=x.get("price_status") or "estimated",
                               url=(x.get("url") or "")[:600], lead_days=x.get("lead_days")))
        delivery_amd = sum(x["total"] or 0 for x in lines if x["group"] == "delivery")
        install_amd = sum(x["total"] or 0 for x in lines if x["group"] == "installation")
        db.add(m.Delivery(order_id=o.id, cost_amd=int(delivery_amd), address=proj.address or ""))
        db.add(m.Installation(order_id=o.id, cost_amd=int(install_amd), status="pending" if install_amd else "not_needed"))
        o.totals = _totals(db, o, sup, delivery_amd, install_amd)
        orders.append(o)
    return cart, orders


def _items(db: Session, o: m.Order) -> list[m.OrderItem]:
    db.flush()  # the session factory does not autoflush
    return list(db.scalars(select(m.OrderItem).where(m.OrderItem.order_id == o.id)))


def _totals(db: Session, o: m.Order, sup: m.Supplier | None, delivery_amd: float, install_amd: float) -> dict:
    items = _items(db, o)
    goods = sum((it.rechecked_price if it.rechecked_price is not None else (it.unit_price or 0)) * (it.qty or 1) if it.unit_price is not None or it.rechecked_price is not None
                else 0 for it in items)
    return {"goods": round(goods), "delivery": round(delivery_amd), "installation": round(install_amd),
            "quote_required": sum(1 for it in items if it.unit_price is None and it.rechecked_price is None),
            "commission_platform": round(goods * ((sup.commission_pct if sup else 0) / 100)), "discount": int((o.totals or {}).get("discount", 0))}


def recheck_cart(db: Session, cart: m.Cart) -> dict:
    """Re-read every item's current price (internal catalogue variant or external record with its TTL)."""
    s = get_settings()
    now = _now()
    changed, unavailable, stale = [], [], []
    for o in db.scalars(select(m.Order).where(m.Order.cart_id == cart.id, m.Order.status == "cart")):
        for it in _items(db, o):
            price, kind = None, it.ref.split(":", 1)[0] if ":" in it.ref else ""
            if kind == "pv":
                v = db.get(m.ProductVariant, it.ref[3:])
                if not v or v.stock_status == "discontinued":
                    unavailable.append(it.name)
                price = v.price if v else None
            elif kind == "ext":
                rec = db.get(m.ExternalProductRecord, it.ref[4:])
                if not rec:
                    unavailable.append(it.name)
                else:
                    price = rec.price_amd
                    src = db.get(m.ExternalSource, rec.source_id)
                    if (now - _aware(rec.retrieved_at)).total_seconds() / 3600 > float(((src.ttl_h if src else None) or {}).get("price", s.external_price_ttl_h)):
                        stale.append(it.name)
            else:
                price = it.unit_price
            if price is not None and it.unit_price is not None and abs(price - it.unit_price) >= 1:
                changed.append({"name": it.name, "was": it.unit_price, "now": price})
            it.rechecked_price = price
        sup = db.get(m.Supplier, o.supplier_id) if o.supplier_id else None
        d = db.scalar(select(m.Delivery).where(m.Delivery.order_id == o.id))
        inst = db.scalar(select(m.Installation).where(m.Installation.order_id == o.id))
        o.totals = _totals(db, o, sup, d.cost_amd if d else 0, inst.cost_amd if inst else 0)
    delta = sum((c["now"] - c["was"]) for c in changed)
    cart.rechecked_at = now
    cart.recheck = {"changed": changed[:100], "unavailable": unavailable[:100], "stale": stale[:100], "delta_amd": round(delta)}
    return cart.recheck


# ------------------------------------------------------------------ lifecycle
def transition(db: Session, o: m.Order, to: str, *, side: str, actor: str, note: str = "") -> m.Order:
    allowed = TRANSITIONS.get(o.status, {})
    who = allowed.get(to)
    if who is None or not (who == side or who == "any" or side == "platform"):
        raise ApiError(409, "order.bad_transition", frm=o.status, to=to)
    if to == "cancelled" and o.payment_status == "paid":
        raise ApiError(409, "order.paid_needs_refund")
    o.history = [*(o.history or []), {"at": _now().isoformat(), "from": o.status, "to": to, "by": actor, "side": side, "note": note[:300]}]
    o.status = to
    return o


def request(db: Session, o: m.Order, *, actor: str, idempotency_key: str | None) -> m.Order:
    if o.status == "requested" and idempotency_key and o.idempotency_key == idempotency_key:
        return o  # retried request
    cart = db.get(m.Cart, o.cart_id) if o.cart_id else None
    max_age = timedelta(hours=get_settings().order_recheck_max_age_h)
    if not cart or not cart.rechecked_at or _now() - _aware(cart.rechecked_at) > max_age:
        raise ApiError(409, "order.recheck_required")
    if (cart.recheck or {}).get("unavailable"):
        raise ApiError(409, "order.items_unavailable", n=len(cart.recheck["unavailable"]))
    sup = db.get(m.Supplier, o.supplier_id) if o.supplier_id else None
    if sup and sup.is_demo:
        raise ApiError(409, "order.demo_supplier")
    if idempotency_key:
        o.idempotency_key = idempotency_key
    transition(db, o, "requested", side="bureau", actor=actor)
    cart.status = "checked_out" if all(x.status != "cart" for x in db.scalars(select(m.Order).where(m.Order.cart_id == cart.id))) else cart.status
    return o


def confirm(db: Session, o: m.Order, *, total_amd: int, valid_days: int, actor: str, note: str = "") -> m.SupplierQuote:
    """Supplier confirms with a binding total; commissions are fixed at this moment."""
    if total_amd <= 0:
        raise ApiError(422, "validation", fields=["total_amd"])
    transition(db, o, "confirmed", side="supplier", actor=actor, note=note)
    q = m.SupplierQuote(order_id=o.id, supplier_id=o.supplier_id, total_amd=int(total_amd), valid_until=_now() + timedelta(days=valid_days), note=note[:500])
    db.add(q)
    sup = db.get(m.Supplier, o.supplier_id) if o.supplier_id else None
    proj = db.get(m.Project, o.project_id)
    cs = commerce_settings(db)
    org = db.get(m.Organization, proj.org_id) if proj else None
    designer_pct = float(((org.settings or {}).get("commerce") or {}).get("designer_commission_pct", cs["designer_commission_pct"])) if org else 0.0
    db.query(m.Commission).filter_by(order_id=o.id).delete()
    db.add(m.Commission(order_id=o.id, party="platform", pct=sup.commission_pct if sup else 0.0, amount_amd=round(total_amd * (sup.commission_pct if sup else 0) / 100)))
    db.add(m.Commission(order_id=o.id, party="designer", org_id=proj.org_id if proj else None, pct=designer_pct, amount_amd=round(total_amd * designer_pct / 100)))
    o.totals = {**(o.totals or {}), "quoted": int(total_amd)}
    return q


def payable_amd(db: Session, o: m.Order) -> int:
    q = db.scalar(select(m.SupplierQuote).where(m.SupplierQuote.order_id == o.id, m.SupplierQuote.status == "accepted").order_by(m.SupplierQuote.created_at.desc()).limit(1))
    if not q:
        raise ApiError(409, "order.not_confirmed")
    return max(0, int(q.total_amd) - int((o.totals or {}).get("discount", 0)))


# ------------------------------------------------------------------ money (ledger)
def capture_lines(db: Session, o: m.Order, amount_amd: int) -> list[tuple[str, int, int]]:
    q = db.scalar(select(m.SupplierQuote).where(m.SupplierQuote.order_id == o.id).order_by(m.SupplierQuote.created_at.desc()).limit(1))
    gross = int(q.total_amd) if q else amount_amd
    discount = gross - amount_amd
    com = {c.party: c for c in db.scalars(select(m.Commission).where(m.Commission.order_id == o.id))}
    platform = int(com["platform"].amount_amd) if "platform" in com else 0
    designer = int(com["designer"].amount_amd) if "designer" in com else 0
    tax = round(platform * commerce_settings(db)["tax_rate_pct"] / 100)
    sup_key = f"supplier_payable:{o.supplier_id or o.supplier_name}"
    designer_key = f"designer_payable:{com['designer'].org_id if 'designer' in com else 'unknown'}"
    return [("cash", amount_amd, 0), ("promo_expense", max(discount, 0), 0),
            (sup_key, 0, gross - platform - designer), ("revenue:commission", 0, platform - tax), (designer_key, 0, designer), ("tax_payable", 0, tax)]


def record_capture(db: Session, o: m.Order, pay: m.Payment) -> str:
    txn = ledger.post(db, "capture", capture_lines(db, o, int(pay.amount_amd)), idempotency_key=f"capture:{pay.id}", order_id=o.id, memo=f"{pay.provider} {pay.provider_ref}")
    pay.status = "captured"
    o.payment_status = "paid"
    return txn


def record_refund(db: Session, o: m.Order, pay: m.Payment) -> str:
    cap = db.scalar(select(m.LedgerEntry.txn_id).where(m.LedgerEntry.idempotency_key == f"capture:{pay.id}").limit(1))
    if not cap:
        raise ApiError(409, "order.nothing_to_refund")
    txn = ledger.reverse(db, cap, idempotency_key=f"refund:{pay.id}", memo=f"refund {pay.provider_ref}")
    pay.status = "refunded"
    o.payment_status = "refunded"
    if o.status not in FINAL:
        o.history = [*(o.history or []), {"at": _now().isoformat(), "from": o.status, "to": "refunded", "by": "provider", "side": "platform", "note": ""}]
        o.status = "refunded"
    return txn


def record_payout(db: Session, supplier_id: str, amount_amd: int, *, reference: str, idempotency_key: str) -> m.Payout:
    existing = db.scalar(select(m.Payout).where(m.Payout.reference == reference, m.Payout.supplier_id == supplier_id))
    if existing:
        return existing  # retried request
    owed = ledger.balances(db).get(f"supplier_payable:{supplier_id}", 0)
    if amount_amd <= 0 or amount_amd > -owed:
        raise ApiError(409, "payout.exceeds_balance", owed=-owed)
    txn = ledger.post(db, "payout", [(f"supplier_payable:{supplier_id}", amount_amd, 0), ("cash", 0, amount_amd)], idempotency_key=idempotency_key, memo=reference)
    p = m.Payout(supplier_id=supplier_id, amount_amd=amount_amd, reference=reference[:200], txn_id=txn)
    db.add(p)
    return p
