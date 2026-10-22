"""scheduled supplier price feed settings and sync history

Revision ID: 0008_supplier_feed
Revises: 0007_notifications
"""
import sqlalchemy as sa
from alembic import op

revision = "0008_supplier_feed"
down_revision = "0007_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("suppliers") as b:
        b.add_column(sa.Column("feed", sa.JSON(), nullable=False, server_default="{}"))


def downgrade() -> None:
    with op.batch_alter_table("suppliers") as b:
        b.drop_column("feed")
