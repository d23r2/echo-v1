"""ECHO Layer 2D — orchestration_engine.py: policy CRUD, task classification,
cloud eligibility, stage-profile budgeting, build_plan(). All pure/deterministic
— no model call, no tool call, isolated db_session fixture."""

from app import schemas
from app.models import OrchestrationPolicy
from app.services import orchestration_engine as oe

# ---- Policy CRUD ----


def test_ensure_default_policies_seeds_one_per_category(db_session):
    oe.ensure_default_policies(db_session)
    categories = {p.task_category for p in db_session.query(OrchestrationPolicy).all()}
    assert categories == set(oe._DEFAULT_POLICY_BY_CATEGORY.keys())


def test_ensure_default_policies_idempotent(db_session):
    oe.ensure_default_policies(db_session)
    oe.ensure_default_policies(db_session)
    count = db_session.query(OrchestrationPolicy).count()
    assert count == len(oe._DEFAULT_POLICY_BY_CATEGORY)


def test_get_policy_falls_back_to_mixed_for_unknown_category(db_session):
    policy = oe.get_policy(db_session, "not_a_real_category")
    assert policy.task_category == "mixed"


def test_update_policy_partial_update(db_session):
    oe.ensure_default_policies(db_session)
    policy = oe.get_policy(db_session, "question")
    updated = oe.update_policy(db_session, policy.id, schemas.OrchestrationPolicyUpdate(cloud_allowed=True))
    assert updated.cloud_allowed is True
    assert updated.stage_profile == "simple"  # untouched fields survive a partial update


def test_update_policy_404_for_unknown_id(db_session):
    assert oe.update_policy(db_session, "does-not-exist", schemas.OrchestrationPolicyUpdate(cloud_allowed=True)) is None


# ---- Task classification (chains existing classifiers, never re-derives) ----


def test_classify_task_category_question():
    category, intent = oe.classify_task_category("I really appreciate your patience and kindness.")
    assert category == "question"
    assert intent.intent is not None


def test_classify_task_category_debugging():
    category, _intent = oe.classify_task_category("Fix the failing backend test for the login flow")
    assert category == "debugging"


# ---- Stage-profile budgeting (Phase 7: tight budget forces a cheaper profile) ----


def test_effective_profile_downgrades_when_budget_too_tight():
    assert oe._effective_profile("deep", 1) == "simple"
    assert oe._effective_profile("deep", 2) == "standard"
    assert oe._effective_profile("deep", 4) == "deep"
    assert oe._effective_profile("simple", 1) == "simple"


def test_hard_max_calls_backstop_cannot_be_overridden(db_session):
    request = schemas.OrchestrationRequest(user_message="Fix the failing backend test for the login flow", max_model_calls=999)
    plan = oe.build_plan(db_session, request)
    assert plan.budgets["max_model_calls"] <= oe._HARD_MAX_CALLS


# ---- Cloud eligibility (composes existing cloud_fallback_* settings) ----


def test_build_plan_cloud_not_allowed_by_default(db_session):
    request = schemas.OrchestrationRequest(user_message="Fix the failing backend test for the login flow")
    plan = oe.build_plan(db_session, request)
    assert plan.cloud_allowed is False


def test_build_plan_local_only_privacy_blocks_cloud_even_if_requested(db_session, monkeypatch):
    monkeypatch.setenv("CLOUD_FALLBACK_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        request = schemas.OrchestrationRequest(
            user_message="Fix the failing backend test for the login flow",
            privacy_level="local_only",
            cloud_allowed=True,
            cloud_confirmed=True,
        )
        plan = oe.build_plan(db_session, request)
        assert plan.cloud_allowed is False
    finally:
        get_settings.cache_clear()


def test_build_plan_cloud_requires_confirmation_when_policy_demands_it(db_session, monkeypatch):
    monkeypatch.setenv("CLOUD_FALLBACK_ENABLED", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        # "Review this code for bugs" classifies as the "code_review" intent,
        # which IS in Settings.cloud_fallback_allowed_intents' default list —
        # required for _resolve_cloud_allowed()'s intent-allowlist check to
        # ever reach the confirmation check being tested here.
        oe.ensure_default_policies(db_session)
        policy = oe.get_policy(db_session, "debugging")
        oe.update_policy(db_session, policy.id, schemas.OrchestrationPolicyUpdate(cloud_allowed=True, require_confirmation_for_cloud=True))

        request_unconfirmed = schemas.OrchestrationRequest(
            user_message="Review this code for bugs", task_type="debugging", privacy_level="cloud_ok", cloud_confirmed=False
        )
        plan_unconfirmed = oe.build_plan(db_session, request_unconfirmed)
        assert plan_unconfirmed.cloud_allowed is False

        request_confirmed = schemas.OrchestrationRequest(
            user_message="Review this code for bugs", task_type="debugging", privacy_level="cloud_ok", cloud_confirmed=True
        )
        plan_confirmed = oe.build_plan(db_session, request_confirmed)
        assert plan_confirmed.cloud_allowed is True
        assert "cloud_call" in plan_confirmed.confirmation_points
    finally:
        get_settings.cache_clear()


# ---- Stage plans for complex tasks (planner/coder/critic only when warranted) ----


def test_coding_task_deep_profile_includes_critic_and_repair(db_session):
    request = schemas.OrchestrationRequest(user_message="Fix the failing backend test for the login flow", task_type="debugging")
    plan = oe.build_plan(db_session, request)
    assert plan.stage_profile == "deep"
    stage_names = [s.stage for s in plan.stages]
    assert "critique" in stage_names
    assert "repair" in stage_names
    assert "coding" in plan.selected_models


def test_simple_question_is_single_stage_single_model(db_session):
    request = schemas.OrchestrationRequest(user_message="I really appreciate your patience and kindness.")
    plan = oe.build_plan(db_session, request)
    assert plan.stage_profile == "simple"
    assert len(plan.stages) == 1
    assert plan.stages[0].stage == "final"
    assert plan.budgets["max_model_calls"] == 1


# ---- Failure categorization (translates provider_errors, never re-derives) ----


def test_categorize_failure_maps_provider_error_categories():
    class FakeExc(Exception):
        status_code = 429

    assert oe.categorize_failure(FakeExc("rate limited")) == "rate_limited"


def test_categorize_failure_unknown_defaults_to_unknown_error():
    assert oe.categorize_failure(Exception("something weird")) == "unknown_error"


# ---- Structured-output repair (deterministic, bounded, no extra model call) ----


def test_repair_structured_output_passthrough_when_already_valid():
    text, repaired = oe.repair_structured_output('{"a": 1}')
    assert text == '{"a": 1}'
    assert repaired is False


def test_repair_structured_output_strips_code_fence():
    text, repaired = oe.repair_structured_output('```json\n{"a": 1}\n```')
    assert text == '{"a": 1}'
    assert repaired is True


def test_repair_structured_output_extracts_embedded_json():
    text, repaired = oe.repair_structured_output('Here you go: {"y": true} — hope that helps!')
    assert text == '{"y": true}'
    assert repaired is True


def test_repair_structured_output_gives_up_on_non_json():
    text, repaired = oe.repair_structured_output("This is not JSON at all.")
    assert text is None
    assert repaired is False
