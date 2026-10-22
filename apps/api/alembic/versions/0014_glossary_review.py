"""Armenian terminology review: proposed / approved HY overrides for the album vocabulary

Revision ID: 0014_glossary_review
Revises: 0013_domus_full_index
"""
import sqlalchemy as sa
from alembic import op

revision = "0014_glossary_review"
down_revision = "0013_domus_full_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("glossary_entries", sa.Column("id", sa.String(32), primary_key=True), sa.Column("term_key", sa.String(160), nullable=False, unique=True),
                    sa.Column("hy_original", sa.Text(), nullable=False), sa.Column("hy_proposed", sa.Text(), nullable=False), sa.Column("comment", sa.Text(), nullable=False),
                    sa.Column("status", sa.String(20), nullable=False), sa.Column("author", sa.String(200), nullable=False),
                    sa.Column("reviewed_by", sa.String(200), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    op.drop_table("glossary_entries")
