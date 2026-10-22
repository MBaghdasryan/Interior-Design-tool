"""supplier onboarding (verification, agreement, category map), supplier assets,
locations, delivery options, installation services

Revision ID: 0010_supplier_partner
Revises: 0009_commerce
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_supplier_partner"
down_revision = "0009_commerce"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("suppliers") as b:
        b.add_column(sa.Column("verification", sa.String(20), nullable=False, server_default="verified"))  # existing rows were curated
        b.add_column(sa.Column("onboarding", sa.JSON(), nullable=False, server_default="{}"))
        b.add_column(sa.Column("category_map", sa.JSON(), nullable=False, server_default="{}"))
    ts = sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)
    op.create_table("supplier_assets", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("supplier_id", sa.String(32), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("variant_id", sa.String(32), nullable=True, index=True), sa.Column("kind", sa.String(20), nullable=False),
                    sa.Column("filename", sa.String(300), nullable=False), sa.Column("mime", sa.String(100), nullable=False), sa.Column("size", sa.Integer(), nullable=False),
                    sa.Column("sha256", sa.String(64), nullable=False), sa.Column("storage_key", sa.String(400), nullable=False), sa.Column("meta", sa.JSON(), nullable=False),
                    sa.Column("scan_status", sa.String(20), nullable=False), ts.copy())
    op.create_table("supplier_locations", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("supplier_id", sa.String(32), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("kind", sa.String(20), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("city", sa.String(100), nullable=False),
                    sa.Column("address", sa.String(300), nullable=False), ts.copy())
    op.create_table("supplier_delivery_options", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("supplier_id", sa.String(32), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("name", sa.String(120), nullable=False), sa.Column("regions", sa.JSON(), nullable=False), sa.Column("fee_amd", sa.Integer(), nullable=False),
                    sa.Column("days_min", sa.Integer(), nullable=False), sa.Column("days_max", sa.Integer(), nullable=False), ts.copy())
    op.create_table("supplier_services", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("supplier_id", sa.String(32), sa.ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("name", sa.String(120), nullable=False), sa.Column("category", sa.String(50), nullable=False), sa.Column("price_amd", sa.Integer(), nullable=True),
                    sa.Column("unit", sa.String(20), nullable=False), ts.copy())


def downgrade() -> None:
    for t in ("supplier_services", "supplier_delivery_options", "supplier_locations", "supplier_assets"):
        op.drop_table(t)
    with op.batch_alter_table("suppliers") as b:
        for c in ("category_map", "onboarding", "verification"):
            b.drop_column(c)
