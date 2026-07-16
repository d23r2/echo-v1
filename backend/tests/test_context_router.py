"""app/services/context_router.py — Smart Context Router v1. Pure regex/
dataclass classification, no network/model calls — same testing posture as
test_search_intent.py. Covers the worked examples from the ECHO Personal OS
v1 spec plus the empty/ambiguous-input safe default.
"""

from app.services.context_router import classify_context


def test_personal_memory_question_routes_to_atlas_and_previous_conversation():
    route = classify_context("What did we decide about SearXNG?")
    assert route.selected_sources == ["atlas_memory", "previous_conversation"]
    assert route.should_search_atlas is True
    assert route.should_search_web is False
    assert route.should_search_wiki is False


def test_encyclopedia_question_routes_to_wiki():
    route = classify_context("Who was Nikola Tesla?")
    assert "wiki" in route.selected_sources
    assert route.should_search_wiki is True
    assert route.should_search_web is False


def test_live_score_question_routes_to_web_and_rss_not_wiki_alone():
    route = classify_context("What is the Liverpool score now?")
    assert "web_search" in route.selected_sources
    assert "rss" in route.selected_sources
    assert route.selected_sources != ["wiki"]
    assert route.should_search_web is True
    assert route.should_search_rss is True


def test_tasks_due_today_routes_to_tasks_and_schedule():
    route = classify_context("What tasks are due today?")
    assert route.selected_sources == ["tasks", "schedule"]
    assert route.should_search_tasks is True


def test_continue_where_we_left_off_routes_broadly():
    route = classify_context("Continue where we left off")
    assert route.selected_sources == ["projects", "tasks", "previous_conversation", "schedule", "library"]
    assert route.should_search_projects is True
    assert route.should_search_tasks is True


def test_explain_entropy_routes_to_wiki_or_normal_chat_not_current_web():
    route = classify_context("Explain entropy")
    assert route.selected_sources[0] in ("wiki", "normal_chat")
    assert route.should_search_web is False


def test_find_uploaded_file_routes_to_library():
    route = classify_context("Find the PDF I uploaded")
    assert route.selected_sources == ["library"]
    assert route.should_search_library is True


def test_active_projects_question_routes_to_projects():
    route = classify_context("What projects are active?")
    assert route.selected_sources == ["projects"]
    assert route.should_search_projects is True


def test_empty_message_defaults_to_normal_chat():
    route = classify_context("")
    assert route.selected_sources == ["normal_chat"]


def test_ambiguous_message_defaults_to_normal_chat_not_speculative_search():
    route = classify_context("hey, how's it going?")
    assert route.selected_sources == ["normal_chat"]
    assert route.should_search_web is False
    assert route.should_search_wiki is False
