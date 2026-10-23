"""AI credits (pricing v1.0 §3): an internal unit, not money. Grants expire (plan credits monthly, packs after 12 months);
spends are written once per successful paid AI operation — a provider error without a result is not charged.
The ledger is append-only; the balance is computed by spending the soonest-expiring grants first."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m

# AI task / render → operation of the credit matrix
TASK_OPERATION = {
    "change_command": "text_command", "design_brief": "text_command", "variant_copy": "text_command",
    "floorplan_vision": "plan_ocr", "photo_rooms": "photo_analysis", "photo_elements": "photo_analysis", "view_groups": "photo_analysis",
    "render": "grounded_render", "album": "album",
}
FREE_TASKS = {"render_grounding"}  # part of the render it checks


class NoCredits(Exception):
    def __init__(self, balance: int, need: int):
        super().__init__(f"credits: {balance} < {need}")
        self.balance, self.need = balance, need


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d and d.tzinfo is None else d


def grant(db: Session, org_id: str, credits: int, reason: str, *, ref: str = "", expires_at: datetime | None = None,
          idempotency_key: str | None = None, user_id: str | None = None) -> bool:
    """Adds credits once per idempotency key. Returns False for a repeated grant."""
    if credits <= 0:
        return False
    if idempotency_key and db.scalar(select(m.CreditEntry.id).where(m.CreditEntry.idempotency_key == idempotency_key)):
        return False
    try:
        with db.begin_nested():
            db.add(m.CreditEntry(org_id=org_id, delta=credits, reason=reason, ref=ref, expires_at=expires_at, idempotency_key=idempotency_key, user_id=user_id))
    except IntegrityError:
        return False
    return True


def cost(db: Session, operation: str) -> int:
    from .tariffs import get_tariffs

    return int(get_tariffs(db).credit_costs.get(operation, 0))


def balance(db: Session, org_id: str, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(select(m.CreditEntry).where(m.CreditEntry.org_id == org_id).order_by(m.CreditEntry.created_at)).all()
    grants = [[_aware(r.created_at), _aware(r.expires_at), r.delta] for r in rows if r.delta > 0]
    for r in rows:
        if r.delta >= 0:
            continue
        need, at = -r.delta, _aware(r.created_at)
        # spend from grants valid at that moment, soonest expiry first
        for g in sorted((g for g in grants if g[0] <= at and (g[1] is None or g[1] > at) and g[2] > 0), key=lambda g: g[1] or datetime.max.replace(tzinfo=timezone.utc)):
            take = min(need, g[2])
            g[2] -= take
            need -= take
            if not need:
                break
    return sum(g[2] for g in grants if g[1] is None or g[1] > now)


def charge(db: Session, org_id: str | None, operation: str, *, project_id: str | None = None, ref: str = "") -> int:
    """Writes the spend of one AI operation; returns credits charged (0 when the operation is free or unknown)."""
    if not org_id:
        return 0
    n = cost(db, operation)
    if n <= 0:
        return 0
    db.add(m.CreditEntry(org_id=org_id, delta=-n, reason="spend", operation=operation, project_id=project_id, ref=ref))
    return n


def check(db: Session, org_id: str | None, operation: str) -> None:
    """Refuses an operation at an insufficient balance — only when the platform switched enforcement on."""
    from .tariffs import get_tariffs, org_plan

    if not org_id or not get_tariffs(db).credits_enforced:
        return
    org = db.get(m.Organization, org_id)
    if not org or org_plan(db, org) is None:  # pilot organisations without a plan are not limited
        return
    need, have = cost(db, operation), balance(db, org_id)
    if need and have < need:
        raise NoCredits(have, need)


def month_end(now: datetime) -> datetime:
    nxt = (now.replace(day=28) + timedelta(days=4)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return nxt


def grant_plan_month(db: Session, org: m.Organization, now: datetime | None = None) -> bool:
    """Monthly plan credits (expire at the end of the month); once per organisation and month."""
    from .tariffs import org_plan

    now = now or datetime.now(timezone.utc)
    plan = org_plan(db, org)
    if not plan or not plan.ai_credits_month or plan.price_amd_month == 0:
        return False
    return grant(db, org.id, plan.ai_credits_month, "grant_plan", ref=plan.key, expires_at=month_end(now),
                 idempotency_key=f"plan:{org.id}:{now:%Y-%m}")


def ledger(db: Session, org_id: str, limit: int = 100) -> list[dict]:
    rows = db.scalars(select(m.CreditEntry).where(m.CreditEntry.org_id == org_id).order_by(m.CreditEntry.created_at.desc()).limit(limit))
    return [{"at": r.created_at.isoformat() if r.created_at else None, "delta": r.delta, "reason": r.reason, "operation": r.operation, "project_id": r.project_id,
             "expires_at": r.expires_at.isoformat() if r.expires_at else None} for r in rows]
