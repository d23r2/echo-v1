"""ECHO Layer 2E — Phase 6 cross-layer integration + the end-to-end
"CognitiveBrief -> context -> goal progress" scenario. Never calls real
Ollama or a real cloud provider — monkeypatches LocalModelRouter's class
reference the same established way test_local_intelligence_chat_integration.py
does."""

from app import schemas
from app.models import Task
from app.services import goal_engine
from app.services.local_intelligence_engine import LocalIntelligenceEngine
from app.services.local_model_router import LocalModelRouter
from tests.fake_providers import FakeProvider


def test_context_selection_v2_flag_off_uses_legacy_gather_context(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="a plain answer")
    engine = LocalIntelligenceEngine(db_session, model_router=LocalModelRouter(provider=fake))

    result = engine.generate_response("hello there", mode="simple")
    assert "context_gathered" in result.pipeline_steps
    assert "context_bundle:v2" not in result.pipeline_steps


def test_context_selection_v2_flag_on_uses_context_bundle(db_session, monkeypatch):
    monkeypatch.setenv("CONTEXT_SELECTION_V2_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake = FakeProvider("ollama", available=True, response_text="a plain answer")
        engine = LocalIntelligenceEngine(db_session, model_router=LocalModelRouter(provider=fake))

        result = engine.generate_response("hello there", mode="simple")
        assert "context_bundle:v2" in result.pipeline_steps
        assert "context_gathered" not in result.pipeline_steps
        assert result.answer == "a plain answer"
    finally:
        get_settings.cache_clear()


def test_context_bundle_goal_context_reaches_the_draft_prompt(db_session, monkeypatch):
    """The concrete Phase 6 promise: a goal linked via active_project_id-less
    context still reaches the actual prompt sent to the model when Context
    Selection v2 is enabled, via the project_context fold-in."""
    from app.services.intent_classifier import classify_intent
    from app.services.local_intelligence_engine import _build_draft_system_prompt

    goal = goal_engine.create_goal(db_session, schemas.GoalCreate(title="Ship the Intelligence Center", origin="explicit_user"))
    from app.services import context_selector
    from app.services.local_intelligence_engine import _context_bundle_to_gathered

    bundle = context_selector.select_context(db_session, schemas.ContextRequest(user_message="how's my goal going?", goal_id=goal.id))
    gathered = _context_bundle_to_gathered(bundle)
    intent = classify_intent("how's my goal going?")
    prompt = _build_draft_system_prompt(db_session, intent, gathered, "default", None)
    assert "Ship the Intelligence Center" in prompt


def test_end_to_end_request_to_goal_progress_pipeline(db_session, monkeypatch):
    """user request -> CognitiveBrief/context -> (decision/plan already
    covered elsewhere) -> goal progress update, as one coherent chain."""
    goal = goal_engine.create_goal(db_session, schemas.GoalCreate(title="Finish the milestone", origin="explicit_user"))
    db_session.add(Task(title="Write the tests", status="todo", goal_id=goal.id))
    db_session.commit()

    monkeypatch.setenv("CONTEXT_SELECTION_V2_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        fake = FakeProvider("ollama", available=True, response_text="You're partially through — one task left.")
        engine = LocalIntelligenceEngine(db_session, model_router=LocalModelRouter(provider=fake))
        result = engine.generate_response("How am I doing on finishing the milestone?", mode="simple")
        assert result.answer

        # Now mark the evidence complete and confirm progress/achievement updates.
        task = db_session.query(Task).filter(Task.goal_id == goal.id).first()
        task.status = "done"
        db_session.commit()
        progress = goal_engine.compute_progress(db_session, goal.id)
        assert progress.percent_complete == 100.0
        achieved = goal_engine.maybe_mark_achieved(db_session, goal.id)
        assert achieved.status == "achieved"
    finally:
        get_settings.cache_clear()
