"""step params for i18n, external source seed keys

Revision ID: 0002_i18n_sources
Revises: 0001_baseline
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_i18n_sources"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generation_steps") as b:
        b.add_column(sa.Column("params", sa.JSON(), nullable=False, server_default="{}"))
    with op.batch_alter_table("external_sources") as b:
        b.add_column(sa.Column("canonical_domain", sa.String(200), nullable=True))
        b.add_column(sa.Column("connector_type", sa.String(30), nullable=False, server_default="jsonld_sitemap"))
        b.add_column(sa.Column("live_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("policy_status", sa.String(30), nullable=False, server_default="pending"))
        b.add_column(sa.Column("health_status", sa.String(30), nullable=False, server_default="unknown"))
        b.create_unique_constraint("uq_external_sources_canonical_domain", ["canonical_domain"])


def downgrade() -> None:
    with op.batch_alter_table("external_sources") as b:
        b.drop_constraint("uq_external_sources_canonical_domain", type_="unique")
        for c in ("health_status", "policy_status", "live_enabled", "connector_type", "canonical_domain"):
            b.drop_column(c)
    with op.batch_alter_table("generation_steps") as b:
        b.drop_column("params")
