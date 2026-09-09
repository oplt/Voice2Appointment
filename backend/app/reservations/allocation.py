"""Resource allocation for single_resource, multi_resource, and capacity modes."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from itertools import combinations
from typing import Iterable

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    Reservation,
    ReservationResource,
    Resource,
    ResourceAdjacency,
    ResourceCapability,
    ServiceResourceRequirement,
)
from app.reservations.types import ResourceAllocation, SchedulingMode

_ACTIVE_STATUSES = frozenset({"held", "confirmed", "pending", "pending_provider"})
_EXCLUSIVE_CAPACITY_TYPES = frozenset({"table", "dining_area"})
_COMBO_MAX_TABLES = 3


class AllocationError(ValueError):
    """Requested slot cannot allocate required resources."""


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def infer_scheduling_mode(
    requirements: list[ServiceResourceRequirement],
    *,
    party_size: int = 1,
) -> SchedulingMode:
    if not requirements:
        return "single_resource"
    types = {(req.resource_type or "").casefold() for req in requirements}
    if "capacity_pool" in types or party_size > 1 and any(
        (req.quantity or 1) > 1 or (req.resource_type or "").casefold() in {"table", "dining_area"}
        for req in requirements
    ):
        return "capacity"
    if len(requirements) > 1:
        return "multi_resource"
    return "single_resource"


def _hold_still_active(reservation: Reservation, now: datetime | None = None) -> bool:
    if reservation.status != "held":
        return reservation.status in _ACTIVE_STATUSES
    if reservation.hold_expires_at is None:
        return True
    return _aware(reservation.hold_expires_at) > (now or _utcnow())


def overlapping_resource_usage(
    db: Session,
    *,
    organization_id: int,
    start: datetime,
    end: datetime,
    resource_ids: Iterable[int],
    exclude_reservation_id: int | None = None,
) -> dict[int, int]:
    """Return quantity already allocated per resource in the overlapping window."""
    ids = list(resource_ids)
    if not ids:
        return {}
    start = _aware(start)
    end = _aware(end)
    stmt: Select[tuple[Reservation, int, int]] = (
        select(Reservation, ReservationResource.resource_id, ReservationResource.quantity)
        .join(ReservationResource, Reservation.id == ReservationResource.reservation_id)
        .where(
            Reservation.organization_id == organization_id,
            Reservation.start_datetime < end,
            Reservation.end_datetime > start,
            Reservation.status.in_(tuple(_ACTIVE_STATUSES)),
            ReservationResource.resource_id.in_(ids),
        )
    )
    if exclude_reservation_id is not None:
        stmt = stmt.where(Reservation.id != exclude_reservation_id)
    usage: dict[int, int] = {resource_id: 0 for resource_id in ids}
    now = _utcnow()
    for reservation, resource_id, quantity in db.execute(stmt):
        if not _hold_still_active(reservation, now):
            continue
        usage[int(resource_id)] = usage.get(int(resource_id), 0) + int(quantity)
    return usage


def _resource_capabilities(db: Session, resource_ids: list[int]) -> dict[int, set[str]]:
    if not resource_ids:
        return {}
    rows = db.execute(
        select(ResourceCapability.resource_id, ResourceCapability.capability).where(
            ResourceCapability.resource_id.in_(resource_ids)
        )
    )
    caps: dict[int, set[str]] = {resource_id: set() for resource_id in resource_ids}
    for resource_id, capability in rows:
        caps[int(resource_id)].add(str(capability).casefold())
    return caps


def _candidate_resources(
    db: Session,
    *,
    organization_id: int,
    location_id: int | None,
    resource_type: str | None,
    capability: str | None,
    preferred_resource_ids: tuple[int, ...],
    extra_capabilities: tuple[str, ...] = (),
) -> list[Resource]:
    stmt = select(Resource).where(
        Resource.organization_id == organization_id,
        Resource.active.is_(True),
    )
    if location_id is not None:
        stmt = stmt.where(
            or_(Resource.location_id == location_id, Resource.location_id.is_(None))
        )
    if resource_type:
        stmt = stmt.where(Resource.resource_type == resource_type)
    resources = list(db.scalars(stmt).all())
    if preferred_resource_ids:
        preferred = {rid for rid in preferred_resource_ids}
        resources = sorted(
            resources,
            key=lambda resource: (0 if resource.id in preferred else 1, resource.id),
        )
    # Request-level capabilities apply only to skilled roles / capability-tagged
    # requirements — never to chairs, rooms, or capacity pools.
    skilled_types = {"employee", "practitioner", "staff", "provider"}
    apply_extra = bool(capability) or (resource_type or "").casefold() in skilled_types
    needed = {
        value.casefold()
        for value in ((capability,) if capability else ())
        + (tuple(extra_capabilities) if apply_extra else ())
        if value
    }
    if not needed:
        return resources
    caps = _resource_capabilities(db, [resource.id for resource in resources])
    return [
        resource
        for resource in resources
        if needed.issubset(caps.get(resource.id, set()))
    ]


def _adjacency_neighbor_ids(
    db: Session,
    *,
    organization_id: int,
    resource_ids: set[int],
) -> set[int]:
    if not resource_ids:
        return set()
    rows = db.execute(
        select(ResourceAdjacency.resource_a_id, ResourceAdjacency.resource_b_id).where(
            ResourceAdjacency.organization_id == organization_id,
            ResourceAdjacency.active.is_(True),
            or_(
                ResourceAdjacency.resource_a_id.in_(resource_ids),
                ResourceAdjacency.resource_b_id.in_(resource_ids),
            ),
        )
    )
    neighbors: set[int] = set()
    for left, right in rows:
        neighbors.add(int(left))
        neighbors.add(int(right))
    return neighbors


def _load_adjacency_graph(
    db: Session,
    *,
    organization_id: int,
    resource_ids: Iterable[int],
) -> dict[int, set[int]]:
    ids = {int(resource_id) for resource_id in resource_ids}
    if not ids:
        return {}
    rows = db.execute(
        select(ResourceAdjacency.resource_a_id, ResourceAdjacency.resource_b_id).where(
            ResourceAdjacency.organization_id == organization_id,
            ResourceAdjacency.active.is_(True),
            ResourceAdjacency.resource_a_id.in_(ids),
            ResourceAdjacency.resource_b_id.in_(ids),
        )
    )
    graph: dict[int, set[int]] = defaultdict(set)
    for left, right in rows:
        a, b = int(left), int(right)
        graph[a].add(b)
        graph[b].add(a)
    return graph


def matching_resource_ids(
    db: Session,
    *,
    organization_id: int,
    location_id: int | None,
    requirements: list[ServiceResourceRequirement],
    preferred_resource_ids: tuple[int, ...] = (),
    required_capabilities: tuple[str, ...] = (),
) -> tuple[int, ...]:
    """Return every resource that could satisfy the requested allocation.

    Callers use this set to acquire deterministic resource locks before the
    allocation's overlapping-usage query is evaluated. Adjacency neighbors of
    table/dining candidates are included so combo bookings lock the full set.
    """
    resource_ids: set[int] = set()
    for requirement in requirements:
        if not requirement.required:
            continue
        resource_ids.update(
            resource.id
            for resource in _candidate_resources(
                db,
                organization_id=organization_id,
                location_id=location_id,
                resource_type=requirement.resource_type,
                capability=requirement.capability,
                preferred_resource_ids=preferred_resource_ids,
                extra_capabilities=required_capabilities,
            )
        )
    resource_ids |= _adjacency_neighbor_ids(
        db, organization_id=organization_id, resource_ids=resource_ids
    )
    return tuple(sorted(resource_ids))


def _pick_exclusive(
    candidates: list[Resource],
    usage: dict[int, int],
    *,
    quantity: int,
) -> ResourceAllocation | None:
    for resource in candidates:
        remaining = resource.capacity - usage.get(resource.id, 0)
        if remaining >= quantity:
            return ResourceAllocation(
                resource_id=resource.id,
                resource_name=resource.name,
                resource_type=resource.resource_type,
                quantity=quantity,
            )
    return None


def _pick_capacity(
    candidates: list[Resource],
    usage: dict[int, int],
    *,
    party_size: int,
) -> ResourceAllocation | None:
    # Prefer smallest resource that still fits the party.
    ranked = sorted(
        candidates,
        key=lambda resource: (
            resource.capacity,
            usage.get(resource.id, 0),
            resource.id,
        ),
    )
    for resource in ranked:
        remaining = resource.capacity - usage.get(resource.id, 0)
        if remaining >= party_size:
            return ResourceAllocation(
                resource_id=resource.id,
                resource_name=resource.name,
                resource_type=resource.resource_type,
                quantity=party_size,
            )
    return None


def _is_connected(node_ids: set[int], graph: dict[int, set[int]]) -> bool:
    if not node_ids:
        return False
    start = next(iter(node_ids))
    seen = {start}
    stack = [start]
    while stack:
        current = stack.pop()
        for neighbor in graph.get(current, ()):
            if neighbor in node_ids and neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return seen == node_ids


def _pick_capacity_combo(
    candidates: list[Resource],
    usage: dict[int, int],
    graph: dict[int, set[int]],
    *,
    party_size: int,
) -> list[ResourceAllocation] | None:
    """Combine adjacent exclusive tables/dining areas (max 3) to fit party_size."""
    free = [
        r
        for r in candidates
        if usage.get(r.id, 0) <= 0
        and (r.resource_type or "").casefold() in _EXCLUSIVE_CAPACITY_TYPES
    ]
    if len(free) < 2:
        return None
    by_id = {r.id: r for r in free}
    free_ids = sorted(by_id)
    best: tuple[int, int, tuple[int, ...]] | None = None
    for size in range(2, min(_COMBO_MAX_TABLES, len(free_ids)) + 1):
        for combo in combinations(free_ids, size):
            if not _is_connected(set(combo), graph):
                continue
            total = sum(by_id[rid].capacity for rid in combo)
            if total < party_size:
                continue
            key = (size, total - party_size, combo)
            if best is None or key < best:
                best = key
        if best is not None and best[0] == size:
            break
    if best is None:
        return None
    return [
        ResourceAllocation(
            resource_id=rid,
            resource_name=by_id[rid].name,
            resource_type=by_id[rid].resource_type,
            quantity=by_id[rid].capacity,
        )
        for rid in best[2]
    ]


def allocate_resources(
    db: Session,
    *,
    organization_id: int,
    location_id: int | None,
    start: datetime,
    end: datetime,
    requirements: list[ServiceResourceRequirement],
    party_size: int = 1,
    preferred_resource_ids: tuple[int, ...] = (),
    allowed_resource_ids: tuple[int, ...] = (),
    required_capabilities: tuple[str, ...] = (),
    scheduling_mode: SchedulingMode | None = None,
    exclude_reservation_id: int | None = None,
) -> tuple[SchedulingMode, list[ResourceAllocation]]:
    """Authoritatively allocate resources for a concrete time window."""
    mode = scheduling_mode or infer_scheduling_mode(requirements, party_size=party_size)
    if not requirements:
        return mode, []

    allocations: list[ResourceAllocation] = []
    claimed: set[int] = set()
    for requirement in requirements:
        if not requirement.required:
            continue
        candidates = [
            resource
            for resource in _candidate_resources(
                db,
                organization_id=organization_id,
                location_id=location_id,
                resource_type=requirement.resource_type,
                capability=requirement.capability,
                preferred_resource_ids=preferred_resource_ids,
                extra_capabilities=required_capabilities,
            )
            if resource.id not in claimed
        ]
        if allowed_resource_ids:
            allowed = set(allowed_resource_ids)
            candidates = [resource for resource in candidates if resource.id in allowed]
        if not candidates:
            raise AllocationError("no matching resources for requirement")
        usage = overlapping_resource_usage(
            db,
            organization_id=organization_id,
            start=start,
            end=end,
            resource_ids=[resource.id for resource in candidates],
            exclude_reservation_id=exclude_reservation_id,
        )
        quantity = max(1, int(requirement.quantity or 1))
        if mode == "capacity":
            need = max(party_size, quantity)
            rtype = (requirement.resource_type or "").casefold()
            single = _pick_capacity(candidates, usage, party_size=need)
            if single is not None:
                picks = [single]
            elif rtype in _EXCLUSIVE_CAPACITY_TYPES:
                graph = _load_adjacency_graph(
                    db,
                    organization_id=organization_id,
                    resource_ids=[resource.id for resource in candidates],
                )
                picks = _pick_capacity_combo(candidates, usage, graph, party_size=need) or []
                if not picks:
                    raise AllocationError("insufficient resource capacity for requested slot")
            else:
                raise AllocationError("insufficient resource capacity for requested slot")
        else:
            pick = _pick_exclusive(candidates, usage, quantity=quantity)
            if pick is None:
                raise AllocationError("insufficient resource capacity for requested slot")
            picks = [pick]
        for pick in picks:
            allocations.append(pick)
            claimed.add(pick.resource_id)

    if mode == "single_resource" and len(allocations) > 1:
        mode = "multi_resource"
    return mode, allocations
