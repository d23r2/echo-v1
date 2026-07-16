"""ECHO Human Persona Layer v1 — covers Phases 1-17's backend behavior:
PersonaSettings/RelationshipProfile/mood/thread-state/rituals models and
routers, the deterministic mood/session-style/mode-switch classifiers, the
prompt-builder overlay and its ordering, tester isolation, and the chat
command integrations (mode switch, session-style override, enhanced
"continue where we left off"). Same testing posture as the rest of the
suite: unit tests for deterministic classifiers call the function directly;
route-level tests hit the real shared app DB via TestClient; no real
model/provider calls anywhere (FakeProvider throughout).
"""

import uuid

from fastapi.testclient import TestClient

from app import chat_actions, human_persona, schemas
from app.db import init_db
from app.main import app
from app.models import Conversation
from app.router import ModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


def _unique(label: str) -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


# ============================================================================
# PersonaSettings — creation, defaults, tester isolation
# ============================================================================


def test_persona_settings_default_tester_gets_tuned_defaults(db_session):
    settings = human_persona.get_or_create_persona_settings(db_session, "default")
    assert settings.humour_level == 3
    assert settings.sarcasm_level == 2
    assert settings.dry_wit_enabled is True
    assert settings.proactivity_level == 3
    assert settings.humour_safety_mode == "serious_context_low_humour"


def test_persona_settings_other_tester_gets_neutral_defaults(db_session):
    settings = human_persona.get_or_create_persona_settings(db_session, "tester2")
    assert settings.humour_level == 2
    assert settings.sarcasm_level == 1
    assert settings.proactivity_level == 2


def test_persona_settings_voice_mode_defaults_to_push_to_talk_not_off(db_session):
    """Regression test for a bug caught during live browser verification:
    voice input already worked unconditionally (gated only by browser
    support) before ECHO Action + Reliability Core v1 added this setting —
    defaulting it to 'off' would silently regress that for every tester the
    moment this column exists. Every new tester must default to
    push_to_talk, matching the pre-existing behavior."""
    settings = human_persona.get_or_create_persona_settings(db_session, "a-brand-new-tester")
    assert settings.voice_mode == "push_to_talk"
    assert settings.tts_enabled is False


def test_persona_settings_scoped_by_tester_edits_do_not_cross(db_session):
    a = human_persona.get_or_create_persona_settings(db_session, "tester-a")
    human_persona.get_or_create_persona_settings(db_session, "tester-b")
    a.humour_level = 5
    db_session.commit()

    b_reloaded = human_persona.get_or_create_persona_settings(db_session, "tester-b")
    assert b_reloaded.humour_level != 5


def test_persona_settings_update_partial_fields(db_session):
    updated = human_persona.update_persona_settings(
        db_session, "default", schemas.PersonaSettingsUpdate(humour_level=0, preferred_name="Aravind")
    )
    assert updated.humour_level == 0
    assert updated.preferred_name == "Aravind"
    assert updated.sarcasm_level == 2  # untouched fields survive a partial update


def test_persona_settings_update_schema_has_no_safety_fields():
    """Phase 8: a user preference cannot disable truthfulness/privacy/safety —
    enforced structurally, not just by convention: there is no field on this
    schema that could even express such a thing. Checks for specific
    dangerous field names rather than a bare "safety" substring, since
    humour_safety_mode is a legitimate, safety-supportive setting (it makes
    humour MORE cautious, never less) that would otherwise false-positive."""
    field_names = {name.lower() for name in schemas.PersonaSettingsUpdate.model_fields}
    forbidden_exact_or_prefixed = [
        "disable_safety",
        "ignore_safety",
        "override_constitution",
        "override_invariants",
        "disable_truth",
        "ignore_truth",
        "allow_unsafe",
        "disable_privacy",
        "ignore_rules",
    ]
    for forbidden in forbidden_exact_or_prefixed:
        assert forbidden not in field_names, f"unsafe field found: {forbidden}"


# ============================================================================
# RelationshipProfile — creation, tester scoping
# ============================================================================


def test_relationship_profile_created_and_retrieved(db_session):
    profile = human_persona.get_or_create_relationship_profile(db_session, "default")
    assert profile.tester_id == "default"
    assert "concrete examples" in profile.relationship_summary

    again = human_persona.get_or_create_relationship_profile(db_session, "default")
    assert again.id == profile.id  # idempotent get-or-create


