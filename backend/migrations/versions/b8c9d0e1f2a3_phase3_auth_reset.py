"""Phase 3: auth_version + one-time password reset nonce.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "auth_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("password_reset_token_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "password_reset_consumed_at", sa.DateTime(timezone=True), nullable=True
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.drop_column("password_reset_consumed_at")
        batch_op.drop_column("password_reset_expires_at")
        batch_op.drop_column("password_reset_token_hash")
        batch_op.drop_column("auth_version")
