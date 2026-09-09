"""Reconcile PostgreSQL schema with the current ORM metadata.

Revision ID: h0c1d2e3f4a5
Revises: g9b0c1d2e3f4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h0c1d2e3f4a5"
down_revision = "g9b0c1d2e3f4"
branch_labels = None
depends_on = None


_JSON_COLUMNS = (
    ("audit_log", "data"),
    ("catalog_item", "metadata_json"),
    ("catalog_option", "metadata_json"),
    ("customer", "consent_preferences"),
    ("customer", "metadata_json"),
    ("feature_entitlement", "limits_json"),
    ("industry_profile", "required_customer_fields"),
    ("industry_profile", "required_booking_fields"),
    ("industry_profile", "enabled_tools"),
    ("industry_profile", "confirmation_policy"),
    ("industry_profile", "deposit_policy"),
    ("industry_profile", "handoff_policy"),
    ("industry_profile", "privacy_policy"),
    ("industry_profile", "terminology"),
    ("industry_profile", "flow_steps"),
    ("industry_profile", "metadata_json"),
    ("knowledge_entry", "metadata_json"),
    ("location", "business_hours"),
    ("organization", "metadata_json"),
    ("price", "tax_metadata"),
    ("reservation", "allocation_json"),
    ("reservation_line_item", "tax_metadata"),
    ("waitlist_entry", "metadata_json"),
)

_INDEXES = (
    ("ix_audit_log_actor_user_id", "audit_log", ["actor_user_id"]),
    ("ix_audit_log_organization_id", "audit_log", ["organization_id"]),
    ("ix_availability_exception_location_id", "availability_exception", ["location_id"]),
    ("ix_availability_exception_organization_id", "availability_exception", ["organization_id"]),
    ("ix_availability_exception_resource_id", "availability_exception", ["resource_id"]),
    ("ix_availability_rule_location_id", "availability_rule", ["location_id"]),
    ("ix_availability_rule_organization_id", "availability_rule", ["organization_id"]),
    ("ix_availability_rule_resource_id", "availability_rule", ["resource_id"]),
    ("ix_catalog_category_organization_id", "catalog_category", ["organization_id"]),
    ("ix_catalog_item_organization_id", "catalog_item", ["organization_id"]),
    ("ix_catalog_option_catalog_item_id", "catalog_option", ["catalog_item_id"]),
    ("ix_customer_organization_id", "customer", ["organization_id"]),
    ("ix_feature_entitlement_organization_id", "feature_entitlement", ["organization_id"]),
    ("ix_knowledge_entry_organization_id", "knowledge_entry", ["organization_id"]),
    ("ix_notification_delivery_user_id", "notification_delivery", ["user_id"]),
    ("ix_price_book_organization_id", "price_book", ["organization_id"]),
    ("ix_price_catalog_item_id", "price", ["catalog_item_id"]),
    ("ix_price_location_id", "price", ["location_id"]),
    ("ix_price_price_book_id", "price", ["price_book_id"]),
    ("ix_reservation_customer_id", "reservation", ["customer_id"]),
    ("ix_reservation_line_item_reservation_id", "reservation_line_item", ["reservation_id"]),
    ("ix_reservation_location_id", "reservation", ["location_id"]),
    ("ix_reservation_organization_id", "reservation", ["organization_id"]),
    ("ix_reservation_resource_reservation_id", "reservation_resource", ["reservation_id"]),
    ("ix_reservation_resource_resource_id", "reservation_resource", ["resource_id"]),
    ("ix_resource_capability_resource_id", "resource_capability", ["resource_id"]),
    ("ix_resource_location_id", "resource", ["location_id"]),
    ("ix_resource_organization_id", "resource", ["organization_id"]),
    ("ix_service_resource_requirement_catalog_item_id", "service_resource_requirement", ["catalog_item_id"]),
    ("ix_twilio_call_status", "twilio_call", ["status"]),
    ("ix_waitlist_entry_customer_id", "waitlist_entry", ["customer_id"]),
    ("ix_waitlist_entry_location_id", "waitlist_entry", ["location_id"]),
)


def _alter_json_columns(to_type: sa.types.TypeEngine[object], cast_type: str) -> None:
    for table, column in _JSON_COLUMNS:
        op.alter_column(
            table,
            column,
            existing_type=sa.JSON(),
            type_=to_type,
            postgresql_using=f"{column}::{cast_type}",
        )


def upgrade() -> None:
    op.execute("UPDATE appointment SET reminder_sent = false WHERE reminder_sent IS NULL")
    op.alter_column("appointment", "reminder_sent", existing_type=sa.Boolean(), nullable=False)
    op.execute("UPDATE callsession SET status = 'active' WHERE status IS NULL")
    op.alter_column("callsession", "status", existing_type=sa.String(32), nullable=False)
    op.execute("UPDATE callsession SET started_at = now() WHERE started_at IS NULL")
    op.alter_column("callsession", "started_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.alter_column("res_user", "twilio_phone_number", existing_type=sa.String(20), type_=sa.String(32))
    op.drop_column("res_user", "deepgram_api_key")
    _alter_json_columns(postgresql.JSONB(astext_type=sa.Text()), "jsonb")
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
    _alter_json_columns(sa.JSON(), "json")
    op.add_column("res_user", sa.Column("deepgram_api_key", sa.Text(), nullable=True))
    op.alter_column("res_user", "twilio_phone_number", existing_type=sa.String(32), type_=sa.String(20))
    op.alter_column("callsession", "started_at", existing_type=sa.DateTime(timezone=True), nullable=True)
    op.alter_column("callsession", "status", existing_type=sa.String(32), nullable=True)
    op.alter_column("appointment", "reminder_sent", existing_type=sa.Boolean(), nullable=True)
