"""Authenticated organization and location HTTP API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.db.models import (
    Location,
    Organization,
    OrganizationInvitation,
    OrganizationMember,
    User,
)
from app.tenancy import service as tenancy_service

router = APIRouter(tags=["organization"])


@dataclass(frozen=True)
class OrganizationContext:
    organization_id: int
    user: User
    membership: OrganizationMember


def organization_context_for_user(
    current_user: User = Depends(get_current_user), db: Session = Depends(require_db)
) -> OrganizationContext:
    """The only organization scope accepted by product-domain routes."""
    if current_user.organization_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization required")
    membership = tenancy_service.membership_for_user(
        db, organization_id=current_user.organization_id, user_id=current_user.id
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Organization membership required"
        )
    return OrganizationContext(current_user.organization_id, current_user, membership)


def organization_id_for_user(
    context: OrganizationContext = Depends(organization_context_for_user),
) -> int:
    return context.organization_id


OrganizationId = Annotated[int, Depends(organization_id_for_user)]


def require_org_permission(permission: str):
    def dependency(
        context: OrganizationContext = Depends(organization_context_for_user),
    ) -> int:
        if not tenancy_service.has_permission(context.membership, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Organization permission required"
            )
        return context.organization_id

    return dependency


def require_any_org_permission(*permissions: str):
    def dependency(
        context: OrganizationContext = Depends(organization_context_for_user),
    ) -> int:
        if not any(
            tenancy_service.has_permission(context.membership, permission)
            for permission in permissions
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Organization permission required"
            )
        return context.organization_id

    return dependency


def require_domain_permission(domain: str):
    def dependency(
        request: Request,
        context: OrganizationContext = Depends(organization_context_for_user),
    ) -> None:
        read_only = request.method == "GET" or request.url.path.endswith("/availability")
        permission = f"{domain}.{'read' if read_only else 'write'}"
        if not tenancy_service.has_permission(context.membership, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Organization permission required"
            )

    return dependency


def require_resources_permission():
    """GET needs resources.read; mutations need resources.write; org.manage always allowed."""

    def dependency(
        request: Request,
        context: OrganizationContext = Depends(organization_context_for_user),
    ) -> int:
        if tenancy_service.has_permission(context.membership, "organization.manage"):
            return context.organization_id
        needed = "resources.read" if request.method == "GET" else "resources.write"
        if not tenancy_service.has_permission(context.membership, needed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Organization permission required"
            )
        return context.organization_id

    return dependency


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    slug: str


class LocationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    business_hours: dict[str, Any] = Field(default_factory=dict)


class LocationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    address: str | None = None
    phone: str | None = Field(default=None, max_length=32)
    business_hours: dict[str, Any] | None = None


class LocationOut(LocationIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MemberRoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(pattern="^(owner|admin|manager|staff|viewer)$")


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    user_id: int
    role: str


class InvitationIn(MemberRoleIn):
    email: str = Field(min_length=3, max_length=255)


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    role: str
    expires_at: datetime
    accepted_at: datetime | None


class InvitationCreated(InvitationOut):
    token: str


class InvitationAcceptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=512)


class OrganizationMembershipOut(OrganizationOut):
    role: str
    active: bool


@router.get("/organizations", response_model=list[OrganizationMembershipOut])
def list_organizations(
    current_user: User = Depends(get_current_user), db: Session = Depends(require_db)
) -> list[OrganizationMembershipOut]:
    organizations = tenancy_service.list_organizations_for_user(db, user_id=current_user.id)
    out: list[OrganizationMembershipOut] = []
    for organization in organizations:
        member = tenancy_service.membership_for_user(
            db, organization_id=organization.id, user_id=current_user.id
        )
        if member is None:
            continue
        out.append(
            OrganizationMembershipOut(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                role=member.role,
                active=current_user.organization_id == organization.id,
            )
        )
    return out


@router.get("/organizations/me", response_model=OrganizationOut)
def get_organization(
    organization_id: OrganizationId, db: Session = Depends(require_db)
) -> Organization:
    organization = db.get(Organization, organization_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


@router.get("/locations", response_model=list[LocationOut])
def list_locations(
    organization_id: OrganizationId, db: Session = Depends(require_db)
) -> list[Location]:
    return list(
        db.scalars(
            select(Location)
            .where(Location.organization_id == organization_id)
            .order_by(Location.name)
        ).all()
    )


@router.post("/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationIn,
    organization_id: Annotated[
        int, Depends(require_any_org_permission("organization.manage", "locations.write"))
    ],
    db: Session = Depends(require_db),
) -> Location:
    row = Location(organization_id=organization_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/locations/{location_id}", response_model=LocationOut)
def patch_location(
    location_id: int,
    payload: LocationPatch,
    organization_id: Annotated[
        int, Depends(require_any_org_permission("organization.manage", "locations.write"))
    ],
    db: Session = Depends(require_db),
) -> Location:
    row = db.scalar(
        select(Location).where(
            Location.id == location_id, Location.organization_id == organization_id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Location not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


@router.post("/organizations/{organization_id}/activate", response_model=OrganizationOut)
def activate_organization(
    organization_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Organization:
    try:
        organization = tenancy_service.switch_active_organization(
            db, user=current_user, organization_id=organization_id
        )
        db.commit()
        db.refresh(current_user)
        return organization
    except tenancy_service.TenancyError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/organizations/members", response_model=list[MemberOut])
def list_organization_members(
    organization_id: Annotated[int, Depends(require_org_permission("organization.manage"))],
    db: Session = Depends(require_db),
) -> list[OrganizationMember]:
    return tenancy_service.list_members(db, organization_id=organization_id)


@router.patch("/organizations/members/{user_id}", response_model=MemberOut)
def patch_organization_member(
    user_id: int,
    payload: MemberRoleIn,
    organization_id: Annotated[int, Depends(require_org_permission("organization.manage"))],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> OrganizationMember:
    try:
        row = tenancy_service.set_member_role(
            db,
            organization_id=organization_id,
            actor_user_id=current_user.id,
            member_user_id=user_id,
            role=payload.role,
        )
        db.commit()
        db.refresh(row)
        return row
    except tenancy_service.TenancyError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete(
    "/organizations/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_organization_member(
    user_id: int,
    organization_id: Annotated[int, Depends(require_org_permission("organization.manage"))],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> Response:
    try:
        tenancy_service.remove_member(
            db,
            organization_id=organization_id,
            actor_user_id=current_user.id,
            member_user_id=user_id,
        )
        db.commit()
    except tenancy_service.TenancyError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/organizations/invitations", response_model=list[InvitationOut])
def list_organization_invitations(
    organization_id: Annotated[int, Depends(require_org_permission("organization.manage"))],
    db: Session = Depends(require_db),
) -> list[OrganizationInvitation]:
    return list(
        db.scalars(
            select(OrganizationInvitation)
            .where(OrganizationInvitation.organization_id == organization_id)
            .order_by(OrganizationInvitation.created_at.desc())
        ).all()
    )


@router.post(
    "/organizations/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_organization_invitation(
    payload: InvitationIn,
    organization_id: Annotated[int, Depends(require_org_permission("organization.manage"))],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> InvitationCreated:
    try:
        row, token = tenancy_service.create_invitation(
            db,
            organization_id=organization_id,
            actor_user_id=current_user.id,
            email=payload.email,
            role=payload.role,
        )
        db.commit()
        db.refresh(row)
        return InvitationCreated(**InvitationOut.model_validate(row).model_dump(), token=token)
    except tenancy_service.TenancyError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/organizations/invitations/accept", response_model=MemberOut)
def accept_organization_invitation(
    payload: InvitationAcceptIn,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> OrganizationMember:
    try:
        member = tenancy_service.accept_invitation(db, user=current_user, token=payload.token)
        db.commit()
        db.refresh(member)
        return member
    except tenancy_service.TenancyError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
