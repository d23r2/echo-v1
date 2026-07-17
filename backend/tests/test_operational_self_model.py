"""ECHO Operational Self-Model v1 — unit tests for mode/confidence/risk
detection (operational_self_model.py) plus integration tests for prompt
insertion (persona.py's build_system_prompt) and the interface-settings
router. No real model/network call anywhere — deterministic classification
only, matching this module's own design (see its docstring)."""

from fastapi.testclient import TestClient

from app import persona
from app.db import init_db
from app.human_persona import CHARACTER_CODE
from app.main import app
from app.models import Conversation
from app.services import operational_self_model as osm

init_db()
client = TestClient(app)


# ============================================================================
# Mode detection
# ============================================================================


def test_normal_chat_gets_normal_mode():
    model = osm.build_operational_self_model("hi echo, how are you today?")
    assert model.current_mode == "normal"


def test_coding_prompt_request_sets_coding_mode():
    model = osm.build_operational_self_model("Give me a Claude Code prompt to fix the APK build.")
    assert model.current_mode == "coding_assistant"


def test_tests_failed_sets_troubleshooting_mode():
    model = osm.build_operational_self_model("The tests failed after my last change.")
    assert model.current_mode == "troubleshooting"


def test_release_status_question_sets_release_testing_mode_and_unverified_confidence():
    model = osm.build_operational_self_model("Is ECHO Green now?")
    assert model.current_mode == "release_testing"
    assert model.confidence == "unverified"


def test_current_info_question_becomes_unverified_without_source():
    model = osm.build_operational_self_model("What's the latest score in the match?")
    assert model.confidence == "unverified"


def test_current_info_question_with_source_is_not_forced_unverified():
    model = osm.build_operational_self_model(
        "What's the latest score in the match?", has_current_source=True
    )
    assert model.confidence != "unverified"


def test_overwhelmed_message_sets_low_energy_support_mode():
    from app.human_persona import detect_mood

    message = "I'm overwhelmed, there's too much going on."
    mood = detect_mood(message)
    model = osm.build_operational_self_model(message, mood_mode=mood.mode)
    assert model.current_mode == "low_energy_support"


def test_conscious_question_flagged_and_denies_in_overlay():
    model = osm.build_operational_self_model("Are you conscious?")
    assert model.consciousness_or_feelings_question is True
    overlay = osm.build_overlay_text(model)
    assert "not conscious" in overlay.lower()
    assert "not the same as feeling" not in overlay.lower()  # sanity: no stray copy-paste


def test_feelings_question_flagged_and_denies_in_overlay():
    model = osm.build_operational_self_model("Can you feel?")
    assert model.consciousness_or_feelings_question is True
    overlay = osm.build_overlay_text(model)
    assert "real feelings" in overlay.lower()


# ============================================================================
# Risk detection / confirmation
# ============================================================================


def test_public_push_creates_publication_risk_and_requires_confirmation():
    model = osm.build_operational_self_model("Push this to GitHub.")
    assert model.should_ask_confirmation is True
    assert any("public" in r.lower() for r in model.active_risks)


def test_delete_memories_creates_destructive_risk_and_requires_confirmation():
    model = osm.build_operational_self_model("Delete my memories from Atlas.")
    assert model.should_ask_confirmation is True
    assert any("delete" in r.lower() or "archive" in r.lower() for r in model.active_risks)


def test_normal_message_has_no_risks_and_no_confirmation_needed():
    model = osm.build_operational_self_model("What's a good way to learn Python?")
    assert model.should_ask_confirmation is False
    assert model.active_risks == []


# ============================================================================
# Self-model never overrides safety — should_not_do always includes the
# consciousness/emotion + current-fact honesty rules regardless of mode.
# ============================================================================


def test_should_not_do_always_includes_consciousness_and_source_honesty():
    for message in ["hi", "Push this to GitHub.", "Is ECHO Green?", "I'm overwhelmed."]:
        model = osm.build_operational_self_model(message)
        joined = " ".join(model.should_not_do).lower()
        assert "conscious" in joined
        assert "source" in joined


# ============================================================================
# Cognitive Core integration (optional — must not require it)
# ============================================================================


def test_task_understanding_grounds_goal_and_risks_when_provided():
    class FakeTaskUnderstanding:
        goal_summary = "Help the user create a safe Claude Code prompt for the APK fix."
        risks_json = ["Prompt could be too vague to act on."]
        unknowns_json = ["Exact APK build failure reason not yet known."]
        confidence = "incomplete"

    model = osm.build_operational_self_model(
        "Give me a prompt to fix the APK build.", task_understanding=FakeTaskUnderstanding()
    )
    assert model.current_goal == FakeTaskUnderstanding.goal_summary
    assert "Prompt could be too vague to act on." in model.active_risks
    assert "Exact APK build failure reason not yet known." in model.known_limits
    assert model.confidence == "unverified"


