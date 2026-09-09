"""Application factory for web API and/or voice gateway (modular monolith)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.analytics.router import router as analytics_router
from app.appointments.router import router as appointments_router
from app.auth.router import router as auth_router
from app.calendars.router import router as calendars_router
from app.calls.router import router as calls_router
from app.catalog.api import router as catalog_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import (
    CSRF_HEADER_NAME,
    ContentLengthLimitMiddleware,
    CSRFMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.sentry import init_sentry
from app.customers.api import router as customers_router
from app.dashboard.router import router as dashboard_router
from app.health.router import router as health_router
from app.industries.api import router as industries_router
from app.payments.api import router as payments_router
from app.pricing.api import router as pricing_router
from app.reservations.api import router as reservations_router
from app.resources.api import router as resources_router
from app.telephony.router import router as telephony_router
from app.tenancy.api import router as tenancy_router
from app.users.router import router as users_router
from app.voice.gateway import router as voice_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.require_runtime_secrets()
    init_sentry()
    if settings.fhir_enabled and settings.fhir_base_url:
        from app.industries.ehr import set_ehr_adapter
        from app.industries.fhir import FhirEHRAdapter

        set_ehr_adapter(
            FhirEHRAdapter(
                base_url=settings.fhir_base_url,
                bearer_token=settings.fhir_bearer_token,
                enabled=True,
                timeout_seconds=settings.fhir_timeout_seconds,
            )
        )
    try:
        yield
    finally:
        from app.voice.tool_runtime import shutdown_voice_tool_runtime

        shutdown_voice_tool_runtime()


def create_app(
    *,
    include_api: bool = True,
    include_voice: bool = True,
    title: str | None = None,
) -> FastAPI:
    """Build a FastAPI app sharing domain code.

    Modes:
    - both True: local/dev all-in-one (HTTP + WebSocket)
    - include_api only: production web process
    - include_voice only: production voice gateway process
    """
    setup_logging()

    if title is None:
        if include_api and include_voice:
            title = "Voice2Appointment API"
        elif include_voice:
            title = "Voice2Appointment Voice Gateway"
        else:
            title = "Voice2Appointment Web API"

    application = FastAPI(
        title=title,
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
    )

    register_exception_handlers(application)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    if include_api:
        # Applied outermost-last among these: CORS → security → CSRF → app.
        application.add_middleware(ContentLengthLimitMiddleware)
        application.add_middleware(CSRFMiddleware)
        application.add_middleware(SecurityHeadersMiddleware)
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Accept",
                CSRF_HEADER_NAME,
                "X-CSRF-Token",
                "X-Request-ID",
                "X-Correlation-ID",
            ],
            expose_headers=["X-Request-ID", "X-Correlation-ID"],
        )

    # Outermost: request_id / structured HTTP timing for every process.
    application.add_middleware(RequestContextMiddleware)

    if include_api:
        application.include_router(auth_router, prefix="/api/v1")
        application.include_router(users_router, prefix="/api/v1")
        application.include_router(dashboard_router, prefix="/api/v1")
        application.include_router(appointments_router, prefix="/api/v1")
        application.include_router(calls_router, prefix="/api/v1")
        application.include_router(calendars_router, prefix="/api/v1")
        application.include_router(analytics_router, prefix="/api/v1")
        application.include_router(telephony_router, prefix="/api/v1")
        application.include_router(tenancy_router, prefix="/api/v1")
        application.include_router(catalog_router, prefix="/api/v1")
        application.include_router(pricing_router, prefix="/api/v1")
        application.include_router(resources_router, prefix="/api/v1")
        application.include_router(customers_router, prefix="/api/v1")
        application.include_router(reservations_router, prefix="/api/v1")
        application.include_router(industries_router, prefix="/api/v1")
        application.include_router(payments_router, prefix="/api/v1")

    if include_voice:
        application.include_router(voice_router)

    # Liveness/readiness on every process variant.
    application.include_router(health_router)

    return application
