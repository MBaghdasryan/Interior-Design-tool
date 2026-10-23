"""Business model: tariffs are configuration, not code. They live in `platform_settings["tariffs"]`; until the owner
saves an edited catalogue, the defaults below apply — they are the owner's commercial model v1.0
(docs/Renovara_Pricing_Monetization_and_Partner_Agreement_RU.docx, October 2026). Revenue is read back from the ledger."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m

STREAMS = ("subscription", "credits", "commission", "procurement", "manufacturer", "leads", "white_label", "exports")
Audience = Literal["designer", "bureau", "enterprise", "white_label", "supplier", "manufacturer"]


class Plan(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,30}$")
    name: str = Field(min_length=1, max_length=60)
    audience: Audience = "bureau"
    price_amd_month: int = Field(ge=0)
    price_amd_year: int | None = Field(default=None, ge=0)
    price_from: bool = False  # «from N AMD»: final price by contract
    custom: bool = False  # sold by contract only — no online checkout
    setup_amd: int | None = Field(default=None, ge=0)
    max_projects: int | None = Field(default=None, ge=1)  # None = unlimited / by contract
    seats: int | None = Field(default=None, ge=1)
    extra_seat_amd: int | None = Field(default=None, ge=0)
    storage_gb: float | None = Field(default=None, ge=0)
    ai_credits_month: int = Field(default=0, ge=0)
    ai_credits_once: int = Field(default=0, ge=0)  # Free: one-off grant
    renders_month: int = Field(default=0, ge=0)
    max_render: str = ""  # preview | 2K | 4K
    sku_limit: int | None = Field(default=None, ge=1)  # suppliers / manufacturers
    commission_pct: float | None = Field(default=None, ge=0, le=50)
    designer_reward_pct: float | None = Field(default=None, ge=0, le=50)
    features: list[str] = []  # feature codes, translated in the UI (price.f.<code>)


class CreditPack(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,30}$")
    credits: int = Field(gt=0)
    price_amd: int = Field(ge=0)
    validity_months: int = Field(default=12, ge=1, le=36)


class StorageAddon(BaseModel):
    key: str = Field(pattern=r"^[a-z0-9_]{2,30}$")
    gb: int = Field(gt=0)
    price_amd_month: int | None = Field(default=None, ge=0)  # None = individual


class Trial(BaseModel):
    days: int = Field(default=14, ge=0, le=60)
    credits: int = Field(default=50, ge=0)
    max_projects: int = Field(default=3, ge=1)


class Fee(BaseModel):
    mode: Literal["pct", "fixed", "off"] = "off"
    value: float = Field(default=0, ge=0)


class Tariffs(BaseModel):
    version: str = "1.0 (2026-10)"
    bureau_plans: list[Plan] = []  # designer, bureau, enterprise and white-label plans (bureau organisations)
    supplier_plans: list[Plan] = []  # supplier and manufacturer plans (supplier organisations)
    credit_packs: list[CreditPack] = []
    storage_addons: list[StorageAddon] = []
    credit_costs: dict[str, int] = {}  # AI operation → credits
    trial: Trial = Trial()
    credits_enforced: bool = False  # refuse paid AI operations at zero balance (off for the pilot)
    default_plan: str | None = None  # plan of new organisations; None = pilot without limits
    referral_reward_pct: float = Field(default=0, ge=0, le=50)  # partner reward on referred organisations' platform payments; 0 = terms not published yet
    partner_commission_default_pct: float = Field(default=0, ge=0, le=50)  # per-supplier value overrides
    procurement_fee: Fee = Fee()
    manufacturer: Fee = Fee()  # pct = per SKU per month (AMD), fixed = monthly subscription
    lead_fee_amd: int = Field(default=0, ge=0)
    white_label_setup_amd: int = Field(default=0, ge=0)
    white_label_license_amd_month: int = Field(default=0, ge=0)
    export_prices_amd: dict[str, int] = {}  # album_pdf | dwg | ifc → price per production export


def _p(key, name, audience, month, **kw) -> Plan:
    return Plan(key=key, name=name, audience=audience, price_amd_month=month, **kw)


DEFAULT_TARIFFS = Tariffs(
    bureau_plans=[
        _p("free", "Free", "designer", 0, seats=1, max_projects=1, storage_gb=0.35, ai_credits_once=10, max_render="preview", features=["watermark", "preview_pdf", "share_1"]),
        _p("designer_start", "Designer Start", "designer", 5000, price_amd_year=50000, seats=1, max_projects=10, storage_gb=2, ai_credits_month=50, max_render="2K",
           features=["exports_basic", "dxf_glb_5", "approvals"]),
        _p("designer_pro", "Designer Pro", "designer", 12000, price_amd_year=120000, seats=1, extra_seat_amd=5000, max_projects=30, storage_gb=15, ai_credits_month=150,
           max_render="4K", features=["exports_pro", "ifc_bcf_5", "rfq_versions", "branded_album"]),
        _p("bureau", "Bureau", "bureau", 49900, price_amd_year=499000, seats=5, extra_seat_amd=7900, max_projects=100, storage_gb=100, ai_credits_month=700,
           max_render="4K", features=["roles", "tasks", "procurement", "margin_reports", "exports_full", "bureau_stamp", "designer_commission"]),
        _p("enterprise", "Enterprise", "enterprise", 199000, price_from=True, custom=True, seats=10, storage_gb=500, ai_credits_month=3000,
           features=["sso", "sla", "api", "isolation", "onboarding"]),
        _p("white_label", "White Label", "white_label", 299000, price_from=True, custom=True, setup_amd=1500000, storage_gb=1000, ai_credits_month=5000,
           features=["own_domain", "own_brand", "client_tariffs", "revenue_share"]),
    ],
    supplier_plans=[
        _p("supplier_mini", "Supplier Mini", "supplier", 5000, sku_limit=20, storage_gb=0.1, seats=1, commission_pct=12, designer_reward_pct=3, features=["manual"]),
        _p("supplier_start", "Supplier Start", "supplier", 10000, sku_limit=100, storage_gb=0.5, seats=2, commission_pct=10, designer_reward_pct=3, features=["csv"]),
        _p("supplier_growth", "Supplier Growth", "supplier", 20000, sku_limit=500, storage_gb=2, seats=3, commission_pct=8, designer_reward_pct=2.5, features=["feed"]),
        _p("supplier_pro", "Supplier Pro", "supplier", 39900, sku_limit=2000, storage_gb=10, seats=5, commission_pct=6, designer_reward_pct=2, features=["api", "stock", "variants_3d", "analytics"]),
        _p("supplier_enterprise", "Supplier Enterprise", "supplier", 79900, price_from=True, custom=True, sku_limit=10000, storage_gb=50, seats=10, commission_pct=6,
           features=["api", "stock", "variants_3d", "analytics", "volume_terms"]),
        _p("manufacturer_start", "Manufacturer Start", "manufacturer", 0, sku_limit=50, commission_pct=15, designer_reward_pct=5, features=["rfq", "basic_analytics"]),
        _p("manufacturer_pro", "Manufacturer Pro", "manufacturer", 39900, sku_limit=1000, commission_pct=10, designer_reward_pct=5, features=["variants", "api", "rfq_priority"]),
    ],
    credit_packs=[CreditPack(key="c100", credits=100, price_amd=1490), CreditPack(key="c500", credits=500, price_amd=5900),
                  CreditPack(key="c2000", credits=2000, price_amd=19900), CreditPack(key="c10000", credits=10000, price_amd=79000)],
    storage_addons=[StorageAddon(key="s2", gb=2, price_amd_month=990), StorageAddon(key="s10", gb=10, price_amd_month=2900),
                    StorageAddon(key="s50", gb=50, price_amd_month=7900), StorageAddon(key="s100", gb=100, price_amd_month=12900), StorageAddon(key="s500", gb=500)],
    credit_costs={"text_command": 1, "plan_ocr": 5, "photo_analysis": 5, "layout_variant": 8, "image_flash_1k": 10, "image_flash_2k": 15, "image_flash_4k": 25,
                  "image_pro_2k": 25, "image_pro_4k": 45, "grounded_render": 30, "panorama": 50, "album": 5},
)


def get_tariffs(db: Session) -> Tariffs:
    row = db.get(m.PlatformSetting, "tariffs")
    if not row or not row.value:
        return DEFAULT_TARIFFS.model_copy(deep=True)
    # catalogues saved before v1.0 had only bureau plans: fill new sections from the defaults
    merged = {**DEFAULT_TARIFFS.model_dump(), **{k: v for k, v in row.value.items() if v not in (None, [], {}) or k in ("default_plan",)}}
    return Tariffs.model_validate(merged)


def set_tariffs(db: Session, t: Tariffs) -> Tariffs:
    keys = [p.key for p in t.bureau_plans + t.supplier_plans]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate plan key")
    row = db.get(m.PlatformSetting, "tariffs") or m.PlatformSetting(key="tariffs", value={})
    row.value = t.model_dump()
    db.merge(row)
    return t


def all_plans(t: Tariffs) -> list[Plan]:
    return t.bureau_plans + t.supplier_plans


def plans_for(t: Tariffs, org_kind: str) -> list[Plan]:
    return t.supplier_plans if org_kind == "supplier" else t.bureau_plans


def _aware(d: datetime | str | None) -> datetime | None:
    if isinstance(d, str):
        d = datetime.fromisoformat(d)
    return d.replace(tzinfo=timezone.utc) if d and d.tzinfo is None else d


def org_plan(db: Session, org: m.Organization) -> Plan | None:
    """Active plan of an organisation. A paid plan whose period ended falls back to Free; a plan assigned by the
    platform without a paid period (invoice, pilot agreement) stays active; no plan = pilot without limits."""
    st = org.settings or {}
    t = get_tariffs(db)
    key = st.get("plan")
    if not key:
        return None
    paid_until = _aware(st.get("paid_until"))
    if paid_until and paid_until < datetime.now(timezone.utc):
        key = "free"
    trial_until = _aware(st.get("trial_until"))
    plan = next((p for p in all_plans(t) if p.key == key), None)
    if plan and trial_until and trial_until > datetime.now(timezone.utc) and plan.key == "free":
        return plan.model_copy(update={"max_projects": t.trial.max_projects, "max_render": "2K"})
    return plan


def storage_bytes(db: Session, org: m.Organization) -> int:
    if org.kind == "supplier":
        sup_ids = select(m.Supplier.id).where(m.Supplier.org_id == org.id)
        return int(db.scalar(select(func.coalesce(func.sum(m.SupplierAsset.size), 0)).where(m.SupplierAsset.supplier_id.in_(sup_ids))) or 0)
    pids = select(m.Project.id).where(m.Project.org_id == org.id)
    a = db.scalar(select(func.coalesce(func.sum(m.SourceAsset.size), 0)).where(m.SourceAsset.project_id.in_(pids), m.SourceAsset.scan_status != "purged")) or 0
    d = db.scalar(select(func.coalesce(func.sum(m.Document.size), 0)).where(m.Document.project_id.in_(pids))) or 0
    return int(a) + int(d)


def sku_count(db: Session, org: m.Organization) -> int:
    sup_ids = select(m.Supplier.id).where(m.Supplier.org_id == org.id)
    return db.scalar(select(func.count(m.ProductVariant.id)).join(m.Product).where(m.Product.supplier_id.in_(sup_ids), m.Product.status == "active")) or 0


def seat_limit(org: m.Organization, plan: Plan | None) -> int | None:
    if not plan or plan.seats is None:
        return None
    return plan.seats + int((org.settings or {}).get("extra_seats", 0))


def plan_usage(db: Session, org: m.Organization) -> dict:
    from .credits import balance

    plan = org_plan(db, org)
    st = org.settings or {}
    projects = db.scalar(select(func.count(m.Project.id)).where(m.Project.org_id == org.id, m.Project.status != "archived")) or 0
    seats = db.scalar(select(func.count(func.distinct(m.Membership.user_id))).where(m.Membership.org_id == org.id)) or 0
    usage = {"projects": projects, "seats": seats, "storage_bytes": storage_bytes(db, org), "credits": balance(db, org.id)}
    if org.kind == "supplier":
        usage["skus"] = sku_count(db, org)
    return {"plan": plan.model_dump() if plan else None, "usage": usage, "seat_limit": seat_limit(org, plan),
            "interval": st.get("interval"), "paid_until": st.get("paid_until"), "trial_until": st.get("trial_until"), "trial_used": bool(st.get("trial_used")),
            "assigned_by_platform": bool(st.get("plan")) and not st.get("paid_until")}


def check_project_quota(db: Session, org_id: str) -> None:
    from ..errors import ApiError

    org = db.get(m.Organization, org_id)
    plan = org_plan(db, org) if org else None
    if plan and plan.max_projects is not None:
        n = db.scalar(select(func.count(m.Project.id)).where(m.Project.org_id == org_id, m.Project.status != "archived")) or 0
        if n >= plan.max_projects:
            raise ApiError(402, "plan.project_limit", limit=plan.max_projects, plan=plan.name)


def check_seat_quota(db: Session, org: m.Organization) -> None:
    from ..errors import ApiError

    lim = seat_limit(org, org_plan(db, org))
    if lim is not None:
        n = db.scalar(select(func.count(func.distinct(m.Membership.user_id))).where(m.Membership.org_id == org.id)) or 0
        if n >= lim:
            raise ApiError(402, "plan.seat_limit", limit=lim)


def check_sku_quota(db: Session, supplier: m.Supplier, adding: int = 1) -> None:
    from ..errors import ApiError

    org = db.get(m.Organization, supplier.org_id) if supplier.org_id else None
    plan = org_plan(db, org) if org else None
    if plan and plan.sku_limit is not None and sku_count(db, org) + adding > plan.sku_limit:
        raise ApiError(402, "plan.sku_limit", limit=plan.sku_limit, plan=plan.name)


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
