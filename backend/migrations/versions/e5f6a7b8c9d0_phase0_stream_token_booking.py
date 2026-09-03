"""Phase 0: stream tokens + provider sync status for idempotent booking.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.add_column(sa.Column("stream_token_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("stream_token_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("stream_token_consumed_at", sa.DateTime(timezone=True), nullable=True)
        )

    with op.batch_alter_table("appointment") as batch_op:
        batch_op.add_column(
            sa.Column(
                "provider_sync_status",
                sa.String(length=32),
                nullable=False,
                server_default="confirmed",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("appointment") as batch_op:
        batch_op.drop_column("provider_sync_status")
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.drop_column("stream_token_consumed_at")
        batch_op.drop_column("stream_token_expires_at")
        batch_op.drop_column("stream_token_hash")
