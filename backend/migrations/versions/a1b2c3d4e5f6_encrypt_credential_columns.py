"""Widen encrypted credential columns for Fernet ciphertext."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "c9a6910c93ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("res_user", schema=None) as batch_op:
        batch_op.alter_column(
            "twilio_auth_token",
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "deepgram_api_key",
            existing_type=sa.String(length=255),
            type_=sa.Text(),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("res_user", schema=None) as batch_op:
        batch_op.alter_column(
            "twilio_auth_token",
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "deepgram_api_key",
            existing_type=sa.Text(),
            type_=sa.String(length=255),
            existing_nullable=True,
        )
