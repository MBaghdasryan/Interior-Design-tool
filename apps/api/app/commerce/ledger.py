"""Double-entry ledger (AMD, whole drams). A transaction is a set of lines that balance
(Σdebit = Σcredit); rows are append-only — a correction is a new reversing transaction.
Posting is idempotent: the same `idempotency_key` returns the existing transaction.

Accounts (prefix:qualifier):
  cash                         — money received from clients / paid out (provider settlement account)
  supplier_payable:<supplier>  — owed to a supplier for goods, delivery and installation
  designer_payable:<org>       — designer / bureau commission owed
  revenue:commission           — platform commission (net of tax)
  revenue:<stream>             — other revenue streams (subscription, credits, exports, leads, white_label)
  tax_payable                  — taxes and fees on platform revenue (configurable rate)
  promo_expense                — discounts funded by the platform
"""
from __future__ import annotations

import csv
import io
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m


class LedgerError(ValueError):
    pass


def post(db: Session, kind: str, lines: list[tuple[str, int, int]], *, idempotency_key: str, order_id: str | None = None, memo: str = "") -> str:
    """lines: (account, debit, credit) with exactly one side > 0. Returns the transaction id."""
    existing = db.scalar(select(m.LedgerEntry.txn_id).where(m.LedgerEntry.idempotency_key == idempotency_key).limit(1))
    if existing:
        return existing
    lines = [(a, int(round(d)), int(round(c))) for a, d, c in lines if round(d) or round(c)]
    if not lines:
        raise LedgerError("empty transaction")
    for a, d, c in lines:
        if d < 0 or c < 0 or (d and c):
            raise LedgerError(f"line {a}: one non-negative side per line")
    if sum(d for _, d, _ in lines) != sum(c for _, _, c in lines):
        raise LedgerError("transaction does not balance")
    txn = m.new_id()
    for i, (a, d, c) in enumerate(lines):
        db.add(m.LedgerEntry(txn_id=txn, line_no=i, kind=kind, account=a, debit=d, credit=c, order_id=order_id, idempotency_key=idempotency_key, memo=memo[:300]))
    db.flush()
    return txn


def reverse(db: Session, txn_id: str, *, idempotency_key: str, kind: str = "refund", memo: str = "") -> str:
    rows = db.scalars(select(m.LedgerEntry).where(m.LedgerEntry.txn_id == txn_id).order_by(m.LedgerEntry.line_no)).all()
    if not rows:
        raise LedgerError("unknown transaction")
    return post(db, kind, [(r.account, r.credit, r.debit) for r in rows], idempotency_key=idempotency_key, order_id=rows[0].order_id, memo=memo or f"reversal of {txn_id}")


def balances(db: Session) -> dict[str, int]:
    """Account → debit − credit."""
    rows = db.execute(select(m.LedgerEntry.account, func.sum(m.LedgerEntry.debit), func.sum(m.LedgerEntry.credit)).group_by(m.LedgerEntry.account)).all()
    return {a: int(d or 0) - int(c or 0) for a, d, c in sorted(rows)}


def reconcile(db: Session) -> dict:
    """Every transaction balances, the journal as a whole balances, and captured payments match cash receipts."""
    per_txn = db.execute(select(m.LedgerEntry.txn_id, func.sum(m.LedgerEntry.debit), func.sum(m.LedgerEntry.credit)).group_by(m.LedgerEntry.txn_id)).all()
    unbalanced = [t for t, d, c in per_txn if int(d or 0) != int(c or 0)]
    total_d = sum(int(d or 0) for _, d, _ in per_txn)
    total_c = sum(int(c or 0) for _, _, c in per_txn)
    captured = int(db.scalar(select(func.coalesce(func.sum(m.Payment.amount_amd), 0)).where(m.Payment.status == "captured")) or 0)
    refunded = int(db.scalar(select(func.coalesce(func.sum(m.Payment.amount_amd), 0)).where(m.Payment.status == "refunded")) or 0)
    cash_in = int(db.scalar(select(func.coalesce(func.sum(m.LedgerEntry.debit), 0)).where(m.LedgerEntry.account == "cash", m.LedgerEntry.kind == "capture")) or 0)
    cash_back = int(db.scalar(select(func.coalesce(func.sum(m.LedgerEntry.credit), 0)).where(m.LedgerEntry.account == "cash", m.LedgerEntry.kind == "refund")) or 0)
    return {"balanced": not unbalanced and total_d == total_c, "transactions": len(per_txn), "unbalanced": unbalanced[:20],
            "debit_total": total_d, "credit_total": total_c,
            "payments_match_cash": captured + refunded == cash_in and refunded == cash_back,
            "captured_amd": captured + refunded, "cash_received_amd": cash_in, "refunded_amd": refunded}


def revenue_by_stream(db: Session) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for a, bal in balances(db).items():
        if a.startswith("revenue:"):
            out[a.split(":", 1)[1]] += -bal  # revenue accounts carry credit balances
    return dict(out)


def export_rows(db: Session) -> list[dict]:
    return [{"created_at": r.created_at.isoformat(), "txn_id": r.txn_id, "line": r.line_no, "kind": r.kind, "account": r.account, "debit": r.debit,
             "credit": r.credit, "currency": r.currency, "order_id": r.order_id or "", "memo": r.memo}
            for r in db.scalars(select(m.LedgerEntry).order_by(m.LedgerEntry.created_at, m.LedgerEntry.txn_id, m.LedgerEntry.line_no))]


def export_csv(db: Session) -> bytes:
    rows = export_rows(db)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["created_at", "txn_id", "line", "kind", "account", "debit", "credit", "currency", "order_id", "memo"])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8-sig")


def export_xlsx(db: Session) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "journal"
    rows = export_rows(db)
    head = ["created_at", "txn_id", "line", "kind", "account", "debit", "credit", "currency", "order_id", "memo"]
    ws.append(head)
    for r in rows:
        ws.append([r[h] for h in head])
    bs = wb.create_sheet("balances")
    bs.append(["account", "balance (debit − credit)"])
    for a, b in balances(db).items():
        bs.append([a, b])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
