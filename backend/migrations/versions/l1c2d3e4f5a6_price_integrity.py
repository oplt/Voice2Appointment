"""Enforce price amount and effective-window invariants.

Revision ID: l1c2d3e4f5a6
Revises: k1c2d3e4f5a6
"""

from __future__ import annotations

from alembic import op

revision = "l1c2d3e4f5a6"
down_revision = "k1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_price_amount_minor_nonnegative", "price", "amount_minor >= 0"
    )
    op.create_check_constraint(
        "ck_price_effective_window",
        "price",
        "effective_until IS NULL OR effective_from IS NULL OR effective_until > effective_from",
    )


def downgrade() -> None:
    op.drop_constraint("ck_price_effective_window", "price", type_="check")
    op.drop_constraint("ck_price_amount_minor_nonnegative", "price", type_="check")