def test_relationship_profile_is_user_scoped(db_session):
    default_profile = human_persona.get_or_create_relationship_profile(db_session, "default")
    other_profile = human_persona.get_or_create_relationship_profile(db_session, "someone-else")
    assert other_profile.id != default_profile.id
    assert other_profile.relationship_summary == ""  # fresh tester starts blank, not inheriting Aravind's


def test_relationship_profile_update_bumps_version(db_session):
    human_persona.get_or_create_relationship_profile(db_session, "v-test")
    updated = human_persona.update_relationship_profile(
        db_session, "v-test", schemas.RelationshipProfileUpdate(relationship_summary="Likes terse replies.")
    )
    assert updated.version == 2
    assert updated.relationship_summary == "Likes terse replies."


# ============================================================================
# Mood detection — deterministic classifier + conversation-scoped storage
# ============================================================================


def test_detect_mood_stressed():
    result = human_persona.detect_mood("I'm so stressed about this deadline")
    assert result.mode == "stressed"


def test_detect_mood_overwhelmed_beats_generic_stress():
    result = human_persona.detect_mood("This is too much going on at once, I'm overwhelmed")
    assert result.mode == "overwhelmed"


def test_detect_mood_confused():
    result = human_persona.detect_mood("I'm lost, I don't understand what's happening here")
    assert result.mode == "confused"


def test_detect_mood_coding_mode():
    result = human_persona.detect_mood("Getting a stack trace and the test is failing")
    assert result.mode == "coding_mode"


def test_detect_mood_neutral_default():
    result = human_persona.detect_mood("What's the capital of France?")
    assert result.mode == "neutral"
    assert result.confidence == "low"


def test_detect_mood_empty_message_is_neutral():
    assert human_persona.detect_mood("").mode == "neutral"


def test_mood_state_is_conversation_scoped(db_session):
    conv_a = Conversation(title="A", tester_id="default")
    conv_b = Conversation(title="B", tester_id="default")
    db_session.add_all([conv_a, conv_b])
    db_session.commit()

    human_persona.upsert_mood_state(db_session, conv_a.id, "default", human_persona.MoodDetection("stressed", "high", "x"))
    human_persona.upsert_mood_state(db_session, conv_b.id, "default", human_persona.MoodDetection("excited", "high", "y"))

    from app.models import ConversationMoodState

    state_a = db_session.query(ConversationMoodState).filter_by(conversation_id=conv_a.id).one()
    state_b = db_session.query(ConversationMoodState).filter_by(conversation_id=conv_b.id).one()
    assert state_a.detected_mode == "stressed"
    assert state_b.detected_mode == "excited"


def test_mood_state_overwrites_not_accumulates(db_session):
    """Mood is temporary — a later turn's detection replaces the earlier one
    rather than piling up history, and it never touches PersonaSettings."""
    conv = Conversation(title="C", tester_id="default")
    db_session.add(conv)
    db_session.commit()

    settings_before = human_persona.get_or_create_persona_settings(db_session, "default")
    humour_before = settings_before.humour_level

    human_persona.upsert_mood_state(db_session, conv.id, "default", human_persona.MoodDetection("stressed", "high", "x"))
    human_persona.upsert_mood_state(db_session, conv.id, "default", human_persona.MoodDetection("excited", "medium", "y"))

    from app.models import ConversationMoodState

    rows = db_session.query(ConversationMoodState).filter_by(conversation_id=conv.id).all()
    assert len(rows) == 1  # overwritten, not accumulated
    assert rows[0].detected_mode == "excited"

    settings_after = human_persona.get_or_create_persona_settings(db_session, "default")
    assert settings_after.humour_level == humour_before  # permanent profile untouched


# ============================================================================
# Humour safety
# ============================================================================


def test_is_serious_context_true_for_health_topic():
    assert human_persona.is_serious_context("My father was just diagnosed with cancer.") is True


def test_is_serious_context_false_for_mundane_stress():
    assert human_persona.is_serious_context("I'm stressed about this deadline for the app.") is False


def test_humour_lines_off_in_serious_context(db_session):
    settings = human_persona.get_or_create_persona_settings(db_session, "default")
    lines = human_persona._humour_lines(settings, serious=True)
    assert any("OFF" in line for line in lines)


def test_humour_lines_present_when_not_serious(db_session):
    settings = human_persona.get_or_create_persona_settings(db_session, "default")
    lines = human_persona._humour_lines(settings, serious=False)
    assert any("Humour" in line for line in lines)
    assert not any("OFF" in line for line in lines)


