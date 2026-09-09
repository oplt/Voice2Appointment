import asyncio

import httpx
from fastapi import Depends, FastAPI

from app.core import feature_flags
from app.core.errors import register_exception_handlers
from app.core.feature_flags import (
    clear_flag_cache,
    require_catalog_domain,
    require_reservation_domain,
)


def test_feature_disabled_dependencies_map_to_404(monkeypatch) -> None:
    monkeypatch.setattr(feature_flags, "catalog_domain_enabled", lambda: False)
    monkeypatch.setattr(feature_flags, "reservation_domain_enabled", lambda: False)
    clear_flag_cache()

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/catalog-test", dependencies=[Depends(require_catalog_domain)])
    def _catalog() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/reservation-test", dependencies=[Depends(require_reservation_domain)])
    def _reservation() -> dict[str, bool]:
        return {"ok": True}

    async def _run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            resp = await client.get("/catalog-test")
            assert resp.status_code == 404
            assert resp.json()["detail"]["code"] == "not_found"

            resp = await client.get("/reservation-test")
            assert resp.status_code == 404
            assert resp.json()["detail"]["code"] == "not_found"

            # Enabled: routes behave normally.
            monkeypatch.setattr(feature_flags, "catalog_domain_enabled", lambda: True)
            monkeypatch.setattr(feature_flags, "reservation_domain_enabled", lambda: True)
            clear_flag_cache()

            resp = await client.get("/catalog-test")
            assert resp.status_code == 200

            resp = await client.get("/reservation-test")
            assert resp.status_code == 200

    asyncio.run(_run())
