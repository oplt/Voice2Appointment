"""User settings HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_db
from app.db.models import User
from app.users import service as users_service

router = APIRouter(prefix="/users", tags=["users"])


class UserSettingsOut(BaseModel):
    id: int
    username: str
    email: EmailStr
    image_file: str
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    deepgram_api_key: str | None = None
    config_json: str | None = None
    has_twilio: bool = False
    has_deepgram: bool = False
    twilio_auth_token_set: bool = False
    deepgram_api_key_set: bool = False


class UserSettingsUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=2, max_length=50)
    email: EmailStr | None = None
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_phone_number: str | None = None
    deepgram_api_key: str | None = None
    config_json: str | None = None


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
    user = users_service.update_settings(
        db, current_user, payload.model_dump(exclude_unset=True)
    )
    return UserSettingsOut(**users_service.get_settings(user))