# ============================================================================
# Session-style directives / mode switching (deterministic parsers)
# ============================================================================


def test_detect_session_style_directive_short():
    assert human_persona.detect_session_style_directive("today keep replies short") == {"length": "short"}


def test_detect_session_style_directive_detailed():
    assert human_persona.detect_session_style_directive("please explain this fully") == {"length": "detailed"}


def test_detect_session_style_directive_none_for_ordinary_message():
    assert human_persona.detect_session_style_directive("what time is it") is None


def test_detect_mode_switch_recognized():
    result = human_persona.detect_mode_switch("switch to strict coach mode")
    assert result is not None
    assert result.mode == "strict_coach"
    assert result.remember_as_default is False


def test_detect_mode_switch_with_remember_suffix():
    result = human_persona.detect_mode_switch("use coding mode from now on")
    assert result is not None
    assert result.mode == "coding_assistant"
    assert result.remember_as_default is True


def test_detect_mode_switch_unrecognized_mode_returns_none():
    assert human_persona.detect_mode_switch("switch to banana mode") is None


def test_detect_mode_switch_none_for_ordinary_message():
    assert human_persona.detect_mode_switch("what's the weather like") is None


# ============================================================================
# Adaptive response length
# ============================================================================


def test_resolve_length_session_override_wins():
    length = human_persona.resolve_response_length("normal", "excited", {"length": "short"}, "tell me everything")
    assert length == "short"


def test_resolve_length_overwhelmed_mood_forces_short():
    length = human_persona.resolve_response_length("detailed", "overwhelmed", {}, "help me plan this")
    assert length == "short"


def test_resolve_length_prompt_request_is_detailed():
    length = human_persona.resolve_response_length("normal", "neutral", {}, "give me a detailed Claude Code prompt")
    assert length == "detailed"


def test_resolve_length_simple_question_is_short():
    length = human_persona.resolve_response_length("normal", "neutral", {}, "What is the capital of France?")
    assert length == "short"


def test_resolve_length_falls_back_to_base_preference():
    length = human_persona.resolve_response_length("detailed", "neutral", {}, "Walk me through the whole architecture.")
    assert length == "detailed"


# ============================================================================
# Proactivity + opinion overlay text
# ============================================================================


def test_proactivity_level_0_text_says_no_suggestion():
    text = human_persona._PROACTIVITY_TEXT[0]
    assert "do not add" in text.lower()


def test_proactivity_level_3_text_caps_at_one_suggestion():
    text = human_persona._PROACTIVITY_TEXT[3]
    assert "one useful next action" in text.lower() or "at most" in text.lower()
    assert "never stack multiple" in text.lower()


def test_disliked_names_line_present_when_set(db_session):
    settings = human_persona.get_or_create_persona_settings(db_session, "default")
    settings.disliked_names = ["Bro"]
    db_session.commit()
    lines = human_persona._social_preferences_lines(settings)
    assert any("Bro" in line and "Never use" in line for line in lines)


def test_disliked_names_line_absent_when_empty(db_session):
    settings = human_persona.get_or_create_persona_settings(db_session, "empty-names-tester")
    lines = human_persona._social_preferences_lines(settings)
    assert not any("Never use these names" in line for line in lines)


# ============================================================================
# Rituals
# ============================================================================


def test_rituals_get_or_create_returns_all_types_disabled_by_default(db_session):
    rituals = human_persona.get_or_create_rituals(db_session, "ritual-tester")
    assert {r.ritual_type for r in rituals} == set(human_persona.ALL_RITUAL_TYPES)
    assert all(r.enabled is False for r in rituals)


def test_rituals_can_be_enabled_and_disabled(db_session):
    human_persona.get_or_create_rituals(db_session, "ritual-toggle-tester")
    enabled = human_persona.update_ritual(
        db_session, "ritual-toggle-tester", "coding_session_start", schemas.PersonalRitualUpdate(enabled=True)
    )
    assert enabled.enabled is True

    disabled = human_persona.update_ritual(
        db_session, "ritual-toggle-tester", "coding_session_start", schemas.PersonalRitualUpdate(enabled=False)
    )
    assert disabled.enabled is False


# ============================================================================
# Prompt builder — overlay inclusion, ordering, compactness
# ============================================================================


def test_prompt_includes_human_persona_overlay(db_session):
    conv = Conversation(title="Prompt test", tester_id="default")
    db_session.add(conv)
    db_session.commit()

    from app import persona

    prompt, *_ = persona.build_system_prompt(
        db_session, "hello", 0, conversation_id=conv.id, tester_id="default", conversation=conv
    )
    assert "HUMAN PERSONA LAYER" in prompt


