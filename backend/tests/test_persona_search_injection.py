"""build_system_prompt()'s wiring of app/web_search.py results into the
prompt (see app/persona.py's _source_blocks/_search_unavailable_note/
SOURCE_USAGE_INSTRUCTION). web_search.gather_sources() itself is
monkeypatched here — its own providers are covered by test_web_search.py,
so this only checks that persona.py injects/omits the right prompt text
based on what gather_sources() returns, and that the returned GatherResult
flows back out for chat.py to persist.
"""

from app import persona
from app.web_search import GatherResult, SourceResult


def test_source_blocks_injected_when_sources_found(db_session, monkeypatch):
    gather_result = GatherResult(
        sources=[
            SourceResult(
                source_type="wiki",
                provider="wikimedia",
                title="Marie Curie",
                url="https://en.wikipedia.org/wiki/Marie_Curie",
                snippet="Polish-born physicist and chemist.",
                retrieved_at="2026-07-14T00:00:00Z",
                reliability_note="Wiki source; good for background, not live updates.",
            )
        ],
        wiki_search_used=True,
        search_query="Who is Marie Curie?",
        task_type="encyclopedia_lookup",
    )
    monkeypatch.setattr(persona.web_search, "gather_sources", lambda intent, query: gather_result)

    prompt, _citations, _nudge, _snippets, returned = persona.build_system_prompt(
        db_session, "Who is Marie Curie?", turn_count=0
    )

    assert "WIKI_SEARCH_RESULTS:" in prompt
    assert "Marie Curie" in prompt
    assert persona.SOURCE_USAGE_INSTRUCTION in prompt
    assert returned is gather_result


def test_unavailable_note_injected_when_search_needed_but_nothing_found(db_session, monkeypatch):
    gather_result = GatherResult(
        sources=[],
        search_query="what's the latest news",
        search_failure_reason="No current-info source is configured.",
        task_type="news_lookup",
    )
    monkeypatch.setattr(persona.web_search, "gather_sources", lambda intent, query: gather_result)

    prompt, _citations, _nudge, _snippets, returned = persona.build_system_prompt(
        db_session, "What's the latest news?", turn_count=0
    )

    assert "WIKI_SEARCH_RESULTS:" not in prompt
    assert "WEB_SEARCH_RESULTS:" not in prompt
    assert "could not verify" in prompt.lower() or "say plainly" in prompt.lower()
    assert "No current-info source is configured." in prompt
    assert returned.search_failure_reason == "No current-info source is configured."


def test_no_search_blocks_for_general_chat_but_task_type_still_recorded(db_session, monkeypatch):
    gather_result = GatherResult(sources=[], search_query=None, task_type="general_chat")
    monkeypatch.setattr(persona.web_search, "gather_sources", lambda intent, query: gather_result)

    prompt, _citations, _nudge, _snippets, returned = persona.build_system_prompt(
        db_session, "What's a good book to read?", turn_count=0
    )

    assert "WIKI_SEARCH_RESULTS:" not in prompt
    assert "WEB_SEARCH_RESULTS:" not in prompt
    assert "could not verify" not in prompt.lower()
    assert returned.task_type == "general_chat"


def test_source_usage_instruction_forbids_mentioning_block_names():
    """Regression test: a live Ollama reply once echoed 'WIKI_SEARCH_RESULTS
    block' straight into its ANSWER text because the instruction described
    the block names without telling the model not to repeat them. This just
    asserts the guidance text is actually present, not model behavior
    (that's not something a unit test can verify)."""
    assert "never write them" in persona.SOURCE_USAGE_INSTRUCTION.lower()
