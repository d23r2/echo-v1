"""ECHO Layer 2D — orchestration_engine.py: run_orchestration() execution.
Never touches real Ollama or a real cloud provider — monkeypatches the
LocalModelRouter/LocalIntelligenceEngine class references inside the modules
that construct them internally, same established pattern as
test_local_intelligence_chat_integration.py (these modules don't accept an
injected instance, so the class reference itself must be patched)."""

from app import schemas
from app.services import orchestration_engine as oe
from app.services.local_model_router import LocalModelRouter
from app.services.orchestration_engine import run_orchestration
from tests.fake_providers import FakeProvider


def _simple_request(message="I really appreciate your patience and kindness.", **overrides):
    body = dict(user_message=message)
    body.update(overrides)
    return schemas.OrchestrationRequest(**body)


def _patch_simple_router(monkeypatch, fake_provider):
    monkeypatch.setattr("app.services.orchestration_engine.LocalModelRouter", lambda *a, **k: LocalModelRouter(provider=fake_provider))


def _patch_engine_router(monkeypatch, fake_provider):
    monkeypatch.setattr(
        "app.services.local_intelligence_engine.LocalModelRouter",
        lambda *a, **k: LocalModelRouter(provider=fake_provider),
    )


# ---- Simple task: exactly one local model call ----


def test_simple_task_uses_exactly_one_local_model_call(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="a plain answer")
    _patch_simple_router(monkeypatch, fake)

    run = run_orchestration(db_session, _simple_request())
    assert run.status == "completed"
    assert run.total_model_calls == 1
    assert fake.chat_call_count == 1
    assert run.answer == "a plain answer"
    assert run.stage_profile_used == "simple"


# ---- Complex coding task: staged pipeline only when policy threshold met ----


def test_complex_coding_task_runs_staged_pipeline_via_engine(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="def add(a, b):\n    return a + b")
    _patch_engine_router(monkeypatch, fake)

    request = _simple_request("Fix the failing backend test for the login flow", task_type="debugging")
    run = run_orchestration(db_session, request)
    assert run.stage_profile_used == "deep"
    assert run.status == "completed"
    assert run.answer
    assert fake.chat_call_count >= 1  # delegated to the engine's own draft (at minimum) call


# ---- Missing role model falls back locally (LocalModelRouter's own tested retry) ----


class _FlakyRoleProvider:
    """chat() fails for the role-specific model but succeeds once retried
    against the plain default model — exercises LocalModelRouter.call()'s
    own already-tested fallback path end-to-end through the orchestrator."""

    def __init__(self, default_model: str):
        self.default_model = default_model
        self.calls: list[str | None] = []

    def available(self):
        return True, None

    def chat(self, system_prompt, messages, model=None):
        from app.providers.base import split_reasoning_and_answer

        self.calls.append(model)
        if model != self.default_model:
            raise RuntimeError("model not installed")
        return split_reasoning_and_answer("fallback answer from the default model")


