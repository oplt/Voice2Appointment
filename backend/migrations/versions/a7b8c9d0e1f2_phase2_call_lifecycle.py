"""Phase 2: call lifecycle transcript/outcome fields.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=False,
            existing_server_default="active",
        )
        batch_op.add_column(sa.Column("transcript", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("outcome", sa.String(length=32), nullable=True))
        batch_op.add_column(
            sa.Column("terminal_reason", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.drop_column("terminal_reason")
        batch_op.drop_column("outcome")
        batch_op.drop_column("transcript")
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=False,
            existing_server_default="active",
        )
