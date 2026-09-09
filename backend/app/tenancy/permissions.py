"""Role and permission matrices for organization membership."""

from __future__ import annotations

from app.db.models import OrganizationMember

ROLES = frozenset({"owner", "admin", "manager", "staff", "viewer"})
PERMISSIONS = frozenset(
    {
        "catalog.read",
        "catalog.write",
        "pricing.read",
        "pricing.write",
        "reservation.read",
        "reservation.write",
        "customer.read",
        "customer.write",
        "resources.read",
        "resources.write",
        "locations.write",
        "agent.manage",
        "analytics.read",
        "integration.manage",
        "organization.manage",
        "privacy.manage",
    }
)
_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": PERMISSIONS,
    "admin": PERMISSIONS,
    "manager": frozenset(
        {
            "catalog.read",
            "catalog.write",
            "pricing.read",
            "pricing.write",
            "reservation.read",
            "reservation.write",
            "customer.read",
            "customer.write",
            "resources.read",
            "resources.write",
            "locations.write",
            "agent.manage",
            "analytics.read",
        }
    ),
    "staff": frozenset(
        {
            "catalog.read",
            "pricing.read",
            "reservation.read",
            "reservation.write",
            "customer.read",
            "customer.write",
            "resources.read",
        }
    ),
    "viewer": frozenset(
        {
            "catalog.read",
            "pricing.read",
            "reservation.read",
            "customer.read",
            "resources.read",
            "analytics.read",
        }
    ),
}


class TenancyError(ValueError):
    """Safe tenancy and authorization policy violation."""


def _valid_role(role: str) -> str:
    normalized = role.strip().lower()
    if normalized not in ROLES:
        raise TenancyError("role must be owner, admin, manager, staff, or viewer")
    return normalized


def permissions_for_role(role: str) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def has_permission(member: OrganizationMember, permission: str) -> bool:
    return permission in permissions_for_role(member.role)