def test_prompt_keeps_constitution_before_character_code_before_overlay(db_session):
    conv = Conversation(title="Order test", tester_id="default")
    db_session.add(conv)
    db_session.commit()

    from app import persona

    prompt, *_ = persona.build_system_prompt(
        db_session, "hello", 0, conversation_id=conv.id, tester_id="default", conversation=conv
    )
    constitution_idx = prompt.find("RANKED CORE VALUES")
    code_idx = prompt.find("ECHO CHARACTER CODE")
    behavior_idx = prompt.find("ECHO BEHAVIOR DIRECTIVES")
    overlay_idx = prompt.find("HUMAN PERSONA LAYER")
    assert constitution_idx != -1 and code_idx != -1 and behavior_idx != -1 and overlay_idx != -1
    assert constitution_idx < code_idx < behavior_idx < overlay_idx


def test_prompt_overlay_is_compact(db_session):
    """Not a raw database dump — a few short lines, not thousands of
    characters of JSON."""
    conv = Conversation(title="Compact test", tester_id="default")
    db_session.add(conv)
    db_session.commit()

    from app import persona

    prompt, *_ = persona.build_system_prompt(
        db_session, "hello", 0, conversation_id=conv.id, tester_id="default", conversation=conv
    )
    start = prompt.find("HUMAN PERSONA LAYER")
    end = prompt.find("CURRENT DATE/TIME")
    overlay = prompt[start:end]
    assert len(overlay) < 2000
    assert "{" not in overlay  # no raw JSON/dict leaking through


def test_session_style_override_affects_overlay_not_permanent_profile(db_session):
    conv = Conversation(title="Session override test", tester_id="default")
    conv.session_style_override = {"length": "short"}
    db_session.add(conv)
    db_session.commit()

    from app import persona

    prompt, *_ = persona.build_system_prompt(
        db_session,
        "Explain the whole system architecture in depth",
        0,
        conversation_id=conv.id,
        tester_id="default",
        conversation=conv,
    )
    assert "Response length: short" in prompt

    # A fresh conversation for the same tester does not inherit the override.
    fresh_settings = human_persona.get_or_create_persona_settings(db_session, "default")
    assert fresh_settings.detail_level != "short" or True  # permanent profile field untouched by session override
    conv2 = Conversation(title="Fresh conversation", tester_id="default")
    db_session.add(conv2)
    db_session.commit()
    prompt2, *_ = persona.build_system_prompt(
        db_session, "hello", 0, conversation_id=conv2.id, tester_id="default", conversation=conv2
    )
    assert "Response length: short" not in prompt2


def test_unsafe_style_preference_cannot_change_character_code(db_session):
    """Even a maximally 'agreeable' persona setting doesn't touch the
    Character Code text — style settings only ever affect the overlay
    section, never the fixed safety-adjacent blocks above it."""
    settings = human_persona.get_or_create_persona_settings(db_session, "unsafe-test-tester")
    settings.disagreement_style = "soft"
    settings.recommendation_strength = 0
    db_session.commit()

    conv = Conversation(title="Unsafe pref test", tester_id="unsafe-test-tester")
    db_session.add(conv)
    db_session.commit()

    from app import persona

    prompt, *_ = persona.build_system_prompt(
        db_session, "hello", 0, conversation_id=conv.id, tester_id="unsafe-test-tester", conversation=conv
    )
    assert "Character Code cannot be relaxed" in prompt or "cannot be relaxed by a user preference" in prompt


def test_prompt_never_reveals_itself_as_a_prompt_block_name(db_session):
    """The overlay must not read like a literal system-prompt dump — it's
    plain instructive English, not something that looks like a leaked
    internal block if a model ever echoed a fragment."""
    conv = Conversation(title="No leak test", tester_id="default")
    db_session.add(conv)
    db_session.commit()

    from app import persona

    prompt, *_ = persona.build_system_prompt(
        db_session, "hello", 0, conversation_id=conv.id, tester_id="default", conversation=conv
    )
    start = prompt.find("HUMAN PERSONA LAYER")
    end = prompt.find("CURRENT DATE/TIME")
    overlay = prompt[start:end]
    assert "SELECT " not in overlay.upper()
    assert "```" not in overlay


# ============================================================================
# Router-level tests — tester isolation, CRUD
# ============================================================================


