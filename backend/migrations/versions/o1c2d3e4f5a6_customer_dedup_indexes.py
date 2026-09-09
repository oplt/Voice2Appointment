"""Add partial unique indexes for customer phone/email dedup.

Revision ID: o1c2d3e4f5a6
Revises: n1c2d3e4f5a6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.telephony.phones import canonical_e164

revision = "o1c2d3e4f5a6"
down_revision = "n1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    customers = list(
        bind.execute(
            sa.text("SELECT id, organization_id, name, phone, email, language FROM customer")
        ).mappings()
    )

    # Normalize only numbers that are already internationally qualified.  There
    # is no country field on the legacy customer/location schema, so guessing a
    # region here would corrupt otherwise valid local numbers.
    for customer in customers:
        phone = customer["phone"]
        normalized_phone = canonical_e164(phone, default_region=None) if phone else None
        normalized_email = customer["email"].strip().lower() if customer["email"] else None
        bind.execute(
            sa.text(
                "UPDATE customer SET phone = :phone, email = :email WHERE id = :id"
            ),
            {
                "id": customer["id"],
                "phone": normalized_phone or (phone.strip() if phone else None),
                "email": normalized_email,
            },
        )

    customers = list(
        bind.execute(
            sa.text("SELECT id, organization_id, name, phone, email, language FROM customer")
        ).mappings()
    )
    parent = {customer["id"]: customer["id"] for customer in customers}

    def find(customer_id: int) -> int:
        while parent[customer_id] != customer_id:
            parent[customer_id] = parent[parent[customer_id]]
            customer_id = parent[customer_id]
        return customer_id

    def union(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[max(left_root, right_root)] = min(left_root, right_root)

    seen: dict[tuple[int, str, str], int] = {}
    for customer in customers:
        for field in ("phone", "email"):
            value = customer[field]
            if value:
                key = (customer["organization_id"], field, value)
                if key in seen:
                    union(customer["id"], seen[key])
                else:
                    seen[key] = customer["id"]

    grouped: dict[int, list[dict[str, object]]] = {}
    for customer in customers:
        grouped.setdefault(find(customer["id"]), []).append(dict(customer))

    references = (
        "reservation",
        "customer_order",
        "secure_link_delivery",
        "payment_intent",
        "waitlist_entry",
    )
    for group in grouped.values():
        if len(group) == 1:
            continue
        group.sort(key=lambda customer: int(customer["id"]))
        canonical, duplicates = group[0], group[1:]
        for duplicate in duplicates:
            for field in ("name", "phone", "email", "language"):
                if not canonical[field] and duplicate[field]:
                    canonical[field] = duplicate[field]
            for table in references:
                bind.execute(
                    sa.text(
                        f"UPDATE {table} SET customer_id = :target "
                        "WHERE organization_id = :organization_id AND customer_id = :source"
                    ),
                    {
                        "target": canonical["id"],
                        "organization_id": canonical["organization_id"],
                        "source": duplicate["id"],
                    },
                )
            bind.execute(sa.text("DELETE FROM customer WHERE id = :id"), {"id": duplicate["id"]})
        bind.execute(
            sa.text(
                "UPDATE customer SET name = :name, phone = :phone, email = :email, "
                "language = :language WHERE id = :id"
            ),
            canonical,
        )

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_org_phone "
        "ON customer (organization_id, phone) WHERE phone IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_org_email "
        "ON customer (organization_id, email) WHERE email IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("uq_customer_org_email", table_name="customer")
    op.drop_index("uq_customer_org_phone", table_name="customer")
