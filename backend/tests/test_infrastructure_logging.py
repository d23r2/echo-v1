"""ECHO Layer 0 — structured logging + secret redaction."""

import logging

from app.core.logging import Timer, log_event, redact


def test_redact_hides_anthropic_style_api_key():
    text = "call failed with key sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
    redacted = redact(text)
    assert "sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890" not in redacted
    assert "REDACTED" in redacted


def test_redact_hides_bearer_token():
    text = "Authorization: Bearer abc123def456ghi789jklmno"
    redacted = redact(text)
    assert "abc123def456ghi789jklmno" not in redacted


def test_redact_hides_generic_secret_field():
    text = 'config dump: {"api_key": "supersecretvalue123", "other": "fine"}'
    redacted = redact(text)
    assert "supersecretvalue123" not in redacted
    assert "other" in redacted  # non-secret fields survive


def test_redact_leaves_normal_text_untouched():
    text = "user asked about Python list comprehensions"
    assert redact(text) == text


def test_redact_never_raises_on_empty_or_none():
    assert redact("") == ""


def test_log_event_emits_structured_record_with_safe_fields(caplog):
    logger = logging.getLogger("test.infra.logging")
    with caplog.at_level(logging.INFO, logger="test.infra.logging"):
        log_event(
            logger,
            "test_event",
            conversation_id="conv-123",
            provider_id="ollama",
            elapsed_ms=42.7,
        )
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.conversation_id == "conv-123"
    assert record.provider_id == "ollama"
    assert record.elapsed_ms == 42.7
    assert record.event == "test_event"


def test_log_event_does_not_accept_raw_message_content():
    """Structural guarantee, not just convention: log_event() has no
    message/prompt/content parameter at all, so a call site cannot
    accidentally pass raw user text into a log record through it."""
    import inspect

    sig = inspect.signature(log_event)
    param_names = set(sig.parameters.keys())
    assert "message" not in param_names
    assert "prompt" not in param_names
    assert "content" not in param_names


def test_timer_measures_positive_elapsed_ms():
    with Timer() as t:
        pass
    assert t.elapsed_ms >= 0
