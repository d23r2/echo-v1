"""Tests for Goal 12's context-aware dependency-pattern detector
(app/dependency_patterns.py) — pure functions, no DB or model calls.
"""

from app import dependency_patterns as dp


def test_no_pattern_for_empty_history():
    assert dp.detect([]) is None


def test_no_pattern_for_ordinary_single_message():
    assert dp.detect(["What's the capital of France?"]) is None


def test_decide_for_me_requires_repetition():
    # A single occurrence shouldn't fire — "repeatedly" means at least twice.
    assert dp.detect(["What should I name this variable?"]) is None

    result = dp.detect(["You decide, I don't mind.", "Honestly you choose, whatever you think is best."])
    assert result is not None
    pattern_id, nudge = result
    assert pattern_id == "decide_for_me"
    assert nudge == dp.NUDGES["decide_for_me"]


def test_reassurance_seeking_requires_repetition():
    assert dp.detect(["Is this right?"]) is None

    result = dp.detect(["Is this correct?", "Am I doing this right though?"])
    assert result is not None
    assert result[0] == "reassurance_seeking"


def test_repeated_same_task_detected_via_word_overlap():
    result = dp.detect([
        "How do I set up a virtual environment for this Python project?",
        "Can you set up a virtual environment for this Python project for me?",
    ])
    assert result is not None
    assert result[0] == "repeated_same_task"


def test_repeated_same_task_not_flagged_for_unrelated_messages():
    result = dp.detect([
        "What's the weather like today?",
        "Can you recommend a good sci-fi book?",
    ])
    assert result is None


def test_do_it_for_me_fires_on_single_occurrence():
    result = dp.detect(["Whatever, just do it for me."])
    assert result is not None
    assert result[0] == "do_it_for_me"


def test_avoidance_fires_on_single_occurrence():
    result = dp.detect(["I don't want to try, I'll do it later."])
    assert result is not None
    assert result[0] == "avoidance"


def test_decide_for_me_takes_priority_over_later_patterns():
    # Both decide_for_me and avoidance-style phrasing appear; decide_for_me is
    # checked first and should win.
    messages = [
        "You decide, I really don't want to try this myself.",
        "Just you choose, whatever you think is best — I don't want to try.",
    ]
    result = dp.detect(messages)
    assert result is not None
    assert result[0] == "decide_for_me"


def test_only_recent_window_is_considered():
    # One decide-for-me hit falls outside the detection window (pushed out by
    # filler messages), leaving only one hit inside the window — not enough to
    # cross the repeat threshold of 2.
    messages = ["you decide"] + ["unrelated filler message"] * 7 + ["you decide again, please"]
    result = dp.detect(messages)
    assert result is None
