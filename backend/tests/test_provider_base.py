from app.providers.base import split_reasoning_and_answer


def test_fallback_mode_still_cuts_off_a_late_memory_marker():
    raw = (
        "The capital of France is Paris.\n"
        'MEMORY: {"content": "secret user detail", "epistemic_status": "Verified"}'
    )
    result = split_reasoning_and_answer(raw)
    assert "secret user detail" not in result.text
    assert "MEMORY:" not in result.text
    assert result.text == "The capital of France is Paris."
    assert result.memory_json == (
        '{"content": "secret user detail", "epistemic_status": "Verified"}'
    )


def test_fallback_mode_with_no_memory_marker_returns_raw_text():
    raw = "Just a plain direct answer, no envelope at all."
    result = split_reasoning_and_answer(raw)
    assert result.text == raw
    assert result.reasoning is None
    assert result.memory_json is None


def test_full_envelope_still_parses():
    raw = "REASONING: because logic\nANSWER: 42\nMEMORY: NONE"
    result = split_reasoning_and_answer(raw)
    assert result.text == "42"
    assert result.reasoning == "because logic"
    assert result.memory_json == "NONE"


def test_two_part_trace_still_parses():
    raw = "REASONING: thinking it through\nANSWER: done"
    result = split_reasoning_and_answer(raw)
    assert result.text == "done"
    assert result.reasoning == "thinking it through"
    assert result.memory_json is None