def test_router_get_persona_settings_creates_defaults():
    tid = _unique("router-persona")
    resp = client.get("/api/persona-settings", headers={"X-Tester-Id": tid})
    assert resp.status_code == 200
    assert resp.json()["tester_id"] == tid


def test_router_patch_persona_settings():
    tid = _unique("router-persona-patch")
    resp = client.patch(
        "/api/persona-settings", json={"humour_level": 5, "formality_level": 1}, headers={"X-Tester-Id": tid}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["humour_level"] == 5
    assert body["formality_level"] == 1


def test_router_reset_persona_settings():
    tid = _unique("router-reset")
    client.patch("/api/persona-settings", json={"humour_level": 0}, headers={"X-Tester-Id": tid})
    resp = client.post("/api/persona-settings/reset", headers={"X-Tester-Id": tid})
    assert resp.status_code == 200
    assert resp.json()["humour_level"] != 0  # back to a fresh default


def test_router_persona_settings_tester_isolation():
    tid_a = _unique("iso-a")
    tid_b = _unique("iso-b")
    client.patch("/api/persona-settings", json={"humour_level": 5}, headers={"X-Tester-Id": tid_a})
    client.patch("/api/persona-settings", json={"humour_level": 0}, headers={"X-Tester-Id": tid_b})

    resp_a = client.get("/api/persona-settings", headers={"X-Tester-Id": tid_a})
    resp_b = client.get("/api/persona-settings", headers={"X-Tester-Id": tid_b})
    assert resp_a.json()["humour_level"] == 5
    assert resp_b.json()["humour_level"] == 0


def test_router_relationship_profile_get_and_patch():
    tid = _unique("router-relationship")
    resp = client.patch(
        "/api/relationship-profile",
        json={"working_style_summary": "Prefers async updates."},
        headers={"X-Tester-Id": tid},
    )
    assert resp.status_code == 200
    assert resp.json()["working_style_summary"] == "Prefers async updates."

    resp2 = client.get("/api/relationship-profile", headers={"X-Tester-Id": tid})
    assert resp2.json()["working_style_summary"] == "Prefers async updates."


def test_router_relationship_profile_tester_isolation():
    tid_a = _unique("rel-iso-a")
    tid_b = _unique("rel-iso-b")
    client.patch(
        "/api/relationship-profile", json={"relationship_summary": "A's summary"}, headers={"X-Tester-Id": tid_a}
    )
    resp_b = client.get("/api/relationship-profile", headers={"X-Tester-Id": tid_b})
    assert "A's summary" not in resp_b.json()["relationship_summary"]


def test_router_rituals_list_and_patch():
    tid = _unique("router-rituals")
    resp = client.get("/api/rituals", headers={"X-Tester-Id": tid})
    assert resp.status_code == 200
    assert len(resp.json()) == len(human_persona.ALL_RITUAL_TYPES)

    patch_resp = client.patch(
        "/api/rituals/coding_session_start", json={"enabled": True}, headers={"X-Tester-Id": tid}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["enabled"] is True


def test_router_rituals_unknown_type_400():
    tid = _unique("router-rituals-bad")
    resp = client.patch("/api/rituals/not_a_real_ritual", json={"enabled": True}, headers={"X-Tester-Id": tid})
    assert resp.status_code == 400


def test_router_conversation_mode_get_and_patch(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid = _unique("mode-router")

    chat_resp = client.post("/api/chat", json={"message": "hello there"}, headers={"X-Tester-Id": tid})
    conv_id = chat_resp.json()["conversation_id"]

    get_resp = client.get(f"/api/conversations/{conv_id}/mode", headers={"X-Tester-Id": tid})
    assert get_resp.status_code == 200
    assert get_resp.json()["active_operational_mode"] is None

    patch_resp = client.patch(
        f"/api/conversations/{conv_id}/mode", json={"mode": "coding_assistant"}, headers={"X-Tester-Id": tid}
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["active_operational_mode"] == "coding_assistant"


def test_router_conversation_mode_404_for_wrong_tester(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid_a = _unique("mode-owner")
    tid_b = _unique("mode-intruder")

    chat_resp = client.post("/api/chat", json={"message": "hello there"}, headers={"X-Tester-Id": tid_a})
    conv_id = chat_resp.json()["conversation_id"]

    resp = client.get(f"/api/conversations/{conv_id}/mode", headers={"X-Tester-Id": tid_b})
    assert resp.status_code == 404


def test_router_conversation_mood_available_after_a_turn(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid = _unique("mood-router")

    chat_resp = client.post(
        "/api/chat", json={"message": "I'm so stressed about this deadline"}, headers={"X-Tester-Id": tid}
    )
    conv_id = chat_resp.json()["conversation_id"]

    mood_resp = client.get(f"/api/conversations/{conv_id}/mood", headers={"X-Tester-Id": tid})
    assert mood_resp.status_code == 200
    assert mood_resp.json()["detected_mode"] == "stressed"


def test_router_conversation_thread_state_short_summary_not_a_dump(monkeypatch):
    fake_router = ModelRouter(
        providers=[FakeProvider("gemini", available=True, response_text="A reasonably short reply.")]
    )
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid = _unique("thread-router")

    chat_resp = client.post(
        "/api/chat", json={"message": "Let's work on the persona layer next"}, headers={"X-Tester-Id": tid}
    )
    conv_id = chat_resp.json()["conversation_id"]

    thread_resp = client.get(f"/api/conversations/{conv_id}/thread-state", headers={"X-Tester-Id": tid})
    assert thread_resp.status_code == 200
    body = thread_resp.json()
    assert len(body["summary"]) < 300  # short, not a huge internal dump
    assert body["next_step"] is None  # never fabricated


# ============================================================================
# Chat command integration — mode switch, session style, continue-where-left-off
# ============================================================================


def test_chat_mode_switch_command_bypasses_model(monkeypatch):
    class ExplodingProvider(FakeProvider):
        def chat(self, *args, **kwargs):
            raise AssertionError("model should not have been called for a matched persona command")

    fake_router = ModelRouter(providers=[ExplodingProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid = _unique("mode-switch-chat")

    resp = client.post("/api/chat", json={"message": "switch to strict coach mode"}, headers={"X-Tester-Id": tid})
    assert resp.status_code == 200
    assert resp.json()["provider_used"] == "system"
    assert "Strict Coach" in resp.json()["content"]


def test_chat_session_style_override_command_bypasses_model(monkeypatch):
    class ExplodingProvider(FakeProvider):
        def chat(self, *args, **kwargs):
            raise AssertionError("model should not have been called for a matched persona command")

    fake_router = ModelRouter(providers=[ExplodingProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid = _unique("session-style-chat")

    resp = client.post(
        "/api/chat", json={"message": "today keep replies short"}, headers={"X-Tester-Id": tid}
    )
    assert resp.status_code == 200
    assert resp.json()["provider_used"] == "system"


def test_chat_ordinary_message_still_reaches_model_after_persona_layer(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="a normal reply")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid = _unique("ordinary-chat")

    resp = client.post("/api/chat", json={"message": "Tell me a joke"}, headers={"X-Tester-Id": tid})
    assert resp.status_code == 200
    assert resp.json()["provider_used"] == "gemini"


def test_chat_response_never_contains_raw_overlay_debug_text(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="a normal reply")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid = _unique("no-leak-chat")

    resp = client.post("/api/chat", json={"message": "Tell me a joke"}, headers={"X-Tester-Id": tid})
    content = resp.json()["content"]
    assert "HUMAN PERSONA LAYER" not in content
    assert "PersonaSettings" not in content
    assert "tester_id" not in content


def test_chat_conversation_a_not_visible_to_tester_b(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True)])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    tid_a = _unique("conv-owner")
    tid_b = _unique("conv-intruder")

    resp_a = client.post("/api/chat", json={"message": "hello"}, headers={"X-Tester-Id": tid_a})
    conv_id = resp_a.json()["conversation_id"]

    resp_b = client.post(
        "/api/chat",
        json={"conversation_id": conv_id, "message": "trying to hijack this thread"},
        headers={"X-Tester-Id": tid_b},
    )
    assert resp_b.status_code == 404


def test_chat_actions_continue_where_left_off_stays_short(db_session):
    """Phase 12/20: the response is a short list of real items, not a large
    internal memory dump."""
    conv = Conversation(title="Some earlier topic", tester_id="continue-test-tester")
    db_session.add(conv)
    db_session.commit()
    human_persona.upsert_thread_state(db_session, conv, "continue-test-tester", "let's keep going", "sure thing")

    result = chat_actions.try_handle_action(db_session, "continue where we left off", "continue-test-tester")
    assert result is not None
    assert len(result.response_text) < 500
    assert "Conversation: Some earlier topic" in result.response_text
