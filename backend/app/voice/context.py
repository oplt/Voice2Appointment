"""Immutable tenant context for an active voice call."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class CallContext:
    call_sid: str
    user_id: int
    timezone: str
    calendar_id: str


current_call_context: ContextVar[CallContext | None] = ContextVar(
    "current_call_context", default=None
)


def bind_call_context(ctx: CallContext) -> Token:
    return current_call_context.set(ctx)


def unbind_call_context(token: Token) -> None:
    current_call_context.reset(token)


def require_call_context() -> CallContext:
    ctx = current_call_context.get()
    if ctx is None:
        raise ValueError("CallContext is required for this operation")
    return ctx
