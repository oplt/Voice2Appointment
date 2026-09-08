"""Additive organization resolution while legacy user ownership remains valid."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Organization, OrganizationMember, User


def organization_for_user(db: Session, user: User) -> Organization | None:
    """Return the migrated organization without changing legacy ownership."""
    if user.organization_id is None:
        return None
    return db.get(Organization, user.organization_id)


def create_organization_for_user(db: Session, user: User) -> Organization:
    """Compatibility fallback for a user created before the backfill runs."""
    existing = organization_for_user(db, user)
    if existing is not None:
        return existing
    organization = Organization(name=user.username, slug=f"legacy-{user.id}")
    db.add(organization)
    db.flush()
    user.organization_id = organization.id
    db.add(OrganizationMember(organization_id=organization.id, user_id=user.id, role="owner"))
    return organization
