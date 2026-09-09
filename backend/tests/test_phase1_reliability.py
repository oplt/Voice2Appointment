import asyncio
import json
from types import SimpleNamespace

import pytest
import requests

from app.calendars import tools
from app.users.product_prefs import (
    ProductPrefsUpdate,
    load_product_prefs,
    update_product_prefs,
)
from app.voice import function_calls as voice_function_calls
from app.voice import session as voice_session
from app.voice.context import CallContext
from app.voice.latency import LatencyTracker
from app.workers import tasks


class _Socket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, payload: str) -> None:
        self.messages.append(json.loads(payload))


_CTX = CallContext(call_sid="CA" + "a" * 32, user_id=1, timezone="UTC", calendar_id="primary")


def _function(function_id: str, name: str = "tool", arguments: str = "{}") -> dict:
    return {"id": function_id, "name": name, "arguments": arguments}


def test_voice_tool_error_is_cached_and_does_not_leave_inflight(monkeypatch) -> None:
    socket = _Socket()
    results: dict[str, dict] = {}
    inflight: set[str] = set()
    calls = 0

    def fail(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider unavailable")

    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(voice_session.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(voice_session, "_run_tool_in_thread", fail)
    request = {"functions": [_function("one")]}
    asyncio.run(
        voice_session.handle_function_call_request(
            request,
            socket,
            ctx=_CTX,
            latency=LatencyTracker(),
            tool_results=results,
            inflight_tool_ids=inflight,
        )
    )

    assert inflight == set()
    assert calls == 1
    assert "RuntimeError" in socket.messages[0]["content"]

    asyncio.run(
        voice_session.handle_function_call_request(
            request,
            socket,
            ctx=_CTX,
            latency=LatencyTracker(),
            tool_results=results,
            inflight_tool_ids=inflight,
        )
    )
    assert calls == 1
    assert socket.messages[1] == socket.messages[0]


def test_voice_tool_malformed_and_failed_calls_do_not_block_later_calls(monkeypatch) -> None:
    socket = _Socket()
    inflight: set[str] = set()

    def run(name, _arguments, _ctx):
        if name == "broken":
            raise ValueError("broken")
        return {"success": True, "tool": name}

    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(voice_session.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(voice_session, "_run_tool_in_thread", run)
    asyncio.run(
        voice_session.handle_function_call_request(
            {
                "functions": [
                    _function("malformed", arguments="not json"),
                    _function("broken", name="broken"),
                    _function("good", name="good"),
                ]
            },
            socket,
            ctx=_CTX,
            latency=LatencyTracker(),
            tool_results={},
            inflight_tool_ids=inflight,
        )
    )

    assert inflight == set()
    assert len(socket.messages) == 3
    assert "JSONDecodeError" in socket.messages[0]["content"]
    assert "ValueError" in socket.messages[1]["content"]
    assert json.loads(socket.messages[2]["content"]) == {"success": True, "tool": "good"}


def test_voice_duplicate_completed_mutation_is_not_run_twice(monkeypatch) -> None:
    socket = _Socket()
    results: dict[str, dict] = {}
    calls = 0

    def mutate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {"success": True}

    async def run_inline(function, *args):
        return function(*args)

    monkeypatch.setattr(voice_session.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(voice_session, "_run_tool_in_thread", mutate)
    request = {"functions": [_function("mutation", name="create_calendar_event")]}

    for _ in range(2):
        asyncio.run(
            voice_session.handle_function_call_request(
                request,
                socket,
                ctx=_CTX,
                latency=LatencyTracker(),
                tool_results=results,
                inflight_tool_ids=set(),
            )
        )

    assert calls == 1
    assert socket.messages[0] == socket.messages[1]


def test_disconnected_calendar_read_tools_return_local_only_results(monkeypatch) -> None:
    monkeypatch.setattr(tools, "_resolve_service", lambda: (None, None, "UTC", "primary"))

    availability = tools.check_calendar_availability(
        "2030-01-01T10:00:00+00:00", "2030-01-01T11:00:00+00:00"
    )
    appointments = tools.find_appointments(
        "2030-01-01T10:00:00+00:00", "2030-01-01T11:00:00+00:00"
    )

    assert availability["code"] == "calendar_not_connected"
    assert availability["mode"] == "local_only_mode"
    assert availability["available"] is False
    assert appointments["code"] == "calendar_not_connected"
    assert appointments["appointments"] == []


def test_product_pref_patch_preserves_unknown_fields_and_notification_consent() -> None:
    user = SimpleNamespace(
        config_json=json.dumps(
            {
                "booking_policy": {"future_policy": True},
                "product": {
                    "future_section": {"kept": True},
                    "notifications": {"confirmations_enabled": False, "future": "kept"},
                    "transcripts": {"future": "kept"},
                },
            }
        )
    )

    updated = update_product_prefs(
        user,
        ProductPrefsUpdate.model_validate(
            {"notifications": {"confirmations_enabled": True}}
        ),
    )
    stored = json.loads(user.config_json)

    assert updated.notifications.confirmations_enabled is True
    assert updated.notifications.consent_at is not None
    assert stored["booking_policy"] == {"future_policy": True}
    assert stored["product"]["future_section"] == {"kept": True}
    assert stored["product"]["notifications"]["future"] == "kept"
    assert stored["product"]["transcripts"]["future"] == "kept"


def test_transcript_storage_requires_explicit_consent_and_round_trips() -> None:
    user = SimpleNamespace(config_json=None)
    request = ProductPrefsUpdate.model_validate({"transcripts": {"storage_enabled": True}})

    with pytest.raises(ValueError, match="explicit transcript storage consent"):
        update_product_prefs(user, request)

    saved = update_product_prefs(
        user,
        ProductPrefsUpdate.model_validate(
            {
                "transcripts": {"storage_enabled": True, "redact_phone_numbers": True},
                "transcript_storage_consent": True,
            }
        ),
    )
    round_trip = update_product_prefs(
        user, ProductPrefsUpdate.model_validate(saved.model_dump(mode="json"))
    )

    assert saved.transcripts.storage_enabled is True
    assert saved.transcripts.consent_at is not None
    assert round_trip == load_product_prefs(user.config_json)


class _RetryCalled(Exception):
    pass


class _Db:
    def __init__(self, user) -> None:
        self.user = user
        self.commits = 0

    def get(self, _model, _user_id):
        return self.user

    def add(self, _value) -> None:
        pass

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        pass


def test_twilio_sync_retries_transient_failures(monkeypatch) -> None:
    user = SimpleNamespace(
        id=7,
        twilio_account_sid="ACtest",
        twilio_auth_token="token",
        config_json="{}",
    )
    db = _Db(user)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    from app.analytics import service as analytics_service

    monkeypatch.setattr(
        analytics_service,
        "fetch_and_store_twilio",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(requests.Timeout("timeout")),
    )
    retry_args: dict | None = None

    def retry(**kwargs):
        nonlocal retry_args
        retry_args = kwargs
        raise _RetryCalled

    monkeypatch.setattr(tasks.sync_twilio_for_user, "retry", retry)

    with pytest.raises(_RetryCalled):
        tasks.sync_twilio_for_user.run(7)

    assert retry_args is not None
    assert retry_args["max_retries"] == 5
    assert retry_args["countdown"] >= 1


def test_twilio_sync_marks_permanent_provider_failure(monkeypatch) -> None:
    user = SimpleNamespace(
        id=8,
        twilio_account_sid="ACtest",
        twilio_auth_token="token",
        config_json="{}",
    )
    db = _Db(user)
    monkeypatch.setattr(tasks, "SessionLocal", lambda: db)
    from app.analytics import service as analytics_service

    class Unauthorized(Exception):
        status = 401

    monkeypatch.setattr(
        analytics_service,
        "fetch_and_store_twilio",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(Unauthorized()),
    )

    result = tasks.sync_twilio_for_user.run(8)

    assert result == {"ok": False, "user_id": 8, "error_code": "twilio_auth"}
    assert json.loads(user.config_json)["integration_health"]["twilio_sync"]["status"] == "permanent_failure"



def test_voice_read_calls_are_batched_with_mutation_barrier(monkeypatch) -> None:
    socket = _Socket()
    order: list[str] = []

    class _Meta:
        def __init__(self, kind: str) -> None:
            self.kind = kind

    async def fake_run(_name: str, fn):
        return fn()

    def fake_tool(name, _arguments, _ctx):
        order.append(name)
        return {"tool": name}

    class _Runtime:
        async def run(self, name, fn):
            await asyncio.sleep(0 if name != 'mutate' else 0.01)
            return fn()

    from app.voice.tool_runtime import ToolKind

    monkeypatch.setattr(voice_session, "_run_tool_in_thread", fake_tool)
    monkeypatch.setattr(voice_function_calls, "get_voice_tool_runtime", lambda: _Runtime())
    monkeypatch.setattr(
        voice_function_calls,
        "get_tool_metadata",
        lambda name: _Meta(ToolKind.MUTATION if name == "mutate" else ToolKind.READ),
    )

    req = {
        "functions": [
            _function("1", "read_a", "{}"),
            _function("2", "read_b", "{}"),
            _function("3", "mutate", "{}"),
            _function("4", "read_c", "{}"),
        ]
    }
    asyncio.run(
        voice_session.handle_function_call_request(
            req,
            socket,
            ctx=_CTX,
            latency=LatencyTracker(),
            tool_results={},
            inflight_tool_ids=set(),
        )
    )

    assert [json.loads(m["content"])["tool"] for m in socket.messages] == [
        "read_a",
        "read_b",
        "mutate",
        "read_c",
    ]
    assert order == ["read_a", "read_b", "mutate", "read_c"]
