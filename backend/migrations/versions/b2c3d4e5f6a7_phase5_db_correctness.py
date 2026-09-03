"""Phase 5: reconcile schema, timezone-aware datetimes, indexes, idempotency."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _alter_to_tz(table: str, column: str, *, nullable: bool) -> None:
    if _is_postgres():
        op.execute(
            sa.text(
                f'ALTER TABLE "{table}" ALTER COLUMN "{column}" '
                f"TYPE TIMESTAMP WITH TIME ZONE "
                f"USING \"{column}\" AT TIME ZONE 'UTC'"
            )
        )
        op.alter_column(table, column, nullable=nullable)
    else:
        with op.batch_alter_table(table) as batch_op:
            batch_op.alter_column(
                column,
                existing_type=sa.DateTime(),
                type_=sa.DateTime(timezone=True),
                existing_nullable=nullable,
                nullable=nullable,
            )


def upgrade() -> None:
    with op.batch_alter_table("callsession") as batch_op:
        batch_op.add_column(sa.Column("recording_path", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "recording_downloaded_at", sa.DateTime(timezone=True), nullable=True
            )
        )

    with op.batch_alter_table("google_calendar_auth") as batch_op:
        batch_op.alter_column(
            "embeded_link",
            new_column_name="embedded_link",
            existing_type=sa.String(length=500),
            existing_nullable=True,
        )

    json_type = (
        postgresql.JSONB(astext_type=sa.Text()) if _is_postgres() else sa.JSON()
    )
    op.create_table(
        "twilio_call_analytics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("call_data", json_type, server_default="{}", nullable=False),
        sa.Column("processed_metrics", json_type, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("twilio_call_analytics") as batch_op:
        batch_op.create_index(
            batch_op.f("ix_twilio_call_analytics_date"), ["date"], unique=False
        )

    with op.batch_alter_table("appointment") as batch_op:
        batch_op.add_column(
            sa.Column("idempotency_key", sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_appointment_google_calendar_event_id"),
            ["google_calendar_event_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_appointment_user_start",
            ["user_id", "start_datetime"],
            unique=False,
        )
        batch_op.create_index(
            "ix_appointment_user_status_start",
            ["user_id", "status", "start_datetime"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_appointment_idempotency_key", ["idempotency_key"]
        )

    # Recreate FK with ON DELETE SET NULL (constraint name may vary by dialect).
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    fks = inspector.get_foreign_keys("appointment")
    for fk in fks:
        if fk.get("constrained_columns") == ["callsession_id"]:
            with op.batch_alter_table("appointment") as batch_op:
                batch_op.drop_constraint(fk["name"], type_="foreignkey")
                batch_op.create_foreign_key(
                    "appointment_callsession_id_fkey",
                    "callsession",
                    ["callsession_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            break

    for table, column, nullable in [
        ("appointment", "start_datetime", False),
        ("appointment", "end_datetime", False),
        ("appointment", "created_at", False),
        ("appointment", "updated_at", False),
        ("google_calendar_auth", "access_token_expires_at", True),
        ("google_calendar_auth", "created_at", False),
        ("google_calendar_auth", "updated_at", False),
        ("callsession", "started_at", True),
        ("callsession", "ended_at", True),
        ("callsession", "expires_at", True),
    ]:
        _alter_to_tz(table, column, nullable=nullable)


def downgrade() -> None:
    with op.batch_alter_table("appointment") as batch_op:
        batch_op.drop_constraint("appointment_callsession_id_fkey", type_="foreignkey")
        batch_op.create_foreign_key(
            "appointment_callsession_id_fkey",
            "callsession",
            ["callsession_id"],
            ["id"],
        )
        batch_op.drop_constraint("uq_appointment_idempotency_key", type_="unique")
        batch_op.drop_index("ix_appointment_user_status_start")
        batch_op.drop_index("ix_appointment_user_start")
        batch_op.drop_index(batch_op.f("ix_appointment_google_calendar_event_id"))
        batch_op.drop_column("idempotency_key")

    with op.batch_alter_table("twilio_call_analytics") as batch_op:
        batch_op.drop_index(batch_op.f("ix_twilio_call_analytics_date"))
    op.drop_table("twilio_call_analytics")

    with op.batch_alter_table("google_calendar_auth") as batch_op:
        batch_op.alter_column(
            "embedded_link",
            new_column_name="embeded_link",
            existing_type=sa.String(length=500),
            existing_nullable=True,
        )

    with op.batch_alter_table("callsession") as batch_op:
        batch_op.drop_column("recording_downloaded_at")
        batch_op.drop_column("recording_path")
