"""User settings HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session

from app.appointments.policy import BookingPolicy, load_booking_policy, save_booking_policy
from app.auth.deps import get_current_user, require_db
from app.core.errors import ConflictAppError, map_exception, raise_http
from app.db.models import User
from app.users import service as users_service
from app.users.product_prefs import (
    ProductPrefs,
    grant_notification_consent,
    load_product_prefs,
    save_product_prefs,
)
from app.users.readiness import compute_readiness

router = APIRouter(prefix="/users", tags=["users"])


class UserSettingsOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    image_file: str
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    has_twilio: bool = False
    has_deepgram: bool = False
    twilio_auth_token_set: bool = False


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str | None = Field(default=None, min_length=2, max_length=50)
    email: EmailStr | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_legacy_deepgram_key(cls, value: object) -> object:
        """Reject the removed tenant credential with a stable compatibility error."""
        if isinstance(value, dict) and "deepgram_api_key" in value:
            raise PydanticCustomError(
                "deprecated_credential_source",
                "deepgram_api_key is no longer accepted; configure DEEPGRAM_API_KEY on the server.",
            )
        return value


@router.get("/me", response_model=UserSettingsOut)
def get_me_settings(
    current_user: User = Depends(get_current_user),
) -> UserSettingsOut:
    return UserSettingsOut(**users_service.get_settings(current_user))


@router.patch("/me", response_model=UserSettingsOut)
def patch_me_settings(
    payload: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> UserSettingsOut:
    try:
        user = users_service.update_settings(
            db, current_user, payload.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise_http(map_exception(exc))
    except Exception as exc:
        from sqlalchemy.exc import IntegrityError

        if isinstance(exc, IntegrityError):
            raise_http(
                ConflictAppError("twilio_phone_number already in use", cause=exc)
            )
        raise
    return UserSettingsOut(**users_service.get_settings(user))


@router.get("/me/booking-policy", response_model=BookingPolicy)
def get_booking_policy(
    current_user: User = Depends(get_current_user),
) -> BookingPolicy:
    return load_booking_policy(current_user.config_json)


@router.put("/me/booking-policy", response_model=BookingPolicy)
def put_booking_policy(
    payload: BookingPolicy,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> BookingPolicy:
    try:
        save_booking_policy(current_user, payload)
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    except Exception as exc:
        db.rollback()
        raise_http(map_exception(exc))
    return load_booking_policy(current_user.config_json)


@router.get("/me/product-prefs", response_model=ProductPrefs)
def get_product_prefs(
    current_user: User = Depends(get_current_user),
) -> ProductPrefs:
    return load_product_prefs(current_user.config_json)


@router.put("/me/product-prefs", response_model=ProductPrefs)
def put_product_prefs(
    payload: ProductPrefs,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> ProductPrefs:
    try:
        prefs = payload
        notif = prefs.notifications
        if (
            notif.confirmations_enabled or notif.reminders_enabled
        ) and not notif.consent_at:
            notif = grant_notification_consent(notif)
            prefs = prefs.model_copy(update={"notifications": notif})
        langs = prefs.languages.model_copy(update={"primary": "en", "enabled": ["en"]})
        prefs = prefs.model_copy(update={"languages": langs})
        save_product_prefs(current_user, prefs)
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    except Exception as exc:
        db.rollback()
        raise_http(map_exception(exc))
    return load_product_prefs(current_user.config_json)


@router.get("/me/readiness")
def get_readiness(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    return compute_readiness(db, current_user)


@router.get("/me/notifications/deliveries")
def list_notification_deliveries(
    appointment_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(require_db),
) -> dict:
    from app.notifications.service import list_delivery_status

    return {
        "items": list_delivery_status(
            db, current_user.id, appointment_id=appointment_id
        )
    }
