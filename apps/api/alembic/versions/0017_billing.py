"""Billing: AI-credit ledger, card payments through Ameriabank vPOS, supplier applications

Revision ID: 0017_billing
Revises: 0016_retire_client_verifier
"""
import sqlalchemy as sa
from alembic import op

revision = "0017_billing"
down_revision = "0016_retire_client_verifier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_entries",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), nullable=False, index=True),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False, server_default=""),
        sa.Column("project_id", sa.String(32)),
        sa.Column("user_id", sa.String(32)),
        sa.Column("ref", sa.String(120), nullable=False, server_default=""),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("idempotency_key", sa.String(120), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "vpos_order_seq",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "billing_payments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("org_id", sa.String(32), nullable=False, index=True),
        sa.Column("user_id", sa.String(32)),
        sa.Column("purpose", sa.String(20), nullable=False),
        sa.Column("item_key", sa.String(40), nullable=False),
        sa.Column("interval", sa.String(10), nullable=False, server_default=""),
        sa.Column("amount_amd", sa.BigInteger, nullable=False),
        sa.Column("provider", sa.String(30), nullable=False, server_default="ameriabank"),
        sa.Column("order_id", sa.BigInteger, unique=True),
        sa.Column("provider_payment_id", sa.String(80), nullable=False, server_default="", index=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="created"),
        sa.Column("response_code", sa.String(20), nullable=False, server_default=""),
        sa.Column("details", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("refunded_amd", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "supplier_applications",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("company", sa.String(200), nullable=False),
        sa.Column("contact_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(40), nullable=False, server_default=""),
        sa.Column("website", sa.String(300), nullable=False, server_default=""),
        sa.Column("city", sa.String(100), nullable=False, server_default=""),
        sa.Column("kind", sa.String(20), nullable=False, server_default="store"),
        sa.Column("sku_count", sa.Integer),
        sa.Column("categories", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("message", sa.Text, nullable=False, server_default=""),
        sa.Column("locale", sa.String(5), nullable=False, server_default="hy"),
        sa.Column("status", sa.String(20), nullable=False, server_default="new"),
        sa.Column("note", sa.Text, nullable=False, server_default=""),
        sa.Column("org_id", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    for t in ("supplier_applications", "billing_payments", "vpos_order_seq", "credit_entries"):
        op.drop_table(t)
