"""ECHO Layer 0 — small generic in-process TTL cache.

`app/web_search.py` already has its own working per-module TTL cache for
SearXNG/RSS results (see its own `_cache_get`/`_cache_set`) — that one is
left alone, not migrated here, since it already works and is tested. This
module is for the things that didn't have a cache yet: provider health
checks, the installed-Ollama-model list, and feature-availability snapshots
(all read-heavy, cheap-to-recompute-but-not-instant, and safe to serve
slightly stale for a few seconds).

In-process dict only — no Redis, matching this milestone's explicit "don't
add Redis unless there's a clear need" rule; this is a single-process app.
"""

import threading
import time
from collections.abc import Callable
from typing import Any

from app.config import get_settings

_lock = threading.Lock()
_store: dict[str, tuple[float, Any]] = {}
_hits = 0
_misses = 0


def _now() -> float:
    return time.monotonic()


def get(key: str) -> Any | None:
    """Returns the cached value, or None on miss/expiry — never raises."""
    global _hits, _misses
    with _lock:
        entry = _store.get(key)
        if entry is None:
            _misses += 1
            return None
        expires_at, value = entry
        if _now() > expires_at:
            del _store[key]
            _misses += 1
            return None
        _hits += 1
        return value


def set(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    settings = get_settings()
    if not settings.cache_enabled:
        return
    ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_seconds
    with _lock:
        _store[key] = (_now() + ttl, value)


def invalidate(key: str) -> None:
    with _lock:
        _store.pop(key, None)


def invalidate_prefix(prefix: str) -> None:
    """Used when e.g. a project/memory change should drop every cached
    entry derived from it, without needing to track each individual key."""
    with _lock:
        for key in [k for k in _store if k.startswith(prefix)]:
            del _store[key]


def clear() -> None:
    global _hits, _misses
    with _lock:
        _store.clear()
        _hits = 0
        _misses = 0


def stats() -> dict:
    with _lock:
        return {"size": len(_store), "hits": _hits, "misses": _misses}


def cached(key: str, ttl_seconds: int | None, compute: Callable[[], Any]) -> Any:
    """get-or-compute-and-set in one call. `compute` failing propagates the
    exception as-is (a cache failure must never silently swallow a real
    error) — but a cache *lookup* failure never can, since get()/set() above
    never raise themselves."""
    cached_value = get(key)
    if cached_value is not None:
        return cached_value
    value = compute()
    set(key, value, ttl_seconds)
    return value
