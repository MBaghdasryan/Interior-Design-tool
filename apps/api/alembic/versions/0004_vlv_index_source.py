"""enable VLV as the second live source (background index, audit 2026-10-22)

Data migration: the idempotent seed keeps admin decisions on existing rows, so the
audited policy change for VLV is applied explicitly here (and reverted on downgrade).

Revision ID: 0004_vlv_index_source
Revises: 0003_auth_sessions
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0004_vlv_index_source"
down_revision = "0003_auth_sessions"
branch_labels = None
depends_on = None

src = sa.table("external_sources", sa.column("key", sa.String), sa.column("enabled", sa.Boolean), sa.column("live_enabled", sa.Boolean),
               sa.column("connector_type", sa.String), sa.column("policy_status", sa.String), sa.column("method", sa.String),
               sa.column("connector_status", sa.String), sa.column("categories", sa.JSON), sa.column("policy", sa.JSON), sa.column("notes", sa.Text))


def upgrade() -> None:
    from app.catalog.sources import SOURCES

    vlv = next(s for s in SOURCES if s["key"] == "vlv")
    op.execute(src.update().where(src.c.key == "vlv").values(
        enabled=True, live_enabled=True, connector_type="jsonld_index", policy_status="approved", method="jsonld_index", connector_status="ok",
        categories=vlv["categories"], policy=vlv["policy"], notes=vlv["notes"]))


def downgrade() -> None:
    op.execute(src.update().where(src.c.key == "vlv").values(
        enabled=False, live_enabled=False, connector_type="jsonld_sitemap", policy_status="pending", method="jsonld_sitemap", connector_status="needs_audit",
        categories=json.loads('["appliances", "furniture", "plumbing", "decor"]')))
