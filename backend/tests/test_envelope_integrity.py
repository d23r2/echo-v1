"""Tests for Phase 1: envelope integrity tracking (envelope_status,
reasoning_available, memory_block_available, envelope_degradation_reason) on
ChatResult, computed by both the non-streaming parser (base.py) and the
streaming parser (envelope_stream.py). Never invents reasoning — a degraded
result's `reasoning` is always None, never a placeholder.
"""

from app.envelope_stream import EnvelopeStreamParser
from app.providers.base import split_reasoning_and_answer

# ---- non-streaming (split_reasoning_and_answer) ----


def test_full_envelope_is_complete():
    raw = "REASONING: because reasons\nANSWER: hi there\nMEMORY: NONE"
    result = split_reasoning_and_answer(raw)

    assert result.envelope_status == "complete"
    assert result.reasoning_available is True
    assert result.memory_block_available is True
    assert result.envelope_degradation_reason is None
    assert result.reasoning == "because reasons"


def test_reasoning_and_answer_no_memory_is_partial():
    raw = "REASONING: because reasons\nANSWER: hi there"
    result = split_reasoning_and_answer(raw)

    assert result.envelope_status == "partial"
    assert result.reasoning_available is True
    assert result.memory_block_available is False
    assert result.envelope_degradation_reason is not None


def test_bare_memory_marker_with_no_reasoning_prefix_is_malformed():
    raw = 'Just answered directly.\nMEMORY: {"content": "x", "epistemic_status": "Verified"}'
    result = split_reasoning_and_answer(raw)

    assert result.envelope_status == "malformed"
    assert result.reasoning_available is False
    assert result.reasoning is None  # never invented
    assert result.memory_block_available is True
    assert "reasoning is unavailable" in result.envelope_degradation_reason.lower()


def test_plain_text_no_envelope_at_all_is_missing():
    raw = "Just a plain direct answer, no envelope at all."
    result = split_reasoning_and_answer(raw)

    assert result.envelope_status == "missing"
    assert result.reasoning_available is False
    assert result.reasoning is None
    assert result.memory_block_available is False
    assert result.text == raw
    assert "did not return the expected" in result.envelope_degradation_reason.lower()


# ---- streaming (EnvelopeStreamParser) ----


def test_streaming_full_envelope_is_complete():
    parser = EnvelopeStreamParser()
    parser.feed("REASONING: ok\nANSWER: hi\nMEMORY: NONE")
    result = parser.result()

    assert result.envelope_status == "complete"
    assert result.reasoning_available is True
    assert result.memory_block_available is True


def test_streaming_no_envelope_at_all_is_missing_and_never_invents_reasoning():
    parser = EnvelopeStreamParser()
    plain = "Sure, the capital of France is Paris. " * 3  # forces the length-based fallback
    for i in range(0, len(plain), 5):
        parser.feed(plain[i : i + 5])
    result = parser.result()

    assert result.envelope_status == "missing"
    assert result.reasoning is None
    assert result.reasoning_available is False
    assert result.memory_block_available is False


def test_streaming_fallback_with_late_memory_marker_is_malformed():
    parser = EnvelopeStreamParser()
    direct_answer = "The sky looks blue because sunlight scatters in the atmosphere overhead. " * 2
    tail = 'MEMORY: {"content": "note", "epistemic_status": "Verified", "confidence": 1.0, "tags": []}'
    full = direct_answer + tail
    for i in range(0, len(full), 9):
        parser.feed(full[i : i + 9])
    result = parser.result()

    assert result.envelope_status == "malformed"
    assert result.reasoning is None
    assert result.memory_block_available is True


def test_streaming_reasoning_and_answer_no_memory_is_partial():
    parser = EnvelopeStreamParser()
    parser.feed("REASONING: thinking it through\nANSWER: done")
    result = parser.result()

    assert result.envelope_status == "partial"
    assert result.reasoning_available is True
    assert result.memory_block_available is False


# ---- reasoning is never fabricated ----


def test_degraded_result_never_has_placeholder_reasoning_text():
    for raw in [
        "plain text with no markers whatsoever, long enough to trip fallback " * 3,
        'direct answer\nMEMORY: {"content": "x", "epistemic_status": "Verified"}',
    ]:
        result = split_reasoning_and_answer(raw)
        assert result.reasoning is None
        assert result.reasoning_available is False
