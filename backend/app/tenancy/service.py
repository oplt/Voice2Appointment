"""Additive organization resolution while legacy user ownership remains valid."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from secrets import token_urlsafe

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AuditLog,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    User,
)
from app.tenancy.permissions import (
    TenancyError,
    _valid_role,
    has_permission,
)

INVITATION_TTL_DAYS = 7


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def membership_for_user(
    db: Session, *, organization_id: int, user_id: int
) -> OrganizationMember | None:
    return db.scalar(
        select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
    )


def require_membership(
    db: Session, *, organization_id: int, user_id: int, permission: str | None = None
) -> OrganizationMember:
    member = membership_for_user(db, organization_id=organization_id, user_id=user_id)
    if member is None:
        raise TenancyError("organization membership required")
    if permission is not None and not has_permission(member, permission):
        raise TenancyError("organization permission required")
    return member


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


def list_members(db: Session, *, organization_id: int) -> list[OrganizationMember]:
    return list(
        db.scalars(
            select(OrganizationMember)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(OrganizationMember.created_at, OrganizationMember.id)
        ).all()
    )


def list_organizations_for_user(db: Session, *, user_id: int) -> list[Organization]:
    return list(
        db.scalars(
            select(Organization)
            .join(
                OrganizationMember,
                OrganizationMember.organization_id == Organization.id,
            )
            .where(
                OrganizationMember.user_id == user_id,
                Organization.active.is_(True),
            )
            .order_by(Organization.name, Organization.id)
        ).all()
    )


def switch_active_organization(db: Session, *, user: User, organization_id: int) -> Organization:
    require_membership(db, organization_id=organization_id, user_id=user.id)
    organization = db.get(Organization, organization_id)
    if organization is None or not organization.active:
        raise TenancyError("organization not found")
    user.organization_id = organization.id
    db.add(user)
    return organization


def _audit(
    db: Session, *, organization_id: int, actor_user_id: int, action: str, data: dict[str, object]
) -> None:
    db.add(
        AuditLog(
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type="organization_member",
            entity_id=str(data.get("user_id") or ""),
            data=data,
            occurred_at=_now(),
        )
    )


def set_member_role(
    db: Session, *, organization_id: int, actor_user_id: int, member_user_id: int, role: str
) -> OrganizationMember:
    role = _valid_role(role)
    actor = require_membership(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        permission="organization.manage",
    )
    member = require_membership(db, organization_id=organization_id, user_id=member_user_id)
    if (member.role == "owner" or role == "owner") and actor.role != "owner":
        raise TenancyError("only an owner can manage owner roles")
    if member.role == "owner" and role != "owner":
        _ensure_another_owner(db, organization_id, member.user_id)
    member.role = role
    _audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="organization.member_role_changed",
        data={"user_id": member_user_id, "role": role},
    )
    return member


def remove_member(
    db: Session, *, organization_id: int, actor_user_id: int, member_user_id: int
) -> None:
    actor = require_membership(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        permission="organization.manage",
    )
    member = require_membership(db, organization_id=organization_id, user_id=member_user_id)
    if member.role == "owner" and actor.role != "owner":
        raise TenancyError("only an owner can remove an owner")
    if member.role == "owner":
        _ensure_another_owner(db, organization_id, member.user_id)
    db.delete(member)
    _audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="organization.member_removed",
        data={"user_id": member_user_id},
    )


def _ensure_another_owner(db: Session, organization_id: int, user_id: int) -> None:
    owners = list(
        db.scalars(
            select(OrganizationMember.id).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == "owner",
                OrganizationMember.user_id != user_id,
            )
        ).all()
    )
    if not owners:
        raise TenancyError("organization must retain an owner")


def create_invitation(
    db: Session, *, organization_id: int, actor_user_id: int, email: str, role: str
) -> tuple[OrganizationInvitation, str]:
    role = _valid_role(role)
    actor = require_membership(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        permission="organization.manage",
    )
    if role == "owner" and actor.role != "owner":
        raise TenancyError("only an owner can invite an owner")
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise TenancyError("email is required")
    token = token_urlsafe(32)
    token_hash = sha256(token.encode()).hexdigest()
    invitation = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.organization_id == organization_id,
            OrganizationInvitation.email == normalized_email,
        )
    )
    if invitation is None:
        invitation = OrganizationInvitation(organization_id=organization_id, email=normalized_email)
        db.add(invitation)
    invitation.role = role
    invitation.token_hash = token_hash
    invitation.expires_at = _now() + timedelta(days=INVITATION_TTL_DAYS)
    invitation.accepted_at = None
    invitation.invited_by_user_id = actor_user_id
    _audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action="organization.invited",
        data={"email": normalized_email, "role": role},
    )
    return invitation, token


def accept_invitation(db: Session, *, user: User, token: str) -> OrganizationMember:
    invitation = db.scalar(
        select(OrganizationInvitation).where(
            OrganizationInvitation.token_hash == sha256(token.encode()).hexdigest()
        )
    )
    if (
        invitation is None
        or invitation.accepted_at is not None
        or _aware(invitation.expires_at) <= _now()
    ):
        raise TenancyError("invitation is invalid or expired")
    if invitation.email.casefold() != user.email.casefold():
        raise TenancyError("invitation email does not match authenticated user")
    member = membership_for_user(db, organization_id=invitation.organization_id, user_id=user.id)
    if member is None:
        member = OrganizationMember(
            organization_id=invitation.organization_id, user_id=user.id, role=invitation.role
        )
        db.add(member)
    invitation.accepted_at = _now()
    user.organization_id = invitation.organization_id
    db.add(user)
    _audit(
        db,
        organization_id=invitation.organization_id,
        actor_user_id=user.id,
        action="organization.invitation_accepted",
        data={"user_id": user.id, "role": invitation.role},
    )
    return member
