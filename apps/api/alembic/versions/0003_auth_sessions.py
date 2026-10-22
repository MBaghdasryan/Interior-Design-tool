"""registration, email verification, password reset, server-side sessions

Revision ID: 0003_auth_sessions
Revises: 0002_i18n_sources
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_auth_sessions"
down_revision = "0002_i18n_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("status", sa.String(20), nullable=False, server_default="active"))
        b.add_column(sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("onboarded_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("consents", sa.JSON(), nullable=False, server_default="{}"))
    # accounts that existed before registration (demo/seeded) count as verified and onboarded
    op.execute("UPDATE users SET email_verified_at = created_at, onboarded_at = created_at")
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("user_agent", sa.String(300), nullable=False, server_default=""),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_tokens")
    op.drop_table("auth_sessions")
    with op.batch_alter_table("users") as b:
        for c in ("consents", "onboarded_at", "email_verified_at", "status"):
            b.drop_column(c)
