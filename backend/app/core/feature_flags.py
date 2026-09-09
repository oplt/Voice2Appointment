"""Global kill switches for new product-domain surfaces (Phase 3).

Contract: global domain flags are interpreted as *product availability* gates.

* When a domain flag is OFF, the corresponding HTTP surfaces are considered
  unavailable (HTTP 404 via exception mapping).
* When a domain flag is OFF, capability-aware voice tools are not exposed.

Per-organization entitlements/permissions still gate tools when flags are ON.
Legacy calendar appointment tools remain available when flags are OFF.
"""

from __future__ import annotations

from functools import lru_cache

from app.core.config import settings

# Capabilities that require ENABLE_CATALOG_DOMAIN / reservation / industry flags.
_CATALOG_CAPS = frozenset({"catalog", "pricing", "payments", "orders", "lead", "knowledge"})
_RESERVATION_CAPS = frozenset({"reservation", "waitlist"})
_INDUSTRY_CAPS = frozenset({"clinic", "ehr_port", "salon", "restaurant"})


class FeatureDisabledError(RuntimeError):
    """Raised when a product-domain API is called while its kill switch is off."""


def catalog_domain_enabled() -> bool:
    return bool(settings.enable_catalog_domain)


def reservation_domain_enabled() -> bool:
    return bool(settings.enable_reservation_domain)


def industry_voice_tools_enabled() -> bool:
    return bool(settings.enable_industry_voice_tools)


def require_catalog_domain() -> None:
    if not catalog_domain_enabled():
        raise FeatureDisabledError("catalog domain disabled (ENABLE_CATALOG_DOMAIN=false)")


def require_reservation_domain() -> None:
    if not reservation_domain_enabled():
        raise FeatureDisabledError(
            "reservation domain disabled (ENABLE_RESERVATION_DOMAIN=false)"
        )


def require_industry_voice_tools() -> None:
    if not industry_voice_tools_enabled():
        raise FeatureDisabledError(
            "industry voice tools disabled (ENABLE_INDUSTRY_VOICE_TOOLS=false)"
        )


def capability_allowed(capability: str) -> bool:
    """Whether a tool capability may be exposed given global kill switches."""
    cap = (capability or "").strip().lower()
    if cap in _CATALOG_CAPS and not catalog_domain_enabled():
        return False
    if cap in _RESERVATION_CAPS and not reservation_domain_enabled():
        return False
    if cap in _INDUSTRY_CAPS and not industry_voice_tools_enabled():
        return False
    return True


@lru_cache(maxsize=1)
def flag_snapshot() -> dict[str, bool]:
    """Bounded public snapshot for health/acceptance (no secrets)."""
    return {
        "catalog_domain": catalog_domain_enabled(),
        "reservation_domain": reservation_domain_enabled(),
        "industry_voice_tools": industry_voice_tools_enabled(),
    }


def clear_flag_cache() -> None:
    flag_snapshot.cache_clear()
