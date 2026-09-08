"""Add a durable per-user lease for Twilio synchronization.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.add_column(sa.Column("twilio_sync_lease_token", sa.String(64), nullable=True))
        batch_op.add_column(
            sa.Column("twilio_sync_lease_expires_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("res_user") as batch_op:
        batch_op.drop_column("twilio_sync_lease_expires_at")
        batch_op.drop_column("twilio_sync_lease_token")
