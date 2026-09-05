"""Per-tenant Deepgram voice configuration assembly."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from app.calendars.tool_schemas import AGENT_SYSTEM_PROMPT, VOICE_TOOL_DEFINITIONS
from app.db.models import User
from app.voice.context import CallContext
from app.voice.dates import get_current_date_context
from app.voice.providers.deepgram import get_deepgram_settings

logger = logging.getLogger(__name__)
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.json"


def load_default_config_template() -> dict:
    with open(_DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as config_file:
        return json.load(config_file)


def _deep_merge(base: dict, overlay: dict) -> dict:
    for key, value in overlay.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_voice_config_for_context(
    ctx: CallContext,
    session_factory: Callable[[], Session] | None,
) -> dict:
    config = load_default_config_template()
    if session_factory is not None:
        db = session_factory()
        try:
            user = db.get(User, ctx.user_id)
            if user and user.config_json:
                try:
                    overlay = json.loads(user.config_json)
                except json.JSONDecodeError:
                    logger.error(
                        "Invalid config_json for user_id=%s; using defaults",
                        ctx.user_id,
                    )
                else:
                    if isinstance(overlay, dict) and overlay.get("type") == "Settings":
                        config = overlay
                    elif isinstance(overlay, dict):
                        config = _deep_merge(copy.deepcopy(config), overlay)
        finally:
            db.close()

    think = config.setdefault("agent", {}).setdefault("think", {})
    think["functions"] = copy.deepcopy(VOICE_TOOL_DEFINITIONS)
    deepgram = get_deepgram_settings()
    listen = config.setdefault("agent", {}).setdefault("listen", {}).setdefault(
        "provider", {}
    )
    listen["model"] = deepgram.model
    # P6-V05: multilingual gated — runtime language is English-only until thresholds pass.
    listen["language"] = "en"
    # Strip tenant overlay attempts to change speak/listen language or greeting locale.
    speak = config.setdefault("agent", {}).setdefault("speak", {}).setdefault(
        "provider", {}
    )
    if "language" in speak:
        speak["language"] = "en"
    think["prompt"] = AGENT_SYSTEM_PROMPT.format(
        current_date_context=get_current_date_context(timezone_name=ctx.timezone)
    )
    return config