def test_build_operational_self_model_works_with_no_optional_context():
    """Cognitive Core / Permission Center / relationship profile are all
    optional — omitting every optional param must never raise."""
    model = osm.build_operational_self_model("hello")
    assert model.current_mode == "normal"


# ============================================================================
# Meaningfulness gate
# ============================================================================


def test_trivial_greeting_is_not_meaningful():
    model = osm.build_operational_self_model("hi")
    assert osm.is_meaningful_interaction(model, "hi") is False


def test_risky_request_is_meaningful():
    model = osm.build_operational_self_model("Push this to GitHub.")
    assert osm.is_meaningful_interaction(model, "Push this to GitHub.") is True


def test_release_testing_is_meaningful():
    model = osm.build_operational_self_model("Is ECHO Green now?")
    assert osm.is_meaningful_interaction(model, "Is ECHO Green now?") is True


# ============================================================================
# Prompt integration (persona.py's build_system_prompt)
# ============================================================================


def test_self_model_overlay_appears_for_meaningful_request(db_session):
    conversation = Conversation(title="test")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(
        db_session, "Push this to GitHub.", turn_count=0, conversation=conversation
    )
    assert "OPERATIONAL SELF-MODEL" in prompt
    assert "Mode: cautious" in prompt or "risky" in prompt.lower()


def test_self_model_overlay_skipped_for_trivial_chat(db_session):
    conversation = Conversation(title="test2")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(db_session, "hi", turn_count=0, conversation=conversation)
    assert "OPERATIONAL SELF-MODEL" not in prompt


def test_style_directives_and_character_code_appear_before_self_model(db_session):
    conversation = Conversation(title="test3")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(
        db_session, "Push this to GitHub.", turn_count=0, conversation=conversation
    )
    char_code_pos = prompt.find(CHARACTER_CODE[:40])
    style_pos = prompt.find("ECHO RESPONSE STYLE")
    self_model_pos = prompt.find("OPERATIONAL SELF-MODEL")
    assert char_code_pos != -1 and style_pos != -1 and self_model_pos != -1
    assert char_code_pos < style_pos < self_model_pos


def test_self_model_disabled_setting_skips_overlay(db_session):
    osm.update_interface_settings(db_session, {"operational_self_model_enabled": False})
    conversation = Conversation(title="test4")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(
        db_session, "Push this to GitHub.", turn_count=0, conversation=conversation
    )
    assert "OPERATIONAL SELF-MODEL" not in prompt


def test_snapshot_persisted_for_meaningful_interaction(db_session):
    conversation = Conversation(title="test5")
    db_session.add(conversation)
    db_session.commit()

    persona.build_system_prompt(
        db_session, "Push this to GitHub.", turn_count=0, conversation_id=conversation.id, conversation=conversation
    )
    snapshots = osm.list_recent_snapshots(db_session, conversation_id=conversation.id)
    assert len(snapshots) == 1
    assert snapshots[0].should_ask_confirmation is True


def test_no_snapshot_persisted_for_trivial_chat(db_session):
    conversation = Conversation(title="test6")
    db_session.add(conversation)
    db_session.commit()

    persona.build_system_prompt(db_session, "hi", turn_count=0, conversation=conversation)
    snapshots = osm.list_recent_snapshots(db_session, conversation_id=conversation.id)
    assert len(snapshots) == 0


def test_no_raw_self_model_json_in_normal_chat_response(monkeypatch):
    from app.providers.base import split_reasoning_and_answer
    from app.router import ModelRouter
    from tests.fake_providers import FakeProvider

    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="A clean, normal reply.")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat/stream", json={"message": "Push this to GitHub.", "provider": "gemini"})
    assert resp.status_code == 200
    assert "OPERATIONAL SELF-MODEL" not in resp.text
    assert "current_goal" not in resp.text
    assert "should_ask_confirmation" not in resp.text
    _ = split_reasoning_and_answer  # imported for parity with sibling test files


def test_clean_metadata_line_unaffected(monkeypatch):
    from app.router import ModelRouter
    from tests.fake_providers import FakeProvider

    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="A clean, normal reply.")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    resp = client.post("/api/chat/stream", json={"message": "hello there", "provider": "gemini"})
    assert resp.status_code == 200
    assert "event: token" in resp.text or "event: done" in resp.text


# ============================================================================
# Router
# ============================================================================


def test_interface_settings_get_and_patch():
    resp = client.get("/api/interface-settings")
    assert resp.status_code == 200
    body = resp.json()
    assert body["show_advanced_nav"] is False
    assert body["operational_self_model_enabled"] is True

    resp = client.patch("/api/interface-settings", json={"show_advanced_nav": True, "compact_sidebar": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["show_advanced_nav"] is True
    assert body["compact_sidebar"] is True

    # revert so later tests in this module see the default again
    client.patch("/api/interface-settings", json={"show_advanced_nav": False, "compact_sidebar": False})


def test_self_model_recent_endpoint_returns_list():
    resp = client.get("/api/self-model/recent")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
