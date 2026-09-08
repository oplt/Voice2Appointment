"""Add reservation snapshots, knowledge, entitlements, and audit records.

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f8a9b0c1d2e3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def _timestamps() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.create_table("reservation", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id"), nullable=False), sa.Column("location_id", sa.Integer(), sa.ForeignKey("location.id")), sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customer.id")), sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("appointment.id"), unique=True), sa.Column("status", sa.String(32), nullable=False, server_default="pending"), sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False), sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=False), sa.Column("party_size", sa.Integer(), nullable=False, server_default="1"), *_timestamps())
    op.create_table("reservation_resource", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("reservation.id", ondelete="CASCADE"), nullable=False), sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resource.id"), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.UniqueConstraint("reservation_id", "resource_id", name="uq_reservation_resource"))
    op.create_table("reservation_line_item", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("reservation_id", sa.Integer(), sa.ForeignKey("reservation.id", ondelete="CASCADE"), nullable=False), sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_item.id")), sa.Column("item_name", sa.String(255), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"), sa.Column("unit_price_minor", sa.Integer(), nullable=False), sa.Column("currency", sa.String(3), nullable=False), sa.Column("tax_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.create_table("knowledge_entry", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("title", sa.String(255), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *_timestamps())
    op.create_table("feature_entitlement", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("feature", sa.String(100), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("limits_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), *_timestamps(), sa.UniqueConstraint("organization_id", "feature", name="uq_feature_entitlement"))
    op.create_table("audit_log", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organization.id", ondelete="CASCADE"), nullable=False), sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("res_user.id")), sa.Column("action", sa.String(100), nullable=False), sa.Column("entity_type", sa.String(100), nullable=False), sa.Column("entity_id", sa.String(64)), sa.Column("data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))


def downgrade() -> None:
    for table in ("audit_log", "feature_entitlement", "knowledge_entry", "reservation_line_item", "reservation_resource", "reservation"):
        op.drop_table(table)
