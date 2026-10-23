"""Partner (referral) programme: personal codes and daily click counters

Revision ID: 0019_partner_program
Revises: 0018_crm_tasks_chat
"""
import sqlalchemy as sa
from alembic import op

revision = "0019_partner_program"
down_revision = "0018_crm_tasks_chat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "partner_codes",
        sa.Column("user_id", sa.String(32), primary_key=True),
        sa.Column("code", sa.String(24), nullable=False, unique=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "referral_clicks",
        sa.Column("code", sa.String(24), primary_key=True),
        sa.Column("day", sa.String(10), primary_key=True),
        sa.Column("count", sa.Integer, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("referral_clicks")
    op.drop_table("partner_codes")
