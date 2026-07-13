"""Tests for Goal 11's incremental envelope parser (app/envelope_stream.py) —
the piece responsible for never leaking REASONING/MEMORY content to the client
while a reply is still streaming in, and for behaving safely when a model
doesn't follow the REASONING:/ANSWER:/MEMORY: envelope at all.
"""

from app.envelope_stream import EnvelopeStreamParser


def _feed_all(parser: EnvelopeStreamParser, chunks: list[str]) -> str:
    return "".join(parser.feed(c) for c in chunks)


def test_single_chunk_full_envelope_streams_only_the_answer():
    parser = EnvelopeStreamParser()
    full = 'REASONING: because reasons\nANSWER: Hello there\nMEMORY: NONE'

    streamed = parser.feed(full)

    assert streamed == "Hello there"
    result = parser.result()
    assert result.text == "Hello there"
    assert result.reasoning == "because reasons"
    assert result.memory_json == "NONE"


def test_character_by_character_streaming_reconstructs_the_answer_exactly():
    parser = EnvelopeStreamParser()
    full = 'REASONING: thinking it through\nANSWER: The answer is 42.\nMEMORY: NONE'

    streamed = _feed_all(parser, list(full))  # one character per feed() call

    assert streamed == "The answer is 42."
    assert parser.result().text == "The answer is 42."


def test_memory_json_is_never_present_in_any_streamed_chunk():
    parser = EnvelopeStreamParser()
    full = (
        'REASONING: ok\nANSWER: Sure, here you go.\nMEMORY: '
        '{"content": "secret internal note", "epistemic_status": "Hypothesis", '
        '"confidence": 0.4, "tags": ["x"]}'
    )

    chunks = [full[i : i + 5] for i in range(0, len(full), 5)]  # arbitrary chunk boundaries
    streamed_pieces = [parser.feed(c) for c in chunks]

    assert "secret internal note" not in "".join(streamed_pieces)
    assert "MEMORY" not in "".join(streamed_pieces)
    # But the final parsed result still has it, for internal use only.
    assert "secret internal note" in parser.result().memory_json


def test_answer_marker_split_across_chunk_boundary_is_still_detected():
    parser = EnvelopeStreamParser()
    part1 = "REASONING: hmm\nANS"
    part2 = "WER: split marker works\nMEMORY: NONE"

    streamed = parser.feed(part1) + parser.feed(part2)

    assert streamed == "split marker works"


def test_memory_marker_split_across_chunk_boundary_does_not_leak_fragment():
    parser = EnvelopeStreamParser()
    # "MEMORY:" split right down the middle across two feeds.
    part1 = "REASONING: hmm\nANSWER: done talking\nMEM"
    part2 = "ORY: NONE"

    streamed = parser.feed(part1) + parser.feed(part2)

    assert streamed == "done talking"
    assert "MEM" not in streamed


def test_long_reasoning_before_answer_does_not_trigger_false_fallback():
    parser = EnvelopeStreamParser()
    long_reasoning = "REASONING: " + ("this is a very long chain of thought. " * 5)
    # Feed the long reasoning in small pieces — well past the fallback threshold
    # in raw character count — before ANSWER: ever appears.
    for i in range(0, len(long_reasoning), 7):
        out = parser.feed(long_reasoning[i : i + 7])
        assert out == ""  # nothing should stream yet — still inside REASONING

    out = parser.feed("ANSWER: finally here\nMEMORY: NONE")
    assert out == "finally here"


def test_no_envelope_at_all_falls_back_to_streaming_raw_text():
    parser = EnvelopeStreamParser()
    plain = "Sure, the capital of France is Paris. " * 3  # well past the threshold, no markers

    streamed = _feed_all(parser, [plain[i : i + 6] for i in range(0, len(plain), 6)])

    assert streamed.strip() != ""
    result = parser.result()
    # What streamed live and what gets saved must agree exactly in fallback mode.
    assert result.text == plain.strip()
    assert result.reasoning is None


def test_fallback_mode_still_cuts_off_a_late_memory_marker():
    # Regression test for a real bug found via live Ollama testing: a model that
    # answers directly (triggering the length-based fallback long before any
    # markers appear) but then bolts on a garbled "REASONING: ... ANSWER: ...
    # MEMORY: {...}" envelope as an afterthought. The MEMORY JSON must never end
    # up in the saved/displayed answer just because fallback mode was already
    # active when it showed up.
    parser = EnvelopeStreamParser()
    direct_answer = "The sky looks blue because of how sunlight scatters in the atmosphere overhead. " * 2
    tail = (
        'REASONING: explaining scattering. ANSWER: The sky is blue.'
        ' MEMORY: {"content": "secret note", "epistemic_status": "Verified", "confidence": 1.0, "tags": []}'
    )
    full = direct_answer + tail

    streamed = _feed_all(parser, [full[i : i + 9] for i in range(0, len(full), 9)])

    assert "secret note" not in streamed
    assert "MEMORY" not in streamed

    result = parser.result()
    assert "secret note" not in result.text
    assert "MEMORY" not in result.text
    assert result.memory_json is not None
    assert "secret note" in result.memory_json


def test_reasoning_present_but_answer_never_arrives_streams_nothing_live():
    parser = EnvelopeStreamParser()
    # REASONING: appears, so the length-based fallback must not kick in, even
    # though the reply is cut off before ANSWER: ever shows up.
    cut_off = "REASONING: still figuring this out and it just stops"

    streamed = _feed_all(parser, [cut_off[i : i + 4] for i in range(0, len(cut_off), 4)])

    assert streamed == ""
    # The final parse still falls back gracefully (same as the non-streaming path).
    result = parser.result()
    assert result.text  # not empty — split_reasoning_and_answer's own fallback kicks in


def test_empty_chunks_are_ignored():
    parser = EnvelopeStreamParser()
    assert parser.feed("") == ""
    assert parser.feed("REASONING: a\nANSWER: b\nMEMORY: NONE") == "b"
