"""Tests for Goal 12: build_system_prompt() wiring to the context-aware
dependency-pattern detector, with the old periodic nudge kept only as a
fallback when no specific pattern is detected.
"""

from app import persona


def test_detected_pattern_is_injected_and_reason_returned(db_session):
    prompt, _citations, nudge_reason, _snippets, _gather_result = persona.build_system_prompt(
        db_session,
        "Just you choose, whatever you think is best.",
        turn_count=1,
        prior_user_messages=["You decide, I don't mind either way."],
    )

    assert nudge_reason == "decide_for_me"
    assert "lay out 2 concrete options" in prompt


def test_pattern_takes_priority_over_periodic_nudge(db_session):
    # turn_count is a multiple of the periodic interval (6), which would normally
    # fire the generic nudge — but a specific pattern is present and must win instead.
    prompt, _citations, nudge_reason, _snippets, _gather_result = persona.build_system_prompt(
        db_session,
        "Just you choose, whatever you think is best.",
        turn_count=6,
        prior_user_messages=["You decide, I don't mind either way."],
    )

    assert nudge_reason == "decide_for_me"
    assert persona.INDEPENDENCE_NUDGE not in prompt


def test_periodic_nudge_still_fires_when_no_pattern_detected(db_session):
    prompt, _citations, nudge_reason, _snippets, _gather_result = persona.build_system_prompt(
        db_session, "What's a good book to read?", turn_count=6
    )

    assert nudge_reason == "periodic"
    assert persona.INDEPENDENCE_NUDGE in prompt


def test_no_nudge_when_no_pattern_and_not_on_periodic_turn(db_session):
    prompt, _citations, nudge_reason, _snippets, _gather_result = persona.build_system_prompt(
        db_session, "What's a good book to read?", turn_count=2
    )

    assert nudge_reason is None
    assert persona.INDEPENDENCE_NUDGE not in prompt
