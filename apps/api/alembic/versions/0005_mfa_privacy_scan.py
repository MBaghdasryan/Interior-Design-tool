"""MFA (TOTP + backup codes), account deletion grace period, upload scan status

Revision ID: 0005_mfa_privacy_scan
Revises: 0004_vlv_index_source
"""
import sqlalchemy as sa
from alembic import op

revision = "0005_mfa_privacy_scan"
down_revision = "0004_vlv_index_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("mfa_secret_enc", sa.Text(), nullable=True))
        b.add_column(sa.Column("mfa_pending_enc", sa.Text(), nullable=True))
        b.add_column(sa.Column("mfa_enabled_at", sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("mfa_backup_codes", sa.JSON(), nullable=False, server_default="[]"))
        b.add_column(sa.Column("deletion_due_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("source_assets") as b:
        b.add_column(sa.Column("scan_status", sa.String(20), nullable=False, server_default="not_scanned"))


def downgrade() -> None:
    with op.batch_alter_table("source_assets") as b:
        b.drop_column("scan_status")
    with op.batch_alter_table("users") as b:
        for c in ("deletion_due_at", "mfa_backup_codes", "mfa_enabled_at", "mfa_pending_enc", "mfa_secret_enc"):
            b.drop_column(c)
