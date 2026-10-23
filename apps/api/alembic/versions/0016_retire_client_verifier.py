"""Retire the «client» and «surveyor» (verifier) account roles: clients approve through the share link,
Production Ready is signed off by the bureau head. Demo accounts of those roles are disabled.

Revision ID: 0016_retire_client_verifier
Revises: 0015_product_status
"""
import sqlalchemy as sa
from alembic import op

revision = "0016_retire_client_verifier"
down_revision = "0015_product_status"
branch_labels = None
depends_on = None

DEMO = ("client@forma.local", "verifier@forma.local")


def upgrade() -> None:
    conn = op.get_bind()
    ids = [r[0] for r in conn.execute(sa.text("SELECT id FROM users WHERE email IN :e").bindparams(sa.bindparam("e", expanding=True)), {"e": list(DEMO)})]
    conn.execute(sa.text("DELETE FROM memberships WHERE role IN ('client', 'verifier')"))
    if ids:
        q = sa.bindparam("ids", expanding=True)
        conn.execute(sa.text("DELETE FROM auth_sessions WHERE user_id IN :ids").bindparams(q), {"ids": ids})
        conn.execute(sa.text("UPDATE users SET status = 'deleted' WHERE id IN :ids").bindparams(q), {"ids": ids})


def downgrade() -> None:
    # Removed memberships are not recreated (the roles no longer exist in code); demo accounts are re-activated
    # and the seed attaches nothing to them. Data-only migration — schema is unchanged.
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE users SET status = 'active' WHERE email IN :e").bindparams(sa.bindparam("e", expanding=True)), {"e": list(DEMO)})
