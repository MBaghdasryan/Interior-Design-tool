"""Business model (P2-2): every revenue stream is configuration, not code. Tariffs live in
`platform_settings["tariffs"]`; revenue is read back from the ledger (`revenue:<stream>`).
Defaults are empty — the platform owner sets real prices in the admin; nothing is invented."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m

STREAMS = ("subscription", "credits", "commission", "procurement", "manufacturer", "leads", "white_label", "exports")


class Plan(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,30}$")
    name: str = Field(min_length=1, max_length=60)
    price_amd_month: int = Field(ge=0)
    max_projects: int | None = Field(default=None, ge=1)  # None = unlimited
    seats: int | None = Field(default=None, ge=1)
    ai_credits_month: int = Field(default=0, ge=0)
    renders_month: int = Field(default=0, ge=0)


class CreditPack(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,30}$")
    credits: int = Field(gt=0)
    price_amd: int = Field(ge=0)


class Fee(BaseModel):
    mode: Literal["pct", "fixed", "off"] = "off"
    value: float = Field(default=0, ge=0)


class Tariffs(BaseModel):
    bureau_plans: list[Plan] = []
    credit_packs: list[CreditPack] = []
    partner_commission_default_pct: float = Field(default=0, ge=0, le=50)  # per-supplier value overrides
    procurement_fee: Fee = Fee()
    manufacturer: Fee = Fee()  # pct = per SKU per month (AMD), fixed = monthly subscription
    lead_fee_amd: int = Field(default=0, ge=0)
    white_label_setup_amd: int = Field(default=0, ge=0)
    white_label_license_amd_month: int = Field(default=0, ge=0)
    export_prices_amd: dict[str, int] = {}  # album_pdf | dwg | ifc → price per production export


def get_tariffs(db: Session) -> Tariffs:
    row = db.get(m.PlatformSetting, "tariffs")
    return Tariffs.model_validate(row.value if row else {})


def set_tariffs(db: Session, t: Tariffs) -> Tariffs:
    keys = [p.key for p in t.bureau_plans]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate plan key")
    row = db.get(m.PlatformSetting, "tariffs") or m.PlatformSetting(key="tariffs", value={})
    row.value = t.model_dump()
    db.merge(row)
    return t


def org_plan(db: Session, org: m.Organization) -> Plan | None:
    key = (org.settings or {}).get("plan")
    return next((p for p in get_tariffs(db).bureau_plans if p.key == key), None) if key else None


def plan_usage(db: Session, org: m.Organization) -> dict:
    plan = org_plan(db, org)
    projects = db.scalar(select(func.count(m.Project.id)).where(m.Project.org_id == org.id, m.Project.status != "archived")) or 0
    seats = db.scalar(select(func.count(m.Membership.id)).where(m.Membership.org_id == org.id)) or 0
    return {"plan": plan.model_dump() if plan else None, "usage": {"projects": projects, "seats": seats}}


def check_project_quota(db: Session, org_id: str) -> None:
    from ..errors import ApiError

    org = db.get(m.Organization, org_id)
    plan = org_plan(db, org) if org else None
    if plan and plan.max_projects is not None:
        n = db.scalar(select(func.count(m.Project.id)).where(m.Project.org_id == org_id, m.Project.status != "archived")) or 0
        if n >= plan.max_projects:
            raise ApiError(402, "plan.project_limit", limit=plan.max_projects, plan=plan.name)


def revenue_report(db: Session) -> dict:
    """Revenue per stream and per month, from posted ledger entries only."""
    from collections import defaultdict

    by_month: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    totals: dict[str, int] = defaultdict(int)
    for e in db.scalars(select(m.LedgerEntry).where(m.LedgerEntry.account.like("revenue:%"))):
        stream = e.account.split(":", 1)[1]
        amount = int(e.credit) - int(e.debit)
        by_month[e.created_at.strftime("%Y-%m")][stream] += amount
        totals[stream] += amount
    return {"streams": list(STREAMS), "totals": {s: totals.get(s, 0) for s in STREAMS} | {k: v for k, v in totals.items() if k not in STREAMS},
            "by_month": {k: dict(v) for k, v in sorted(by_month.items())}}
