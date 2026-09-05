"""P6-V01: durable notification outbox lease/attempt counter.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notification_delivery") as batch_op:
        batch_op.add_column(
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("notification_delivery") as batch_op:
        batch_op.drop_column("leased_until")
        batch_op.drop_column("attempt_count")
