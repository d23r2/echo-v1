"""ECHO Layer 0 — lightweight local metrics.

In-process only, no external monitoring service, no persistence — resets on
restart, matching this milestone's "local-first, no invasive external
monitoring" goal. A single lock-guarded module-level registry, since this is
a single-process app (no multi-worker deployment target in scope).

Deliberately narrow scope for v1: HTTP request counts/durations are wired in
automatically via RequestIDMiddleware (core/errors.py) since every request
already passes through there. Model-call counts are wired in at
ModelRouter.chat()'s single chokepoint (app/router.py) since every chat/
Local-Intelligence call already funnels through that one function. Deeper
per-subsystem instrumentation (every individual search/memory/action call
site) is intentionally not added in this pass — see
ECHO_LAYER_0_INFRASTRUCTURE_REPORT.md's known-limitations section.

Never records user content, prompts, or secrets — only counters, durations,
and short category/provider/role labels.
"""

import threading
import time
from collections import defaultdict

_lock = threading.Lock()
_counters: dict[str, int] = defaultdict(int)
_durations: dict[str, list[float]] = defaultdict(list)
_measurements: dict[str, list[float]] = defaultdict(list)
_MAX_SAMPLES_PER_KEY = 500  # bounded — never grows unboundedly for a long-running process
_start_time = time.monotonic()


def increment(name: str, **tags: str) -> None:
    key = _make_key(name, tags)
    with _lock:
        _counters[key] += 1


def record_duration(name: str, elapsed_ms: float, **tags: str) -> None:
    key = _make_key(name, tags)
    with _lock:
        samples = _durations[key]
        samples.append(elapsed_ms)
        if len(samples) > _MAX_SAMPLES_PER_KEY:
            del samples[: len(samples) - _MAX_SAMPLES_PER_KEY]


def record_value(name: str, value: float, **tags: str) -> None:
    """Record a bounded non-time measurement such as a prompt size.

    Like durations, values are summarized at read time and accept only short
    labels—never prompts, messages, or other raw content.
    """
    key = _make_key(name, tags)
    with _lock:
        samples = _measurements[key]
        samples.append(value)
        if len(samples) > _MAX_SAMPLES_PER_KEY:
            del samples[: len(samples) - _MAX_SAMPLES_PER_KEY]


def _make_key(name: str, tags: dict) -> str:
    if not tags:
        return name
    tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
    return f"{name}[{tag_str}]"


def uptime_seconds() -> float:
    return time.monotonic() - _start_time


def snapshot() -> dict:
    """A point-in-time read of everything recorded — never raises. Duration
    lists are summarized (count/avg/max), never returned raw, to keep the
    endpoint response small regardless of how long the process has run."""
    with _lock:
        counters = dict(_counters)
        duration_summary = {}
        for key, samples in _durations.items():
            if not samples:
                continue
            duration_summary[key] = {
                "count": len(samples),
                "avg_ms": round(sum(samples) / len(samples), 1),
                "max_ms": round(max(samples), 1),
            }
        measurement_summary = {}
        for key, samples in _measurements.items():
            if not samples:
                continue
            measurement_summary[key] = {
                "count": len(samples),
                "avg": round(sum(samples) / len(samples), 1),
                "max": round(max(samples), 1),
            }
    return {
        "uptime_seconds": round(uptime_seconds(), 1),
        "counters": counters,
        "durations": duration_summary,
        "measurements": measurement_summary,
    }


def reset() -> None:
    """Test-only — production code never calls this (metrics should persist
    for the life of the process)."""
    with _lock:
        _counters.clear()
        _durations.clear()
        _measurements.clear()
