"""Token-authenticated payment capture HTTP API."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth.deps import require_db
from app.core.feature_flags import require_catalog_domain
from app.core.thread_db import to_thread_db
from app.payments import service as payments_service
from app.payments.providers import verify_stripe_webhook
from app.payments.service import PaymentError

router = APIRouter(
    prefix="/payments",
    tags=["payments"],
    dependencies=[Depends(require_catalog_domain)],
)


class CaptureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str | None = Field(default=None, min_length=1, max_length=256)
    provider_ref: str | None = Field(default=None, max_length=255)


class PaymentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: int
    organization_id: int
    reservation_id: int | None
    amount_minor: int
    currency: str
    purpose: str
    provider: str
    status: str
    checkout_url: str | None = None
    link_expired: bool = False
    expires_at: str | None = None


@router.get("/by-token", response_model=PaymentOut)
def get_payment_by_token(
    token: str = Query(min_length=1, max_length=256),
    db: Session = Depends(require_db),
) -> dict[str, Any]:
    intent = payments_service.find_payment_by_token(db, token)
    if intent is None:
        raise HTTPException(status_code=404, detail="Payment not found")
    return payments_service.payment_public_view(intent, db)


@router.post("/{payment_id}/capture", response_model=PaymentOut)
def capture_payment(
    payment_id: int,
    payload: CaptureIn,
    db: Session = Depends(require_db),
) -> dict[str, Any]:
    try:
        intent = payments_service.capture_payment(
            db,
            payment_id,
            token=payload.token,
            provider_ref=payload.provider_ref,
        )
    except PaymentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payments_service.payment_public_view(intent, db)


def _stripe_webhook_work(
    db: Session, payload: bytes, sig: str | None
) -> dict[str, Any]:
    try:
        event = verify_stripe_webhook(payload, sig)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid stripe webhook") from exc

    event_type = event.get("type") if isinstance(event, dict) else None
    data_object = ((event.get("data") or {}) if isinstance(event, dict) else {}).get(
        "object"
    ) or {}
    if event_type == "checkout.session.completed":
        meta = data_object.get("metadata") or {}
        payment_id = meta.get("payment_intent_id")
        if payment_id:
            try:
                payments_service.capture_payment(
                    db,
                    int(payment_id),
                    provider_ref=str(data_object.get("id") or ""),
                )
            except PaymentError:
                pass
    return {"received": True}


@router.post("/stripe/webhook", status_code=status.HTTP_200_OK)
async def stripe_webhook(request: Request) -> dict[str, Any]:
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    return await to_thread_db(_stripe_webhook_work, payload, sig)
