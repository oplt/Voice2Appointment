"""Create additive catalog, pricing, resource, customer, and reservation tables.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("catalog_category", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), *_timestamps(), sa.UniqueConstraint("organization_id", "name", name="uq_catalog_category"))
    op.create_table("catalog_item", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("category_id", sa.Integer(), sa.ForeignKey("catalog_category.id", ondelete="SET NULL")), sa.Column("kind", sa.String(16), nullable=False, server_default="service"), sa.Column("name", sa.String(255), nullable=False), sa.Column("description", sa.Text()), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("bookable", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("sellable", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("duration_minutes", sa.Integer()), sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default="0"), sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default="0"), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *_timestamps())
    op.create_index("ix_catalog_item_org_active", "catalog_item", ["organization_id", "active"])
    op.create_table("catalog_option", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_item.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *_timestamps())
    op.create_table("price_book", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), *_timestamps())
    op.create_table("price", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("price_book_id", sa.Integer(), sa.ForeignKey("price_book.id", ondelete="CASCADE"), nullable=False), sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_item.id", ondelete="CASCADE"), nullable=False), sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id", ondelete="CASCADE")), sa.Column("amount_minor", sa.Integer(), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("channel", sa.String(32)), sa.Column("effective_from", sa.DateTime(timezone=True)), sa.Column("effective_until", sa.DateTime(timezone=True)), sa.Column("tax_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *_timestamps())
    op.create_index("ix_price_book_item_effective", "price", ["price_book_id", "catalog_item_id", "effective_from"])


def downgrade() -> None:
    for table in ("price", "price_book", "catalog_option", "catalog_item", "catalog_category"):
        op.drop_table(table)
