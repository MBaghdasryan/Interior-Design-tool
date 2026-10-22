"""product embeddings for semantic / visual search; pgvector when the server provides it

Revision ID: 0011_search
Revises: 0010_supplier_partner
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_search"
down_revision = "0010_supplier_partner"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("product_embeddings", sa.Column("id", sa.String(32), primary_key=True), sa.Column("item_ref", sa.String(40), nullable=False, index=True),
                    sa.Column("modality", sa.String(10), nullable=False), sa.Column("provider", sa.String(20), nullable=False), sa.Column("model", sa.String(60), nullable=False),
                    sa.Column("dim", sa.Integer(), nullable=False), sa.Column("vector", sa.JSON(), nullable=False), sa.Column("text_hash", sa.String(64), nullable=False),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("item_ref", "modality", "provider", "model"))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # pgvector is optional: the stock postgres image does not ship it; the in-memory index works without it
        available = bind.exec_driver_sql("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'").first()
        if available:
            op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.drop_table("product_embeddings")
