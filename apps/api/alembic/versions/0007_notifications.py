"""notifications (in-app + e-mail digest) and per-user notification preferences

Revision ID: 0007_notifications
Revises: 0006_ai_budget
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_notifications"
down_revision = "0006_ai_budget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("notification_prefs", sa.JSON(), nullable=False, server_default="{}"))
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("link", sa.String(300), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(32), nullable=True, index=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("emailed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notifications")
    with op.batch_alter_table("users") as b:
        b.drop_column("notification_prefs")
