"""Per-organisation AI cost limits (daily / monthly, USD). Spend is the sum of logged
AIUsage.cost_usd — an estimate from token/image counts and the configured price table
(AI_PRICES), not a provider invoice. Limits: Organization.settings["ai_budget"] or the
defaults AI_ORG_DAILY_USD / AI_ORG_MONTHLY_USD (0 = unlimited)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings


class QuotaExceeded(Exception):
    def __init__(self, period: str, spent: float, limit: float):
        super().__init__(f"AI {period} budget exhausted: {spent:.2f} / {limit:.2f} USD")
        self.period, self.spent, self.limit = period, spent, limit


def org_of_project(db: Session, project_id: str | None) -> str | None:
    if not project_id:
        return None
    p = db.get(m.Project, project_id)
    return p.org_id if p else None


def limits(db: Session, org_id: str) -> dict[str, float]:
    s = get_settings()
    org = db.get(m.Organization, org_id)
    b = ((org.settings or {}).get("ai_budget") if org else None) or {}
    return {"daily_usd": float(b.get("daily_usd", s.ai_org_daily_usd)), "monthly_usd": float(b.get("monthly_usd", s.ai_org_monthly_usd))}


def spent(db: Session, org_id: str, since: datetime) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(m.AIUsage.cost_usd), 0.0)).where(m.AIUsage.org_id == org_id, m.AIUsage.created_at >= since)) or 0.0)


def periods(now: datetime | None = None) -> dict[str, datetime]:
    now = now or datetime.now(timezone.utc)
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {"daily": day, "monthly": day.replace(day=1)}


def check(db: Session, org_id: str | None) -> None:
    if not org_id:
        return
    lim = limits(db, org_id)
    for period, since in periods().items():
        cap = lim[f"{period}_usd"]
        if cap and (used := spent(db, org_id, since)) >= cap:
            raise QuotaExceeded(period, used, cap)


def project_cost(db: Session, project_id: str) -> dict:
    """AI spend of one project — the variable AI part of its unit cost."""
    rows = db.execute(select(m.AIUsage.task, func.count(), func.coalesce(func.sum(m.AIUsage.cost_usd), 0.0))
                      .where(m.AIUsage.project_id == project_id, m.AIUsage.provider != "stub").group_by(m.AIUsage.task)).all()
    return {"total_usd": round(sum(r[2] for r in rows), 4), "calls": sum(r[1] for r in rows),
            "by_task": [{"task": r[0], "calls": r[1], "cost_usd": round(r[2], 4)} for r in sorted(rows, key=lambda r: -r[2])]}


def platform_costs(db: Session) -> dict:
    """Unit economics for the platform admin: AI cost per project (average, median) and per organisation."""
    per_project = db.execute(select(m.AIUsage.project_id, func.count(), func.sum(m.AIUsage.cost_usd)).where(m.AIUsage.project_id.isnot(None), m.AIUsage.provider != "stub")
                             .group_by(m.AIUsage.project_id)).all()
    titles = {p.id: (p.title, p.org_id) for p in db.scalars(select(m.Project).where(m.Project.id.in_([r[0] for r in per_project])))} if per_project else {}
    orgs = {o.id: o.name for o in db.scalars(select(m.Organization))}
    costs = sorted(float(r[2] or 0) for r in per_project if r[0] in titles)
    by_org = db.execute(select(m.AIUsage.org_id, func.count(), func.sum(m.AIUsage.cost_usd)).where(m.AIUsage.provider != "stub").group_by(m.AIUsage.org_id)).all()
    unattributed = db.scalar(select(func.coalesce(func.sum(m.AIUsage.cost_usd), 0.0)).where(m.AIUsage.project_id.is_(None), m.AIUsage.provider != "stub")) or 0.0
    return {"projects_with_ai": len(costs), "avg_per_project_usd": round(sum(costs) / len(costs), 4) if costs else 0.0,
            "median_per_project_usd": round(__import__("statistics").median(costs), 4) if costs else 0.0, "max_per_project_usd": round(costs[-1], 4) if costs else 0.0,
            "projects": [{"project_id": r[0], "title": titles[r[0]][0], "org": orgs.get(titles[r[0]][1], ""), "calls": r[1], "cost_usd": round(float(r[2] or 0), 4)}
                         for r in sorted(per_project, key=lambda r: -(r[2] or 0)) if r[0] in titles][:50],
            "by_org": [{"org": orgs.get(r[0], "—") if r[0] else "—", "calls": r[1], "cost_usd": round(float(r[2] or 0), 4)} for r in sorted(by_org, key=lambda r: -(r[2] or 0))],
            "unattributed_usd": round(unattributed, 4)}


def summary(db: Session, org_id: str) -> dict:
    lim = limits(db, org_id)
    p = periods()
    rows = db.execute(select(m.AIUsage.task, m.AIUsage.provider, func.count(), func.coalesce(func.sum(m.AIUsage.cost_usd), 0.0))
                      .where(m.AIUsage.org_id == org_id, m.AIUsage.created_at >= p["monthly"]).group_by(m.AIUsage.task, m.AIUsage.provider)).all()
    return {"limits": lim, "today_usd": round(spent(db, org_id, p["daily"]), 4), "month_usd": round(spent(db, org_id, p["monthly"]), 4),
            "by_task": [{"task": t, "provider": pr, "calls": n, "cost_usd": round(c, 4)} for t, pr, n, c in rows],
            "note": "estimate from token/image counts × AI_PRICES"}
