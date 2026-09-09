"""Add optimistic-concurrency version to catalog items.

Revision ID: k1c2d3e4f5a6
Revises: j1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "k1c2d3e4f5a6"
down_revision = "j1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_item",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("catalog_item", "version")
