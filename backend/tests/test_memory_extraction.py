"""Tests for app.memory_extraction: parsing the model's MEMORY: envelope section
(see persona.py's BEHAVIOR_DIRECTIVES for the exact format Echo is asked to emit),
and detecting/handling explicit "remember that..." user requests.

The parser must fail closed: on anything malformed or unexpected it returns None
(or a safe default for an individual field) rather than raising, since it runs
on raw, sometimes-messy model output every chat turn.
"""

import pytest

from app import atlas, memory_extraction as mx
from app.providers.base import ChatResult
from app.routers.chat import _extract_memory


# ---- 1. MEMORY: NONE saves nothing ----


@pytest.mark.parametrize("raw", ["NONE", "None", "none.", '"NONE"', "  NONE  ", None, ""])
def test_memory_none_variants_return_nothing(raw):
    assert mx.parse_memory_json(raw) is None


# ---- 2. Valid MEMORY JSON returns a valid memory candidate ----


def test_valid_memory_json_returns_a_candidate():
    raw = (
        '{"content": "User prefers dark mode.", "epistemic_status": "Verified", '
        '"confidence": 0.9, "tags": ["ui", "preference"]}'
    )
    result = mx.parse_memory_json(raw)
    assert result == {
        "content": "User prefers dark mode.",
        "epistemic_status": "Verified",
        "confidence": 0.9,
        "tags": ["ui", "preference"],
    }


# ---- 3. JSON inside a markdown code fence is parsed ----


def test_json_inside_markdown_code_fence_is_parsed():
    raw = (
        "```json\n"
        '{"content": "User is a backend developer.", "epistemic_status": "Inferred", '
        '"confidence": 0.7, "tags": []}\n'
        "```"
    )
    result = mx.parse_memory_json(raw)
    assert result is not None
    assert result["content"] == "User is a backend developer."


# ---- 4. JSON surrounded by prose is parsed if possible ----


def test_json_surrounded_by_prose_is_parsed():
    raw = (
        "Sure, here is the memory: "
        '{"content": "User likes tea.", "epistemic_status": "Hypothesis", '
        '"confidence": 0.5, "tags": ["preference"]} '
        "Let me know if that looks right."
    )
    result = mx.parse_memory_json(raw)
    assert result is not None
    assert result["content"] == "User likes tea."


# ---- 5. Malformed JSON fails closed ----


@pytest.mark.parametrize(
    "raw",
    [
        '{"content": "unterminated string}',
        "{not even json}",
        "{'content': 'single quotes are not valid json'}",
        "{",
        "}",
    ],
)
def test_malformed_json_fails_closed(raw):
    assert mx.parse_memory_json(raw) is None


# ---- 6. Missing required fields fail closed / get safe defaults ----


@pytest.mark.parametrize(
    "raw",
    [
        '{"epistemic_status": "Verified", "confidence": 0.9}',  # no content at all
        '{"content": "", "epistemic_status": "Verified"}',  # empty content
        '{"content": "   ", "epistemic_status": "Verified"}',  # whitespace-only content
    ],
)
def test_missing_content_fails_closed(raw):
    assert mx.parse_memory_json(raw) is None


def test_missing_optional_fields_get_safe_defaults():
    result = mx.parse_memory_json('{"content": "User is left-handed."}')
    assert result == {
        "content": "User is left-handed.",
        "epistemic_status": "Inferred",  # safe default, not Verified
        "confidence": 0.6,  # safe default
        "tags": [],
    }


# ---- 7. Invalid epistemic_status is normalized safely (not rejected outright) ----


def test_invalid_epistemic_status_is_normalized_to_inferred():
    raw = '{"content": "User owns a cat.", "epistemic_status": "TotallySure", "confidence": 0.9}'
    result = mx.parse_memory_json(raw)
    assert result is not None
    assert result["epistemic_status"] == "Inferred"


def test_confidence_out_of_range_is_clamped():
    too_high = mx.parse_memory_json('{"content": "x", "confidence": 5}')
    too_low = mx.parse_memory_json('{"content": "x", "confidence": -3}')
    assert too_high["confidence"] == 1.0
    assert too_low["confidence"] == 0.0


def test_non_numeric_confidence_falls_back_to_default():
    result = mx.parse_memory_json('{"content": "x", "confidence": "very sure"}')
    assert result["confidence"] == 0.6


# ---- 8. Explicit "remember that..." commands are saved as Verified, high confidence ----


def test_explicit_remember_request_is_saved_as_verified_high_confidence(db_session):
    result = ChatResult(text="Got it.", reasoning="User asked me to remember something.", memory_json="NONE")
    update = _extract_memory(db_session, "Please remember that my favorite color is teal.", result)

    assert update is not None
    assert update.saved is True
    assert update.explicit is True
    assert "teal" in update.content

    saved = atlas.list_entries(db_session)
    assert len(saved) == 1
    assert saved[0].epistemic_status == "Verified"
    assert saved[0].confidence == 0.95
    assert "user-stated" in saved[0].tags


# ---- 9. Non-memory casual messages do not create low-quality memories ----


def test_casual_message_with_memory_none_saves_nothing(db_session):
    result = ChatResult(text="Nice to hear!", reasoning="Just chatting.", memory_json="NONE")
    update = _extract_memory(db_session, "haha that's a funny story, thanks for listening", result)

    assert update is None
    assert atlas.list_entries(db_session) == []


def test_casual_message_is_not_mistaken_for_an_explicit_remember_request():
    assert mx.is_explicit_remember_request("haha that's a funny story") is False
    assert mx.is_explicit_remember_request("what's the capital of France?") is False


# ---- 10. Parser never raises on messy provider output ----


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "NONE",
        "not json at all, just rambling prose with no braces",
        "{",
        "}",
        "{{{{",
        '{"content": {"nested": "object instead of a string"}}',
        '["a", "json", "array", "not", "an", "object"]',
        "null",
        "42",
        '{"content": "ok"} trailing garbage {{{',
        "\x00\x01 binary-ish garbage �",
    ],
)
def test_parser_never_raises_on_messy_provider_output(raw):
    result = mx.parse_memory_json(raw)  # must not raise
    assert result is None or isinstance(result, dict)
