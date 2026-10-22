"""custom furniture configurator: configurations, spec versions, manufacturer rates

Revision ID: 0012_custom_furniture
Revises: 0011_search
"""
import sqlalchemy as sa
from alembic import op

revision = "0012_custom_furniture"
down_revision = "0011_search"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("suppliers") as b:
        b.add_column(sa.Column("custom_rates", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table("custom_configs", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("name", sa.String(200), nullable=False), sa.Column("family", sa.String(20), nullable=False), sa.Column("supplier_id", sa.String(32), nullable=True),
                    sa.Column("spec", sa.JSON(), nullable=False), sa.Column("spec_version", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
                    sa.Column("issues", sa.JSON(), nullable=False), sa.Column("pricing", sa.JSON(), nullable=False), sa.Column("order_id", sa.String(32), nullable=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("custom_config_versions", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("config_id", sa.String(32), sa.ForeignKey("custom_configs.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("version", sa.Integer(), nullable=False), sa.Column("spec", sa.JSON(), nullable=False), sa.Column("pricing", sa.JSON(), nullable=False),
                    sa.Column("author", sa.String(200), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                    sa.UniqueConstraint("config_id", "version"))


def downgrade() -> None:
    op.drop_table("custom_config_versions")
    op.drop_table("custom_configs")
    with op.batch_alter_table("suppliers") as b:
        b.drop_column("custom_rates")
