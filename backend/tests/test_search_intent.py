"""app/search_intent.py — deterministic classification of whether a message
needs external info, and what kind. No network, no model calls: this module
is pure regex, so these tests just assert on detect_search_intent()'s output
for representative phrasings, including the two real bugs found and fixed
during live verification (see git history around 2026-07-14): a Wikimedia
User-Agent 403 (app/web_search.py, not this module) and the "what is the
latest ..." classifier over-match fixed below.
"""

from app.search_intent import detect_search_intent


def test_personal_memory_query_routes_to_memory_lookup():
    result = detect_search_intent("Do you remember what I told you about my job?")
    assert result.task_type == "memory_lookup"
    assert result.needs_current_info is False


def test_code_help_query_does_not_trigger_search():
    result = detect_search_intent("Can you explain this error in my code?")
    assert result.task_type == "code_help"
    assert result.needs_current_info is False


def test_explicit_sport_name_with_score_triggers_sports_update():
    result = detect_search_intent("What's the latest football score today?")
    assert result.task_type == "sports_update"
    assert result.needs_current_info is True


def test_team_vs_team_with_score_triggers_sports_update():
    result = detect_search_intent("Liverpool vs Manchester United live score")
    assert result.task_type == "sports_update"
    assert result.needs_current_info is True


def test_fifa_match_details_query_triggers_sports_update():
    """Regression test: a real user query — 'check last match details of
    argentina in fifa 2026' — fell through to general_chat with no search at
    all, because neither 'fifa' nor 'match details' were in the sport-name/
    action vocabularies, and 'last' (as opposed to 'latest') wasn't a
    current-info trigger. ECHO answered from training data instead of
    honestly saying it needed to search, which is exactly the failure mode
    this classifier exists to prevent."""
    result = detect_search_intent("check last match details of argentina in fifa 2026")
    assert result.task_type == "sports_update"
    assert result.needs_current_info is True


def test_last_game_score_triggers_current_info_without_sport_name():
    result = detect_search_intent("What was the last game score?")
    assert result.needs_current_info is True


def test_bare_match_word_does_not_trigger_current_info():
    """Regression guard: 'match' is common outside sports (regex matching,
    pattern matching, dating) — it must only count as a sports signal when
    paired with an explicit sport name/team-vs-team, never as a standalone
    current-info trigger on its own."""
    result = detect_search_intent("this doesn't match what I expected")
    assert result.needs_current_info is False
    assert result.task_type == "general_chat"


def test_last_year_does_not_trigger_current_info():
    result = detect_search_intent("last year I visited Argentina")
    assert result.needs_current_info is False


def test_live_price_query_triggers_web_search():
    result = detect_search_intent("What's the current price of Bitcoin?")
    assert result.task_type == "web_search"
    assert result.needs_current_info is True


def test_news_keyword_triggers_news_lookup():
    result = detect_search_intent("Any breaking news about the election?")
    assert result.task_type == "news_lookup"
    assert result.needs_current_info is True


def test_docs_keyword_triggers_docs_lookup():
    result = detect_search_intent("What's the latest version of the API documentation?")
    assert result.task_type == "docs_lookup"
    assert result.needs_current_info is True


def test_who_is_triggers_encyclopedia_lookup_without_current_info():
    result = detect_search_intent("Who was Marie Curie?")
    assert result.task_type == "encyclopedia_lookup"
    assert result.needs_current_info is False


def test_what_is_stable_definition_triggers_definition_lookup():
    result = detect_search_intent("What is quantum entanglement?")
    assert result.task_type == "definition_lookup"
    assert result.needs_current_info is False


def test_what_is_latest_does_not_trigger_definition_lookup():
    """Regression test: 'what is the latest news today?' was misclassified as
    also needing a stable-background wiki lookup purely because it starts
    with 'what is', even though the whole sentence is a single current-info
    question, not a request to define/background some other subject. This
    caused irrelevant wiki results to be injected alongside the (correctly
    absent) current-info source, which visibly confused a live Ollama
    response. See app/search_intent.py's _ENCYCLOPEDIA_PATTERNS comment."""
    result = detect_search_intent("What is the latest news today?")
    assert result.task_type == "news_lookup"
    assert result.needs_current_info is True
    assert result.also_needs_wiki is False


def test_what_is_current_weather_does_not_trigger_definition_lookup():
    result = detect_search_intent("What is the current weather in Tokyo?")
    assert result.also_needs_wiki is False


def test_mixed_query_sets_also_needs_wiki():
    result = detect_search_intent("Who is Messi and did he score today?")
    assert result.needs_current_info is True
    assert result.also_needs_wiki is True


def test_ambiguous_message_defaults_to_general_chat():
    result = detect_search_intent("What's a good book to read this weekend?")
    assert result.task_type == "general_chat"
    assert result.needs_current_info is False


def test_empty_message_returns_general_chat():
    result = detect_search_intent("   ")
    assert result.task_type == "general_chat"
    assert result.needs_current_info is False
