"""Idempotent seed: organisations, demo users per role, external source registry,
DEMO catalogue and one demo project. No personal data of real clients."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .catalog.demo_seed import DEMO_SUPPLIERS, demo_products
from .catalog.sources import DEFAULT_POLICY, SEED_POLICY, SOURCES, canonical_domain
from .scene.demo import demo_base_scene
from .scene.geometry import room_area_m2
from .security import hash_password

DEMO_PASSWORD = "demo1234"
DEMO_USERS = [
    ("admin@forma.local", "Администратор платформы", "platform", "platform_admin"),
    ("ops@forma.local", "Оператор каталога", "platform", "platform_ops"),
    ("designer@forma.local", "Ани Петросян", "bureau", "designer"),
    ("bureau@forma.local", "Руководитель бюро", "bureau", "bureau_admin"),
    ("supplier@forma.local", "Менеджер поставщика", "supplier", "supplier_admin"),
]


LEGACY_ORG_NAMES = {"Renovara Platform": "FORMA Platform"}


def seed(db: Session) -> None:
    orgs = {}
    for kind, name, settings in (
        ("platform", "Renovara Platform", {}),
        ("bureau", "Демо-бюро «Студия Форма»", {"title_block": {"company": "Studio Forma", "tagline": "interior design", "phone": "+374 00 000 000",
                                                                "address": "Երևան", "email": "studio@forma.local"}}),
        ("supplier", "Дом и стиль (DEMO)", {}),
    ):
        o = db.scalar(select(m.Organization).where(m.Organization.name == name))
        legacy = LEGACY_ORG_NAMES.get(name)
        if not o and legacy and (o := db.scalar(select(m.Organization).where(m.Organization.name == legacy))):
            o.name = name  # rebrand FORMA → Renovara without duplicating the org
        if not o:
            o = m.Organization(name=name, kind=kind, settings=settings)
            db.add(o)
            db.flush()
        orgs[kind] = o
    for email, name, org_kind, role in DEMO_USERS:
        u = db.scalar(select(m.User).where(m.User.email == email))
        if not u:
            u = m.User(email=email, name=name, password_hash=hash_password(DEMO_PASSWORD))
            db.add(u)
            db.flush()
            db.add(m.Membership(user_id=u.id, org_id=orgs[org_kind].id, role=role))
        # demo accounts are ready to use: no e-mail confirmation or onboarding wizard
        u.email_verified_at = u.email_verified_at or m.utcnow()
        u.onboarded_at = u.onboarded_at or m.utcnow()
    seed_external_sources(db)
    # demo catalogue
    if not db.scalar(select(m.Supplier).limit(1)):
        sup_ids = {}
        for slug, name, kind, delivery, inst in DEMO_SUPPLIERS:
            s = m.Supplier(name=name, slug=slug, kind=kind, delivery=delivery, installation=inst, is_demo=True,
                           org_id=orgs["supplier"].id if slug == "dom-i-stil" else None, commission_pct=5.0)
            db.add(s)
            db.flush()
            sup_ids[slug] = s.id
        for p in demo_products():
            prod = m.Product(supplier_id=sup_ids[p["supplier"]], brand=p["brand"], category=p["category"], item_type=p["item_type"],
                             name_ru=p["name_ru"], styles=p["styles"], tier=p["tier"], unit=p.get("unit", "pcs"),
                             package_coverage_m2=p.get("package_coverage_m2"), waste_pct=p.get("waste_pct", 0.0),
                             parametric=p.get("parametric", {}), is_demo=True)
            db.add(prod)
            db.flush()
            for v in p["variants"]:
                db.add(m.ProductVariant(product_id=prod.id, sku=v["sku"], color=v["color"], color_hex=v["color_hex"], material=v["material"],
                                        width_mm=v.get("width_mm", 0), depth_mm=v.get("depth_mm", 0), height_mm=v.get("height_mm", 0),
                                        price=v["price"], price_status=v["price_status"], stock_status=v["stock_status"], lead_time_days=v["lead_time_days"]))
        db.flush()
    # demo project
    designer = db.scalar(select(m.User).where(m.User.email == "designer@forma.local"))
    if not db.scalar(select(m.Project).where(m.Project.title == "Демо-квартира · 3 комнаты")):
        scene = demo_base_scene()
        proj = m.Project(org_id=orgs["bureau"].id, owner_id=designer.id, title="Демо-квартира · 3 комнаты", address="ул. Демонстрационная, 1",
                         area_m2=round(sum(room_area_m2(r) for r in scene.rooms if r.type != "balcony"), 1), accuracy_level="verified",
                         confidence=0.86, status="recognized", product_source="external", designer_name=designer.name,
                         preferences={"budget_tier": "comfort"}, external_settings={"sources": [], "city": "Ереван", "allow_quote": True})
        db.add(proj)
        db.flush()
        db.add(m.BaseScene(project_id=proj.id, version=1, data=scene.model_dump(mode="json"), confirmed=True))
    db.commit()


def seed_external_sources(db: Session) -> list[dict]:
    """Idempotent upsert keyed by canonical domain (DB unique constraint). Existing rows
    keep admin decisions (enabled/live flags); only missing seed fields are back-filled."""
    report = []
    for src in SOURCES:
        dom = canonical_domain(src["domain"])
        policy = {**DEFAULT_POLICY, "connector_type": {"rfq": "rfq", "jsonld_sitemap": "jsonld_sitemap", "jsonld_index": "jsonld_index"}.get(src["method"], "feed"), **SEED_POLICY.get(src["key"], {})}
        row = db.scalar(select(m.ExternalSource).where(m.ExternalSource.canonical_domain == dom)) or \
            db.scalar(select(m.ExternalSource).where(m.ExternalSource.key == src["key"]))
        fields = {k: v for k, v in src.items() if k not in ("priority",)}
        if not row:
            row = m.ExternalSource(**fields, canonical_domain=dom, ttl_h={"price": 24, "availability": 12, "specs": 168, "media": 720}, **policy)
            db.add(row)
            action = "created"
        else:
            action = "unchanged"
            if not row.canonical_domain:
                row.canonical_domain = dom
                row.connector_type = policy["connector_type"]
                row.live_enabled = policy["live_enabled"]
                row.policy_status = policy["policy_status"]
                row.enabled = policy["enabled"]
                action = "backfilled"
        report.append({"key": row.key, "domain": dom, "action": action})
    db.flush()
    return report
