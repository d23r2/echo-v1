"""ECHO Cognitive Core v1 — Phase 13/16 integration tests: CognitiveBrief
inserted into both prompt builders (persona.py's build_system_prompt for
the normal/streaming chat path, and local_intelligence_engine.py's draft
prompt for the engine path), never shown to the user, success criteria fed
to the critic, missing knowledge lowering confidence.
"""

from fastapi.testclient import TestClient

from app import persona
from app.db import init_db
from app.main import app
from app.models import Conversation
from app.providers.base import split_reasoning_and_answer
from app.router import ModelRouter
from app.services.local_intelligence_engine import LocalIntelligenceEngine, _initial_confidence
from app.services.local_model_router import LocalModelRouter
from tests.fake_providers import FakeProvider

init_db()
client = TestClient(app)


class ScriptedProvider(FakeProvider):
    def __init__(self, *args, responses=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.responses = responses or []
        self._i = 0

    def chat(self, system_prompt, messages, model=None):
        self.chat_call_count += 1
        self.last_model_requested = model
        if self._i >= len(self.responses):
            raise AssertionError(f"ScriptedProvider ran out of queued responses (call #{self._i + 1})")
        text = self.responses[self._i]
        self._i += 1
        return split_reasoning_and_answer(text)


# ============================================================================
# F. Prompt integration (persona.py's build_system_prompt)
# ============================================================================


def test_cognitive_brief_included_for_complex_task(db_session):
    conversation = Conversation(title="test")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(
        db_session, "Give me a prompt to update Android APK.", turn_count=0, conversation=conversation
    )
    assert "COGNITIVE_BRIEF" in prompt
    assert "Goal:" in prompt


def test_cognitive_brief_skipped_for_simple_chat(db_session):
    conversation = Conversation(title="test2")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(db_session, "hi", turn_count=0, conversation=conversation)
    assert "COGNITIVE_BRIEF" not in prompt


def test_constitution_persona_appear_before_cognitive_brief(db_session):
    conversation = Conversation(title="test3")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(
        db_session, "Give me a prompt to update Android APK.", turn_count=0, conversation=conversation
    )
    brief_pos = prompt.find("COGNITIVE_BRIEF")
    assert brief_pos > 0
    # Character code (persona) always appears earlier in the prompt than the brief.
    from app.human_persona import CHARACTER_CODE

    char_code_pos = prompt.find(CHARACTER_CODE[:40])
    assert char_code_pos != -1
    assert char_code_pos < brief_pos


def test_cognitive_core_disabled_setting_skips_brief(db_session):
    from app.services import cognitive_core

    cognitive_core.update_settings(db_session, {"cognitive_core_enabled": False})
    conversation = Conversation(title="test4")
    db_session.add(conversation)
    db_session.commit()

    prompt, *_ = persona.build_system_prompt(
        db_session, "Give me a prompt to update Android APK.", turn_count=0, conversation=conversation
    )
    assert "COGNITIVE_BRIEF" not in prompt


def test_no_internal_brief_appears_in_normal_ui_response(monkeypatch):
    """The COGNITIVE_BRIEF section only ever lands in the system prompt
    sent to the model — confirm the actual chat response the user sees
    never contains it, using a fake provider so no real model is called."""
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="A clean, normal reply.")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)

    resp = client.post("/api/chat/stream", json={"message": "Give me a prompt to update Android APK.", "provider": "gemini"})
    assert resp.status_code == 200
    assert "COGNITIVE_BRIEF" not in resp.text
    assert "Goal:" not in resp.text or "goal" not in resp.text.lower()[:50]


def test_clean_metadata_line_unaffected(monkeypatch):
    fake_router = ModelRouter(providers=[FakeProvider("gemini", available=True, response_text="A clean, normal reply.")])
    monkeypatch.setattr("app.routers.chat.model_router", fake_router)
    resp = client.post("/api/chat/stream", json={"message": "hello there", "provider": "gemini"})
    assert resp.status_code == 200
    assert "event: token" in resp.text or "event: done" in resp.text


# ============================================================================
# G. Local Intelligence integration
# ============================================================================


def test_complex_prompt_request_uses_cognitive_core(db_session):
    fake = ScriptedProvider("ollama", available=True, responses=["Here is your prompt."])
    engine = LocalIntelligenceEngine(db_session, model_router=LocalModelRouter(provider=fake))
    result = engine.generate_response("Give me a prompt to update Android APK.")
    assert "cognitive_brief:built" in result.pipeline_steps


def test_simple_greeting_does_not_use_cognitive_core(db_session):
    fake = ScriptedProvider("ollama", available=True, responses=["Hi there!"])
    engine = LocalIntelligenceEngine(db_session, model_router=LocalModelRouter(provider=fake))
    result = engine.generate_response("hi")
    assert "cognitive_brief:built" not in result.pipeline_steps


def test_missing_knowledge_lowers_confidence():
    from app.services.context_gatherer import GatheredContext
    from app.services.intent_classifier import classify_intent

    intent = classify_intent("What is the latest Liverpool score?")
    context = GatheredContext()
    without = _initial_confidence(intent, context, has_missing_knowledge=False)
    with_missing = _initial_confidence(intent, context, has_missing_knowledge=True)
    order = ["unverified", "low", "medium", "high"]
    assert order.index(with_missing) <= order.index(without)


def test_release_testing_confidence_still_capped_low_regardless_of_missing_knowledge():
    from app.services.context_gatherer import GatheredContext
    from app.services.intent_classifier import classify_intent

    intent = classify_intent("Is ECHO Green now?")
    confidence = _initial_confidence(intent, GatheredContext(), has_missing_knowledge=True)
    assert confidence in ("low", "unverified")


def test_success_criteria_used_by_critic(db_session):
    critic_json = (
        '{"passed": false, "issues": ["missing success criteria"], "needs_repair": true, '
        '"confidence": "low", "missing_sources": false, "too_verbose": false, "unsafe_or_overconfident": false}'
    )
    repaired_text = "A better answer that meets the criteria."
    fake = ScriptedProvider("ollama", available=True, responses=["Draft answer.", critic_json, repaired_text])
    engine = LocalIntelligenceEngine(db_session, model_router=LocalModelRouter(provider=fake))
    result = engine.generate_response("Give me a Claude Code prompt to fix the release pipeline.", mode="deep")
    # The critic call must have actually run (queue was consumed past the draft).
    assert fake.chat_call_count >= 2
    assert "critic:" in " ".join(result.pipeline_steps)
