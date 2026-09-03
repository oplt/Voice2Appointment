"""Safe post-login redirect paths (no open redirects)."""

from __future__ import annotations

from urllib.parse import urlparse


def safe_next_path(value: str | None, *, fallback: str = "/dashboard") -> str:
    """Allow only same-site relative paths. Reject //evil.com and absolute URLs."""
    if not value or not isinstance(value, str):
        return fallback
    candidate = value.strip()
    if (
        not candidate.startswith("/")
        or candidate.startswith("//")
        or "\\" in candidate
        or "://" in candidate
    ):
        return fallback
    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc:
        return fallback
    path = parsed.path or "/"
    if not path.startswith("/") or "\\" in path:
        return fallback
    suffix = ""
    if parsed.query:
        suffix += f"?{parsed.query}"
    if parsed.fragment:
        suffix += f"#{parsed.fragment}"
    return f"{path}{suffix}"
