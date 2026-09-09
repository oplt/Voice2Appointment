"""Tenancy roles, active organization, and invitation invariants."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Organization, OrganizationMember, User
from app.tenancy.service import (
    TenancyError,
    accept_invitation,
    create_invitation,
    has_permission,
    membership_for_user,
    remove_member,
    require_membership,
    switch_active_organization,
)


def _session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_roles_expose_least_privilege_permissions() -> None:
    db = _session()
    org = Organization(name="Clinic", slug="clinic")
    viewer = User(username="viewer", email="viewer@example.test", password="x")
    db.add_all((org, viewer))
    db.flush()
    member = OrganizationMember(organization_id=org.id, user_id=viewer.id, role="viewer")
    db.add(member)
    db.commit()

    assert has_permission(member, "catalog.read")
    assert has_permission(member, "analytics.read")
    assert has_permission(member, "resources.read")
    assert not has_permission(member, "catalog.write")
    assert not has_permission(member, "resources.write")
    assert not has_permission(member, "agent.manage")
    assert not has_permission(member, "locations.write")
    assert not has_permission(member, "organization.manage")
    with pytest.raises(TenancyError, match="permission"):
        require_membership(
            db,
            organization_id=org.id,
            user_id=viewer.id,
            permission="catalog.write",
        )


def test_invitation_acceptance_switches_to_a_verified_membership() -> None:
    db = _session()
    first = Organization(name="First", slug="first-rbac")
    second = Organization(name="Second", slug="second-rbac")
    owner = User(username="owner", email="owner@example.test", password="x")
    invitee = User(username="invitee", email="invitee@example.test", password="x")
    db.add_all((first, second, owner, invitee))
    db.flush()
    owner.organization_id = first.id
    invitee.organization_id = second.id
    db.add_all(
        (
            OrganizationMember(organization_id=first.id, user_id=owner.id, role="owner"),
            OrganizationMember(organization_id=second.id, user_id=invitee.id, role="viewer"),
        )
    )
    db.commit()

    invitation, token = create_invitation(
        db,
        organization_id=first.id,
        actor_user_id=owner.id,
        email=invitee.email,
        role="staff",
    )
    db.commit()
    accepted = accept_invitation(db, user=invitee, token=token)
    db.commit()
    db.refresh(invitee)
    db.refresh(invitation)

    assert accepted.role == "staff"
    assert invitation.accepted_at is not None
    assert invitee.organization_id == first.id
    assert membership_for_user(db, organization_id=first.id, user_id=invitee.id) is not None
    assert switch_active_organization(db, user=invitee, organization_id=second.id).id == second.id


def test_cannot_remove_the_last_owner() -> None:
    db = _session()
    org = Organization(name="Clinic", slug="owner-guard")
    owner = User(username="sole-owner", email="sole-owner@example.test", password="x")
    db.add_all((org, owner))
    db.flush()
    owner.organization_id = org.id
    db.add(OrganizationMember(organization_id=org.id, user_id=owner.id, role="owner"))
    db.commit()

    with pytest.raises(TenancyError, match="retain an owner"):
        remove_member(db, organization_id=org.id, actor_user_id=owner.id, member_user_id=owner.id)
