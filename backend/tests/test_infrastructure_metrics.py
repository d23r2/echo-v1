"""ECHO Layer 0 — lightweight local metrics. Resets state before/after each
test so counts from other test files never leak in."""

import pytest

from app.core import metrics


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.reset()
    yield
    metrics.reset()


def test_increment_counts_correctly():
    metrics.increment("test_counter")
    metrics.increment("test_counter")
    metrics.increment("test_counter")
    snap = metrics.snapshot()
    assert snap["counters"]["test_counter"] == 3


def test_increment_with_tags_creates_separate_keys():
    metrics.increment("model_calls_total", provider="ollama", outcome="success")
    metrics.increment("model_calls_total", provider="gemini", outcome="failure")
    snap = metrics.snapshot()
    keys = snap["counters"].keys()
    assert any("ollama" in k and "success" in k for k in keys)
    assert any("gemini" in k and "failure" in k for k in keys)


def test_record_duration_summarizes_correctly():
    metrics.record_duration("test_latency", 10.0)
    metrics.record_duration("test_latency", 20.0)
    metrics.record_duration("test_latency", 30.0)
    snap = metrics.snapshot()
    summary = snap["durations"]["test_latency"]
    assert summary["count"] == 3
    assert summary["avg_ms"] == 20.0
    assert summary["max_ms"] == 30.0


def test_snapshot_includes_uptime():
    snap = metrics.snapshot()
    assert "uptime_seconds" in snap
    assert snap["uptime_seconds"] >= 0


def test_snapshot_never_contains_user_content_by_construction():
    """Structural guarantee: increment()/record_duration() only accept a
    name and short string tags — there is no parameter that could carry
    raw user text or a secret into the metrics registry."""
    import inspect

    inc_params = set(inspect.signature(metrics.increment).parameters.keys())
    dur_params = set(inspect.signature(metrics.record_duration).parameters.keys())
    for forbidden in ("message", "prompt", "content", "user_message"):
        assert forbidden not in inc_params
        assert forbidden not in dur_params


def test_bounded_sample_list_does_not_grow_unbounded():
    for i in range(600):
        metrics.record_duration("bounded_test", float(i))
    snap = metrics.snapshot()
    assert snap["durations"]["bounded_test"]["count"] <= 500


def test_reset_clears_all_state():
    metrics.increment("will_be_cleared")
    metrics.reset()
    snap = metrics.snapshot()
    assert "will_be_cleared" not in snap["counters"]
