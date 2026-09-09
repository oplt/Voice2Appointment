"""Secure-link delivery claim lease + EncryptedText token column.

Revision ID: p1c2d3e4f5a6
Revises: o1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p1c2d3e4f5a6"
down_revision = "o1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("secure_link_delivery") as batch_op:
        batch_op.alter_column(
            "token_ciphertext",
            existing_type=sa.String(length=128),
            type_=sa.Text(),
            existing_nullable=False,
            nullable=True,
        )
        batch_op.add_column(sa.Column("claim_token", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("secure_link_delivery") as batch_op:
        batch_op.drop_column("leased_until")
        batch_op.drop_column("claim_token")
        batch_op.alter_column(
            "token_ciphertext",
            existing_type=sa.Text(),
            type_=sa.String(length=128),
            existing_nullable=True,
            nullable=False,
        )
