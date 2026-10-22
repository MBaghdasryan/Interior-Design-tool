"""Relational model. Geometry lives in versioned scene documents (JSON, millimetres)
— see app/scene/model.py — everything commercial is relational so it can be
queried, audited and snapshotted. Full target ERD: docs/ERD.md."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- identity / tenancy
class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))  # platform | bureau | supplier | client
    # Title-block / white-label settings used by the album generator
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(300))
    locale: Mapped[str] = mapped_column(String(5), default="ru")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | deletion_pending | deleted
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {"terms": {"version": "2026-10", "at": iso}, "marketing": {...}} — consent records (privacy)
    consents: Mapped[dict] = mapped_column(JSON, default=dict)
    # MFA (TOTP): secrets are encrypted with a key derived from SECRET_KEY; backup codes stored as SHA-256
    mfa_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_pending_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    mfa_enabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_backup_codes: Mapped[list] = mapped_column(JSON, default=list)
    # account deletion with a grace period (privacy): purged by the worker after this moment
    deletion_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # {"kinds": {"job": true, ...}, "email_digest": true, "digest_sent_at": iso}
    notification_prefs: Mapped[dict] = mapped_column(JSON, default=dict)
    memberships: Mapped[list[Membership]] = relationship(back_populates="user", lazy="selectin")


class AuthSession(TimestampMixin, Base):
    """Server-side session: the signed cookie/bearer token carries `sid`; revoking the row kills the token."""
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthToken(TimestampMixin, Base):
    """One-time token (email verification, password reset). Only the SHA-256 of the token is stored."""
    __tablename__ = "auth_tokens"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(30))  # verify_email | password_reset
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "org_id", "role"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    # platform_admin | platform_ops | client | collaborator | designer | bureau_admin
    # supplier_admin | supplier_catalog | manufacturer | installer | verifier
    role: Mapped[str] = mapped_column(String(30))
    user: Mapped[User] = relationship(back_populates="memberships")
    org: Mapped[Organization] = relationship(lazy="joined")


# ---------------------------------------------------------------- projects
class Project(TimestampMixin, Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(100), default="Ереван")
    property_type: Mapped[str] = mapped_column(String(30), default="apartment")
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    renovation_stage: Mapped[str] = mapped_column(String(30), default="shell")  # shell | white_box | lived_in
    # concept | verified | production — see docs/PRODUCT.md §Accuracy
    accuracy_level: Mapped[str] = mapped_column(String(20), default="concept")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    brief: Mapped[dict] = mapped_column(JSON, default=dict)
    product_source: Mapped[str] = mapped_column(String(20), default="external")  # external | own | concept
    external_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    client_name: Mapped[str] = mapped_column(String(200), default="")
    designer_name: Mapped[str] = mapped_column(String(200), default="")
    doc_lang: Mapped[str] = mapped_column(String(5), default="hy")
    share_token: Mapped[str] = mapped_column(String(64), default=lambda: secrets.token_urlsafe(18), unique=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SourceAsset(TimestampMixin, Base):
    __tablename__ = "source_assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    # photo | video | plan_pdf | plan_image | dwg | dxf | ifc | rvt | lidar | render
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(400))
    room_hint: Mapped[str | None] = mapped_column(String(50), nullable=True)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    aps: Mapped[dict] = mapped_column(JSON, default=dict)  # {objectId, urn, status, progress}
    scan_status: Mapped[str] = mapped_column(String(20), default="not_scanned")  # clean | not_scanned | purged


class Measurement(TimestampMixin, Base):
    __tablename__ = "measurements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    wall_id: Mapped[str] = mapped_column(String(40))
    measured_mm: Mapped[float] = mapped_column(Float)
    note: Mapped[str] = mapped_column(String(300), default="")
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class BaseScene(TimestampMixin, Base):
    """Recognised / confirmed as-built geometry (BuildingGraph), versioned."""

    __tablename__ = "base_scenes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class DesignVariant(TimestampMixin, Base):
    __tablename__ = "design_variants"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(120))
    subtitle: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    style: Mapped[str] = mapped_column(String(40))
    tier: Mapped[str] = mapped_column(String(20))  # economy | comfort | business | premium
    mode: Mapped[str] = mapped_column(String(20), default="real")  # real | concept
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | selected | approved
    palette: Mapped[list] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    current_version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cover_image: Mapped[str | None] = mapped_column(String(400), nullable=True)


class DesignVersion(TimestampMixin, Base):
    __tablename__ = "design_versions"
    __table_args__ = (UniqueConstraint("variant_id", "number"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    variant_id: Mapped[str] = mapped_column(ForeignKey("design_variants.id", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scene: Mapped[dict] = mapped_column(JSON)
    estimate: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    change_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="ai")  # ai | manual | command | restore
    created_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)  # approved versions are immutable


# ---------------------------------------------------------------- jobs / AI
class GenerationJob(TimestampMixin, Base):
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # pipeline | recognize | album | aps_translate | aps_dwg | catalog_refresh
    status: Mapped[str] = mapped_column(String(20), default="queued")
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True, nullable=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    counters: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    steps: Mapped[list[GenerationStep]] = relationship(order_by="GenerationStep.order", lazy="selectin", cascade="all, delete-orphan")


class GenerationStep(Base):
    __tablename__ = "generation_steps"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id", ondelete="CASCADE"), index=True)
    order: Mapped[int] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    phase: Mapped[str] = mapped_column(String(30), default="design")  # catalog | design
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | running | done | warning | failed | skipped
    detail: Mapped[str] = mapped_column(Text, default="")
    # structured detail for client-side localisation: template "steps.<key>" + params
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIUsage(TimestampMixin, Base):
    __tablename__ = "ai_usage"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # budget accounting
    trace_id: Mapped[str | None] = mapped_column(String(16), nullable=True)
    task: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    prompt_version: Mapped[str] = mapped_column(String(30))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------- catalog / PIM
class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    website: Mapped[str] = mapped_column(String(300), default="")
    city: Mapped[str] = mapped_column(String(100), default="Ереван")
    kind: Mapped[str] = mapped_column(String(20), default="store")  # store | manufacturer | installer
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    contacts: Mapped[dict] = mapped_column(JSON, default=dict)
    delivery: Mapped[dict] = mapped_column(JSON, default=dict)  # {fee_amd, days_min, days_max, regions}
    installation: Mapped[dict] = mapped_column(JSON, default=dict)
    commission_pct: Mapped[float] = mapped_column(Float, default=0.0)
    external_source_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), index=True)
    brand: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(50), index=True)  # normalized taxonomy key
    # serial | made_to_order | parametric | service | material | kit | custom
    item_type: Mapped[str] = mapped_column(String(20), default="serial")
    name_ru: Mapped[str] = mapped_column(String(300))
    name_hy: Mapped[str] = mapped_column(String(300), default="")
    name_en: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    styles: Mapped[list] = mapped_column(JSON, default=list)
    tier: Mapped[str] = mapped_column(String(20), default="comfort")
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    # material-only fields (tile, parquet, paint, wallpaper)
    unit: Mapped[str] = mapped_column(String(10), default="pcs")  # pcs | m2 | pack | l | kg | m
    package_coverage_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    waste_pct: Mapped[float] = mapped_column(Float, default=0.0)
    parametric: Mapped[dict] = mapped_column(JSON, default=dict)  # ranges, price formula, lead time
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    variants: Mapped[list[ProductVariant]] = relationship(back_populates="product", lazy="selectin", cascade="all, delete-orphan")
    supplier: Mapped[Supplier] = relationship(lazy="joined")


class ProductVariant(TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (UniqueConstraint("product_id", "sku"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(120))
    color: Mapped[str] = mapped_column(String(80), default="")
    color_hex: Mapped[str] = mapped_column(String(9), default="#cccccc")
    material: Mapped[str] = mapped_column(String(120), default="")
    width_mm: Mapped[float] = mapped_column(Float, default=0)
    depth_mm: Mapped[float] = mapped_column(Float, default=0)
    height_mm: Mapped[float] = mapped_column(Float, default=0)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="AMD")
    old_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    # confirmed | estimated | quote_required | demo
    price_status: Mapped[str] = mapped_column(String(20), default="estimated")
    stock_status: Mapped[str] = mapped_column(String(20), default="unknown")  # in_stock | to_order | out_of_stock | unknown
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    availability_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    url: Mapped[str] = mapped_column(String(500), default="")
    image_url: Mapped[str] = mapped_column(String(500), default="")
    model3d_url: Mapped[str] = mapped_column(String(500), default="")
    product: Mapped[Product] = relationship(back_populates="variants")


class PriceHistory(Base):
    __tablename__ = "price_history"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    variant_id: Mapped[str] = mapped_column(ForeignKey("product_variants.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(50))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# ---------------------------------------------------------------- external catalog discovery
class ExternalSource(TimestampMixin, Base):
    __tablename__ = "external_sources"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    domain: Mapped[str] = mapped_column(String(200))
    # normalized host without scheme/www — the idempotency key of the seed (unique)
    canonical_domain: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    connector_type: Mapped[str] = mapped_column(String(30), default="jsonld_sitemap")  # jsonld_sitemap | feed | rfq | manual
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)  # per-source opt-in (also needs EXTERNAL_FETCH_LIVE)
    policy_status: Mapped[str] = mapped_column(String(30), default="pending")  # approved | pending | restricted
    health_status: Mapped[str] = mapped_column(String(30), default="unknown")
    allowed_hosts: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    languages: Mapped[list] = mapped_column(JSON, default=list)
    method: Mapped[str] = mapped_column(String(30))  # api | feed | jsonld_sitemap | html | manual | rfq
    connector_status: Mapped[str] = mapped_column(String(20), default="needs_audit")
    policy: Mapped[dict] = mapped_column(JSON, default=dict)
    rate_limit_s: Mapped[float] = mapped_column(Float, default=3.0)
    ttl_h: Mapped[dict] = mapped_column(JSON, default=dict)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExternalConnectorRun(TimestampMixin, Base):
    __tablename__ = "external_connector_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("external_sources.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # discovery | refresh | health
    status: Mapped[str] = mapped_column(String(20))
    found: Mapped[int] = mapped_column(Integer, default=0)
    validated: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)


class ExternalProductRecord(TimestampMixin, Base):
    __tablename__ = "external_product_records"
    __table_args__ = (UniqueConstraint("source_id", "external_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    source_id: Mapped[str] = mapped_column(ForeignKey("external_sources.id", ondelete="CASCADE"), index=True)
    # external id / SKU when present, otherwise a controlled fingerprint (brand+model+variant)
    external_key: Mapped[str] = mapped_column(String(200))
    canonical_url: Mapped[str] = mapped_column(String(600))
    data: Mapped[dict] = mapped_column(JSON)  # NormalizedExternalProduct (see catalog/schema.py)
    price_amd: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalized_category: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    review_status: Mapped[str] = mapped_column(String(20), default="auto")  # auto | pending_review | approved | rejected
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectProductNeed(TimestampMixin, Base):
    __tablename__ = "project_product_needs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(50))
    room_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    qty: Mapped[float] = mapped_column(Float, default=1)
    unit: Mapped[str] = mapped_column(String(10), default="pcs")
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    budget_amd: Mapped[float | None] = mapped_column(Float, nullable=True)


class ProjectCatalogSnapshot(TimestampMixin, Base):
    __tablename__ = "project_catalog_snapshots"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    counters: Mapped[dict] = mapped_column(JSON, default=dict)
    items: Mapped[list[ProjectCatalogSnapshotItem]] = relationship(lazy="selectin", cascade="all, delete-orphan")


class ProjectCatalogSnapshotItem(Base):
    __tablename__ = "project_catalog_snapshot_items"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    snapshot_id: Mapped[str] = mapped_column(ForeignKey("project_catalog_snapshots.id", ondelete="CASCADE"), index=True)
    need_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    record_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    variant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # discovered | validated | selected | rejected | stale | unavailable | quote_required
    status: Mapped[str] = mapped_column(String(20), default="discovered")
    score: Mapped[float] = mapped_column(Float, default=0.0)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(400), default="")
    risk: Mapped[str] = mapped_column(String(400), default="")


# ---------------------------------------------------------------- commerce
class EstimateSnapshot(TimestampMixin, Base):
    __tablename__ = "estimate_snapshots"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[str] = mapped_column(String(32))
    version_id: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(String(20))  # approval | rfq | manual
    data: Mapped[dict] = mapped_column(JSON)


class RFQ(TimestampMixin, Base):
    __tablename__ = "rfqs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | sent | quoted | declined | expired
    items: Mapped[list] = mapped_column(JSON, default=list)
    message: Mapped[str] = mapped_column(Text, default="")
    quote: Mapped[dict] = mapped_column(JSON, default=dict)
    estimate_snapshot_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    supplier_name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="cart")  # cart | requested | confirmed | delivering | installed | cancelled
    items: Mapped[list] = mapped_column(JSON, default=list)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    delivery: Mapped[dict] = mapped_column(JSON, default=dict)
    installation: Mapped[dict] = mapped_column(JSON, default=dict)


class Comment(TimestampMixin, Base):
    __tablename__ = "comments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    author_name: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    anchor: Mapped[dict] = mapped_column(JSON, default=dict)  # {object_id} | {x, y} in mm
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[str] = mapped_column(String(32))
    version_id: Mapped[str] = mapped_column(String(32))
    actor_name: Mapped[str] = mapped_column(String(200))
    actor_role: Mapped[str] = mapped_column(String(30))
    decision: Mapped[str] = mapped_column(String(20))  # approved | rejected | changes_requested
    note: Mapped[str] = mapped_column(Text, default="")
    estimate_snapshot_id: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    variant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    version_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # album_pdf | dxf | dwg | xlsx | csv | glb | json
    lang: Mapped[str] = mapped_column(String(5), default="hy")
    filename: Mapped[str] = mapped_column(String(300))
    storage_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    size: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ready")  # pending | ready | failed
    meta: Mapped[dict] = mapped_column(JSON, default=dict)  # sheets, aps workitem, errors


class AuditEvent(TimestampMixin, Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    org_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Notification(TimestampMixin, Base):
    """In-app notification (bell) — localised on the client by `kind` + `params`; an e-mail digest
    collects unread ones. Never carries secrets or full personal data."""
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # job_done | job_failed | client_comment | client_approved | client_changes | rfq_reply | price_stale | catalog_alert
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    link: Mapped[str] = mapped_column(String(300), default="")
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    emailed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

