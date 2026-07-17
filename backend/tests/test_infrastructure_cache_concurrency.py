"""ECHO Layer 0 — generic cache abstraction + Ollama call concurrency cap."""

import threading
import time

import pytest

from app.core import cache
from app.providers.base import ChatMessage, ChatResult
from app.services.local_model_router import LocalModelRouter, _get_semaphore


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_cache_hit_returns_stored_value():
    cache.set("key1", "value1", ttl_seconds=60)
    assert cache.get("key1") == "value1"


def test_cache_miss_returns_none():
    assert cache.get("does-not-exist") is None


def test_cache_expiry_returns_none_after_ttl():
    cache.set("key2", "value2", ttl_seconds=0)
    time.sleep(0.05)
    assert cache.get("key2") is None


def test_cache_invalidate_removes_key():
    cache.set("key3", "value3", ttl_seconds=60)
    cache.invalidate("key3")
    assert cache.get("key3") is None


def test_cache_invalidate_prefix_removes_matching_keys():
    cache.set("project:1:summary", "a", ttl_seconds=60)
    cache.set("project:1:tasks", "b", ttl_seconds=60)
    cache.set("project:2:summary", "c", ttl_seconds=60)
    cache.invalidate_prefix("project:1:")
    assert cache.get("project:1:summary") is None
    assert cache.get("project:1:tasks") is None
    assert cache.get("project:2:summary") == "c"


def test_cache_disabled_setting_prevents_storage(monkeypatch):
    from app import config

    settings = config.Settings(_env_file=None, cache_enabled=False)
    monkeypatch.setattr(cache, "get_settings", lambda: settings)
    cache.set("key4", "value4")
    assert cache.get("key4") is None


def test_cached_helper_computes_once_on_miss():
    calls = {"count": 0}

    def compute():
        calls["count"] += 1
        return "computed"

    result1 = cache.cached("key5", 60, compute)
    result2 = cache.cached("key5", 60, compute)
    assert result1 == "computed"
    assert result2 == "computed"
    assert calls["count"] == 1


def test_cache_failure_in_compute_propagates():
    def failing():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        cache.cached("key6", 60, failing)


class _SlowFakeProvider:
    """A minimal ModelProvider-shaped fake that blocks for a bit so
    concurrency can actually be observed."""

    name = "ollama"
    label = "Ollama"

    def __init__(self, delay: float = 0.2):
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def available(self):
        return True, None

    def chat(self, system_prompt, messages, model=None):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(self.delay)
        with self._lock:
            self.active -= 1
        return ChatResult(text="ok", reasoning=None)


def test_concurrent_calls_respect_configured_cap(monkeypatch):
    from app import config

    settings = config.Settings(_env_file=None, max_concurrent_model_requests=2)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr("app.services.local_model_router.get_settings", lambda: settings)

    import app.services.local_model_router as lmr

    lmr._semaphore = None  # force re-sizing to the patched setting
    lmr._semaphore_size = None

    fake = _SlowFakeProvider(delay=0.15)
    router = LocalModelRouter(provider=fake)

    threads = [
        threading.Thread(target=router.call, args=("fast", "sys", [ChatMessage(role="user", content="hi")]))
        for _ in range(5)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert fake.max_active <= 2


def test_semaphore_getter_never_raises():
    sem = _get_semaphore()
    assert sem is not None
