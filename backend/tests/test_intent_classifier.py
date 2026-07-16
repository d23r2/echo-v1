"""ECHO Local Intelligence Engine v1, Phase 3 — app/services/intent_classifier.py.
Pure deterministic classification, no network/model calls — same testing
posture as test_search_intent.py/test_context_router.py. Covers the spec's
worked examples plus the 8 required routing tests.
"""

from app.services.intent_classifier import classify_intent


def test_stable_background_question_routes_to_wiki_local():
    c = classify_intent("Who was Nikola Tesla?")
    assert c.intent == "wiki_background"
    assert c.freshness_need == "stable"
    assert c.source_need == "wiki"
    assert c.can_answer_local_only is True


def test_current_live_question_routes_to_web_not_wiki_only():
    c = classify_intent("What is the Liverpool score now?")
    assert c.intent == "current_info"
    assert c.freshness_need == "live"
    assert c.source_need == "web"
    assert c.can_answer_local_only is False


def test_memory_question_routes_to_atlas_previous_conversation():
    c = classify_intent("What did we decide about SearXNG?")
    assert c.intent in ("personal_memory", "previous_conversation")
    assert c.source_need == "memory"
    assert c.can_answer_local_only is True


def test_task_question_routes_to_project_task():
    c = classify_intent("What tasks are due today?")
    assert c.intent == "project_task"


def test_coding_question_routes_to_reasoning_workflow():
    c = classify_intent("Review this code for bugs")
    assert c.intent in ("coding", "code_review")
    assert c.reasoning_need == "high"
    assert c.answer_style in ("detailed", "checklist")


def test_prompt_request_routes_to_detailed_prompt_output():
    c = classify_intent("Give me a Claude Code prompt for this")
    assert c.intent == "prompt_generation"
    assert c.answer_style == "prompt"
    assert c.reasoning_need == "medium"
    assert c.difficulty in ("medium", "hard")


def test_emotional_support_message_routes_to_low_pressure_style():
    c = classify_intent("I'm overwhelmed. What should I do next?")
    assert c.intent == "emotional_support"
    assert c.answer_style == "short"
    assert c.reasoning_need == "low"


def test_unknown_intent_falls_back_safely():
    c = classify_intent("hmm")
    assert c.intent == "unknown"
    assert c.can_answer_local_only is True  # never blocks answering
    assert c.should_ask_clarifying_question is True


def test_empty_message_is_normal_chat_not_unknown():
    c = classify_intent("")
    assert c.intent == "normal_chat"
    assert c.should_ask_clarifying_question is False


def test_library_file_question():
    c = classify_intent("Summarize the PDF I uploaded.")
    assert c.intent == "library_file"
    assert c.source_need == "file"


def test_release_testing_question_does_not_claim_local_only_certainty():
    c = classify_intent("Is ECHO Green now?")
    assert c.intent == "release_testing"
    assert c.answer_style == "checklist"


def test_image_generation_question():
    c = classify_intent("Generate an image of a sunset")
    assert c.intent == "image_generation"


def test_troubleshooting_question():
    c = classify_intent("My Android app keeps crashing on startup")
    assert c.intent == "troubleshooting"
    assert c.reasoning_need == "high"


def test_study_tutor_question():
    c = classify_intent("Teach me how recursion works")
    assert c.intent == "study_tutor"


def test_creative_writing_question():
    c = classify_intent("Write me a short story about a robot")
    assert c.intent == "creative_writing"


def test_normal_chat_question_stays_easy_and_local():
    c = classify_intent("Explain entropy simply.")
    assert c.intent == "normal_chat"
    assert c.difficulty == "easy"
    assert c.can_answer_local_only is True


def test_context_route_is_carried_through():
    c = classify_intent("Who was Nikola Tesla?")
    assert c.context_route.selected_sources == ["wiki", "normal_chat"]