def test_missing_role_model_falls_back_to_default_locally(db_session, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL_CODING", "coder-7b")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        settings = get_settings()
        fake = _FlakyRoleProvider(default_model=settings.ollama_model)
        _patch_simple_router(monkeypatch, fake)

        request = _simple_request("Fix the failing backend test for the login flow", task_type="debugging", max_model_calls=1)
        run = run_orchestration(db_session, request)
        assert run.status == "completed"
        assert run.answer == "fallback answer from the default model"
        assert fake.calls == ["coder-7b", settings.ollama_model]
    finally:
        get_settings.cache_clear()


# ---- Cloud gating: disabled by default, confirmation-gated, privacy-gated ----


def test_cloud_disabled_by_default_prevents_cloud_call(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="local only answer")
    _patch_engine_router(monkeypatch, fake)

    request = _simple_request("Review this code for bugs", task_type="debugging")
    run = run_orchestration(db_session, request)
    assert run.cloud_used is False


def test_cloud_confirmation_required_blocks_cloud_even_when_enabled(db_session, monkeypatch):
    monkeypatch.setenv("CLOUD_FALLBACK_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        oe.ensure_default_policies(db_session)
        policy = oe.get_policy(db_session, "debugging")
        oe.update_policy(db_session, policy.id, schemas.OrchestrationPolicyUpdate(cloud_allowed=True, require_confirmation_for_cloud=True))

        fake = FakeProvider("ollama", available=True, response_text="local answer, unconfirmed cloud")
        _patch_engine_router(monkeypatch, fake)

        request = _simple_request("Review this code for bugs", task_type="debugging", privacy_level="cloud_ok", cloud_confirmed=False)
        run = run_orchestration(db_session, request)
        assert run.cloud_used is False
    finally:
        get_settings.cache_clear()


def test_private_task_cannot_route_to_cloud_under_local_only_policy(db_session, monkeypatch):
    monkeypatch.setenv("CLOUD_FALLBACK_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        oe.ensure_default_policies(db_session)
        policy = oe.get_policy(db_session, "debugging")
        oe.update_policy(db_session, policy.id, schemas.OrchestrationPolicyUpdate(cloud_allowed=True, require_confirmation_for_cloud=False))

        fake = FakeProvider("ollama", available=True, response_text="local-only answer")
        _patch_engine_router(monkeypatch, fake)

        request = _simple_request(
            "Review this code for bugs", task_type="debugging", privacy_level="local_only", cloud_allowed=True, cloud_confirmed=True
        )
        run = run_orchestration(db_session, request)
        assert run.cloud_used is False
    finally:
        get_settings.cache_clear()


# ---- Tool usage matches classification: none for creative, present for current-info ----


def test_creative_task_makes_no_tool_call(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="Once upon a time...")
    _patch_simple_router(monkeypatch, fake)

    request = _simple_request("Write me a short poem about the ocean.")
    run = run_orchestration(db_session, request)
    assert run.tools_used_json == []


# ---- Provider timeout / failure triggers a bounded, clean failure (no crash) ----


def test_provider_failure_produces_clean_failed_run_not_a_crash(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, raises=TimeoutError("connection timed out"))
    _patch_simple_router(monkeypatch, fake)

    run = run_orchestration(db_session, _simple_request())
    assert run.status == "failed"
    assert run.stop_reason == "unavailable"
    assert "Traceback" not in (run.answer or "")


# ---- Billing/quota errors categorized cleanly, never a raw exception ----


def test_categorize_failure_never_leaks_raw_exception_text():
    exc = RuntimeError("insufficient quota: account 12345 over billing limit reached")
    category = oe.categorize_failure(exc)
    assert category in ("quota_exceeded", "billing_required")
    assert isinstance(category, str)


# ---- Budgets stop excessive calls ----


class _SlowProvider:
    """A real (small) delay so the elapsed-time budget check has something
    concrete to trip on — a zero-cost FakeProvider call can finish in under
    a millisecond, which would make a tight latency_budget_ms test flaky."""

    def available(self):
        return True, None

    def chat(self, system_prompt, messages, model=None):
        import time

        from app.providers.base import split_reasoning_and_answer

        time.sleep(0.05)
        return split_reasoning_and_answer("an answer that took some time")


def test_tight_latency_budget_stops_the_run(db_session, monkeypatch):
    _patch_simple_router(monkeypatch, _SlowProvider())

    request = _simple_request(latency_budget_ms=1)
    run = run_orchestration(db_session, request)
    assert run.status == "stopped_budget"
    assert run.stop_reason == "latency_budget_ms exceeded"


# ---- Structured-output repair wired into execution ----


def test_structured_output_repaired_within_budget(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text='Sure! ```json\n{"result": "ok"}\n```')
    _patch_simple_router(monkeypatch, fake)

    request = _simple_request(structured_output_required=True)
    run = run_orchestration(db_session, request)
    assert run.status == "completed"
    assert run.answer == '{"result": "ok"}'
    repair_stages = [s for s in run.stages_json if s["stage"] == "repair"]
    assert len(repair_stages) == 1
    assert repair_stages[0]["status"] == "completed"


def test_structured_output_unrepairable_marks_run_failed(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="This is just plain prose, no JSON here.")
    _patch_simple_router(monkeypatch, fake)

    request = _simple_request(structured_output_required=True)
    run = run_orchestration(db_session, request)
    assert run.status == "failed"
    assert run.stop_reason == "malformed_output"


# ---- Clean via-metadata: no raw prompts, secrets, or stack traces leak into stored state ----


def test_run_never_stores_raw_system_prompt_or_traceback(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="a clean answer")
    _patch_simple_router(monkeypatch, fake)

    run = run_orchestration(db_session, _simple_request())
    serialized = str(run.stages_json) + str(run.answer)
    assert "Traceback" not in serialized
    assert "You are Echo, a helpful assistant" not in serialized  # the internal system prompt text


# ---- Loop prevention: hard cap survives even an absurd requested budget ----


def test_absurd_requested_call_budget_still_capped(db_session, monkeypatch):
    fake = FakeProvider("ollama", available=True, response_text="fine")
    _patch_engine_router(monkeypatch, fake)

    request = _simple_request("Fix the failing backend test for the login flow", task_type="debugging", max_model_calls=10_000)
    run = run_orchestration(db_session, request)
    assert run.total_model_calls <= oe._HARD_MAX_CALLS
