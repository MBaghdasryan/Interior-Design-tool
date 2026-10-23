"""products.status (active | archived) for manual catalogue management

Revision ID: 0015_product_status
Revises: 0014_glossary_review
"""
import sqlalchemy as sa
from alembic import op

revision = "0015_product_status"
down_revision = "0014_glossary_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as b:
        b.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="active"))


def downgrade() -> None:
    with op.batch_alter_table("products") as b:
        b.drop_column("status")
