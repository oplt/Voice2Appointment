"""Add locations resources availability rules and customers.

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.create_table("resource", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id", ondelete="SET NULL")), sa.Column("resource_type", sa.String(64), nullable=False), sa.Column("name", sa.String(255), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("capacity", sa.Integer(), nullable=False, server_default="1"), *_timestamps())
    op.create_table("resource_capability", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resource.id", ondelete="CASCADE"), nullable=False), sa.Column("capability", sa.String(100), nullable=False), sa.UniqueConstraint("resource_id", "capability", name="uq_resource_capability"))
    op.create_table("service_resource_requirement", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_item.id", ondelete="CASCADE"), nullable=False), sa.Column("resource_type", sa.String(64)), sa.Column("capability", sa.String(100)), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("availability_rule", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id"), nullable=False), sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id")), sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resource.id")), sa.Column("weekday", sa.Integer(), nullable=False), sa.Column("start_time", sa.String(5), nullable=False), sa.Column("end_time", sa.String(5), nullable=False), *_timestamps())
    op.create_table("availability_exception", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id"), nullable=False), sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id")), sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resource.id")), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False), sa.Column("available", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("reason", sa.String(255)), *_timestamps())
    op.create_table("customer", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(255)), sa.Column("phone", sa.String(32)), sa.Column("email", sa.String(255)), sa.Column("language", sa.String(16)), sa.Column("consent_preferences", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *_timestamps())
    op.create_index("ix_customer_org_phone", "customer", ["organization_id", "phone"])


def downgrade() -> None:
    for table in ("customer", "availability_exception", "availability_rule", "service_resource_requirement", "resource_capability", "resource"):
        op.drop_table(table)
