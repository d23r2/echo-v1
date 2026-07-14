"""Regression test for a real gap: build_system_prompt() never told the model
the current date, so any backend without live search (Ollama has none at all)
had no way to answer "what's today's date" without guessing from stale
training data. See app/persona.py's _current_date_note().
"""

from datetime import datetime, timezone

from app import persona


def test_system_prompt_includes_current_date_for_every_backend(db_session):
    fixed_now = datetime(2026, 7, 13, 4, 30, tzinfo=timezone.utc)

    prompt, _citations, _nudge_reason, _snippets, _gather_result = persona.build_system_prompt(
        db_session, "what's today's date?", turn_count=0, now=fixed_now
    )

    assert "2026-07-13" in prompt
    assert "UTC" in prompt


def test_date_note_defaults_to_real_now_when_not_passed(db_session):
    prompt, _citations, _nudge_reason, _snippets, _gather_result = persona.build_system_prompt(db_session, "hi", turn_count=0)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert today in prompt
