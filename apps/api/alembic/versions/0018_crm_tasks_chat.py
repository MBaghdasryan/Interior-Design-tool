"""CRM clients and activities, tasks, project chat read state; comment visibility; projects.client_id

Revision ID: 0018_crm_tasks_chat
Revises: 0017_billing
"""
import sqlalchemy as sa
from alembic import op

revision = "0018_crm_tasks_chat"
down_revision = "0017_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False, server_default=""),
        sa.Column("email", sa.String(320), nullable=False, server_default=""),
        sa.Column("source", sa.String(20), nullable=False, server_default="other"),
        sa.Column("stage", sa.String(20), nullable=False, server_default="lead"),
        sa.Column("budget_amd", sa.BigInteger),
        sa.Column("area_m2", sa.Float),
        sa.Column("address", sa.String(300), nullable=False, server_default=""),
        sa.Column("notes", sa.Text, nullable=False, server_default=""),
        sa.Column("owner_id", sa.String(32)),
        sa.Column("next_action", sa.String(300), nullable=False, server_default=""),
        sa.Column("next_action_at", sa.DateTime(timezone=True)),
        sa.Column("lost_reason", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "client_activities",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("client_id", sa.String(32), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_id", sa.String(32)),
        sa.Column("kind", sa.String(20), nullable=False, server_default="note"),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), nullable=False, index=True),
        sa.Column("project_id", sa.String(32), index=True),
        sa.Column("client_id", sa.String(32), index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("assignee_id", sa.String(32), index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="todo"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="normal"),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("estimate_h", sa.Float),
        sa.Column("created_by", sa.String(32)),
        sa.Column("done_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "project_reads",
        sa.Column("user_id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), primary_key=True),
        sa.Column("last_read_at", sa.DateTime(timezone=True)),
    )
    with op.batch_alter_table("comments") as b:
        b.add_column(sa.Column("visibility", sa.String(10), nullable=False, server_default="client"))
    with op.batch_alter_table("projects") as b:
        b.add_column(sa.Column("client_id", sa.String(32)))
        b.create_index("ix_projects_client_id", ["client_id"])


def downgrade() -> None:
    with op.batch_alter_table("projects") as b:
        b.drop_index("ix_projects_client_id")
        b.drop_column("client_id")
    with op.batch_alter_table("comments") as b:
        b.drop_column("visibility")
    for t in ("project_reads", "tasks", "client_activities", "clients"):
        op.drop_table(t)
