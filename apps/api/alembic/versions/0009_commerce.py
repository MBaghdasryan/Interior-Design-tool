"""commerce: carts, order items, quotes, delivery, installation, commissions, payments,
payouts, immutable double-entry ledger, processed webhooks, platform settings

Revision ID: 0009_commerce
Revises: 0008_supplier_feed
"""
import sqlalchemy as sa
from alembic import op

revision = "0009_commerce"
down_revision = "0008_supplier_feed"
branch_labels = None
depends_on = None


def _ts():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    with op.batch_alter_table("orders") as b:
        b.add_column(sa.Column("cart_id", sa.String(32), nullable=True))
        b.add_column(sa.Column("idempotency_key", sa.String(100), nullable=True))
        b.add_column(sa.Column("currency", sa.String(3), nullable=False, server_default="AMD"))
        b.add_column(sa.Column("payment_status", sa.String(20), nullable=False, server_default="none"))
        b.add_column(sa.Column("history", sa.JSON(), nullable=False, server_default="[]"))
        b.create_index("ix_orders_cart_id", ["cart_id"])
        b.create_unique_constraint("uq_orders_idempotency_key", ["idempotency_key"])
    op.create_table("carts", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("variant_id", sa.String(32), nullable=False), sa.Column("status", sa.String(20), nullable=False),
                    sa.Column("rechecked_at", sa.DateTime(timezone=True), nullable=True), sa.Column("recheck", sa.JSON(), nullable=False), *_ts())
    op.create_table("order_items", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("ref", sa.String(80), nullable=False), sa.Column("name", sa.String(300), nullable=False), sa.Column("sku", sa.String(120), nullable=False),
                    sa.Column("qty", sa.Float(), nullable=False), sa.Column("unit", sa.String(20), nullable=False), sa.Column("unit_price", sa.Float(), nullable=True),
                    sa.Column("total", sa.Float(), nullable=True), sa.Column("price_status", sa.String(30), nullable=False), sa.Column("rechecked_price", sa.Float(), nullable=True),
                    sa.Column("url", sa.String(600), nullable=False), sa.Column("lead_days", sa.Integer(), nullable=True))
    op.create_table("supplier_quotes", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("supplier_id", sa.String(32), nullable=True), sa.Column("total_amd", sa.BigInteger(), nullable=False),
                    sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.String(20), nullable=False), sa.Column("note", sa.Text(), nullable=False), *_ts())
    op.create_table("deliveries", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
                    sa.Column("status", sa.String(20), nullable=False), sa.Column("window_from", sa.DateTime(timezone=True), nullable=True),
                    sa.Column("window_to", sa.DateTime(timezone=True), nullable=True), sa.Column("address", sa.String(300), nullable=False), sa.Column("cost_amd", sa.BigInteger(), nullable=False), *_ts())
    op.create_table("installations", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True),
                    sa.Column("status", sa.String(20), nullable=False), sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True), sa.Column("cost_amd", sa.BigInteger(), nullable=False), *_ts())
    op.create_table("commissions", sa.Column("id", sa.String(32), primary_key=True),
                    sa.Column("order_id", sa.String(32), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("party", sa.String(20), nullable=False), sa.Column("org_id", sa.String(32), nullable=True), sa.Column("pct", sa.Float(), nullable=False),
                    sa.Column("amount_amd", sa.BigInteger(), nullable=False), *_ts())
    op.create_table("payments", sa.Column("id", sa.String(32), primary_key=True), sa.Column("order_id", sa.String(32), nullable=False, index=True),
                    sa.Column("provider", sa.String(30), nullable=False), sa.Column("provider_ref", sa.String(120), nullable=False, index=True),
                    sa.Column("amount_amd", sa.BigInteger(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
                    sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True), *_ts())
    op.create_table("payouts", sa.Column("id", sa.String(32), primary_key=True), sa.Column("supplier_id", sa.String(32), nullable=False, index=True),
                    sa.Column("amount_amd", sa.BigInteger(), nullable=False), sa.Column("status", sa.String(20), nullable=False),
                    sa.Column("reference", sa.String(200), nullable=False), sa.Column("txn_id", sa.String(32), nullable=False), *_ts())
    op.create_table("ledger_entries", sa.Column("id", sa.String(32), primary_key=True), sa.Column("txn_id", sa.String(32), nullable=False, index=True),
                    sa.Column("line_no", sa.Integer(), nullable=False), sa.Column("kind", sa.String(30), nullable=False),
                    sa.Column("account", sa.String(120), nullable=False, index=True), sa.Column("debit", sa.BigInteger(), nullable=False),
                    sa.Column("credit", sa.BigInteger(), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
                    sa.Column("order_id", sa.String(32), nullable=True, index=True), sa.Column("idempotency_key", sa.String(120), nullable=False),
                    sa.Column("memo", sa.String(300), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
                    sa.UniqueConstraint("idempotency_key", "line_no"), sa.CheckConstraint("debit >= 0 AND credit >= 0 AND (debit = 0 OR credit = 0)", name="ck_ledger_one_side"))
    op.create_table("processed_webhooks", sa.Column("id", sa.String(200), primary_key=True), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("platform_settings", sa.Column("key", sa.String(60), primary_key=True), sa.Column("value", sa.JSON(), nullable=False), *_ts())
    if op.get_bind().dialect.name == "postgresql":  # append-only journal enforced by the database itself
        op.execute("""CREATE FUNCTION ledger_immutable() RETURNS trigger AS $$
                      BEGIN RAISE EXCEPTION 'ledger_entries are append-only'; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER ledger_no_update BEFORE UPDATE OR DELETE ON ledger_entries FOR EACH ROW EXECUTE FUNCTION ledger_immutable()")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS ledger_no_update ON ledger_entries")
        op.execute("DROP FUNCTION IF EXISTS ledger_immutable()")
    for t in ("platform_settings", "processed_webhooks", "ledger_entries", "payouts", "payments", "commissions", "installations", "deliveries",
              "supplier_quotes", "order_items", "carts"):
        op.drop_table(t)
    with op.batch_alter_table("orders") as b:
        b.drop_constraint("uq_orders_idempotency_key", type_="unique")
        b.drop_index("ix_orders_cart_id")
        for c in ("history", "payment_status", "currency", "idempotency_key", "cart_id"):
            b.drop_column(c)
