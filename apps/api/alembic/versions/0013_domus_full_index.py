"""Domus: full-catalogue background index (owner decision 2026-10-23)

Data migration: per-need live discovery stays; in addition the whole product sitemap
(sitemap index → 72 pages) is indexed in batches on the catalogue worker.

Revision ID: 0013_domus_full_index
Revises: 0012_custom_furniture
"""
import sqlalchemy as sa
from alembic import op

revision = "0013_domus_full_index"
down_revision = "0012_custom_furniture"
branch_labels = None
depends_on = None

src = sa.table("external_sources", sa.column("key", sa.String), sa.column("policy", sa.JSON))
KEYS = ("background_index", "child_sitemap_regex", "product_url_regex", "index_batch", "index_interval_min", "max_bytes")


def _policy(bind) -> dict:
    import json

    row = bind.execute(sa.select(src.c.policy).where(src.c.key == "domus")).first()
    pol = row[0] if row else None
    return (json.loads(pol) if isinstance(pol, str) else dict(pol or {})) if row else {}


def upgrade() -> None:
    from app.catalog.sources import SOURCES

    bind = op.get_bind()
    pol = _policy(bind)
    audited = next(s for s in SOURCES if s["key"] == "domus")["policy"]
    pol.update({k: audited[k] for k in KEYS})
    op.execute(src.update().where(src.c.key == "domus").values(policy=pol))


def downgrade() -> None:
    bind = op.get_bind()
    pol = {k: v for k, v in _policy(bind).items() if k not in KEYS}
    op.execute(src.update().where(src.c.key == "domus").values(policy=pol))
