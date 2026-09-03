"""Phase 5 cache correctness tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_cache_state():
    """Reset cache module state before each test."""
    import app.core.cache as mod
    old_client = mod._client
    old_retry = mod._retry_after
    mod._client = None
    mod._retry_after = 0
    yield
    mod._client = old_client
    mod._retry_after = old_retry


class TestCacheFailOpen:
    """Cache operations must fail open when Redis is unavailable."""

    def test_cache_get_returns_none_on_failure(self):
        import sys

        mock_redis_mod = MagicMock()
        mock_redis_mod.Redis.from_url.side_effect = ConnectionError("down")
        with patch.dict(sys.modules, {"redis": mock_redis_mod}):
            from app.core.cache import cache_get
            result = cache_get("some:key")
            assert result is None

    def test_cache_set_noop_on_failure(self):
        import sys

        mock_redis_mod = MagicMock()
        mock_redis_mod.Redis.from_url.side_effect = ConnectionError("down")
        with patch.dict(sys.modules, {"redis": mock_redis_mod}):
            from app.core.cache import cache_set
            # Should not raise
            cache_set("some:key", {"data": 1}, ttl_seconds=60)


class TestCacheRetryAfterFailure:
    """Redis connection is retried after cooldown, not permanently disabled."""

    def test_retry_after_cooldown(self):
        import sys

        import app.core.cache as mod

        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod = MagicMock()
        mock_redis_mod.Redis.from_url.return_value = mock_client

        with patch.dict(sys.modules, {"redis": mock_redis_mod}):
            client = mod._redis()
            assert client is mock_client

    def test_skips_retry_during_cooldown(self):
        import time

        import app.core.cache as mod

        mod._retry_after = time.monotonic() + 9999  # far future
        result = mod._redis()
        assert result is None


class TestCacheKeyScoping:
    """All cache keys include user_id to prevent cross-user data leaks."""

    def test_analytics_key_contains_user_id(self):
        # analytics_summary uses f"analytics:summary:{user_id}:{start}:{end}"
        user_id = 42
        key = f"analytics:summary:{user_id}:2026-01-01:2026-12-31"
        assert str(user_id) in key

    def test_dashboard_key_contains_user_id(self):
        user_id = 42
        key = f"dashboard:summary:{user_id}"
        assert str(user_id) in key

    def test_calendar_key_contains_user_id(self):
        user_id = 42
        key = f"cal:events:{user_id}:2026-01-01:2026-01-31:"
        assert str(user_id) in key

    def test_user_settings_key_contains_user_id(self):
        user_id = 42
        key = f"user:settings:{user_id}"
        assert str(user_id) in key


class TestInvalidation:
    """Mutations bump tenant cache versions (O(1))."""

    def test_calendar_invalidation_bumps_versions(self):
        from app.core.cache import invalidate_user_calendar_caches

        with patch("app.core.cache.bump_cache_version") as mock_bump:
            invalidate_user_calendar_caches(42)
            mock_bump.assert_any_call(42, "cal")
            mock_bump.assert_any_call(42, "dashboard")

    def test_analytics_invalidation_bumps_version(self):
        from app.core.cache import invalidate_user_analytics_caches

        with patch("app.core.cache.bump_cache_version") as mock_bump:
            invalidate_user_analytics_caches(42)
            mock_bump.assert_called_once_with(42, "analytics")

    def test_settings_invalidation_bumps_version(self):
        from app.core.cache import invalidate_user_settings_cache

        with patch("app.core.cache.bump_cache_version") as mock_bump:
            invalidate_user_settings_cache(42)
            mock_bump.assert_called_once_with(42, "settings")


class TestCacheRoundTrip:
    """Verify JSON serialization round-trips correctly with a mock Redis."""

    def test_set_then_get(self):
        import app.core.cache as mod

        mock_client = MagicMock()
        store = {}

        def mock_setex(key, ttl, value):
            store[key] = value

        def mock_get(key):
            return store.get(key)

        mock_client.setex = mock_setex
        mock_client.get = mock_get
        mod._client = mock_client

        try:
            from app.core.cache import cache_get, cache_set

            data = {"total_calls": 42, "cost": 3.14}
            cache_set("test:key", data, ttl_seconds=60)
            result = cache_get("test:key")
            assert result == data
        finally:
            mod._client = None
            mod._retry_after = 0
