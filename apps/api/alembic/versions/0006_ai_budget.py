"""AI usage: organisation (budget accounting) and trace id

Revision ID: 0006_ai_budget
Revises: 0005_mfa_privacy_scan
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_ai_budget"
down_revision = "0005_mfa_privacy_scan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("ai_usage") as b:
        b.add_column(sa.Column("org_id", sa.String(32), nullable=True))
        b.add_column(sa.Column("trace_id", sa.String(16), nullable=True))
        b.create_index("ix_ai_usage_org_id", ["org_id"])
    # back-fill the organisation of past usage from its project
    op.execute("UPDATE ai_usage SET org_id = (SELECT org_id FROM projects WHERE projects.id = ai_usage.project_id) WHERE project_id IS NOT NULL")


def downgrade() -> None:
    with op.batch_alter_table("ai_usage") as b:
        b.drop_index("ix_ai_usage_org_id")
        b.drop_column("trace_id")
        b.drop_column("org_id")
