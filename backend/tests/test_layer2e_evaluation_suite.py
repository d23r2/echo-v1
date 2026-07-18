"""ECHO Layer 2E — Phase 8 Layer 2 evaluation suite additions to
evaluation_lab.py. Every new check function wraps an already-tested Layer
2A-2D system directly — no model call anywhere in this file, matching the
rest of evaluation_lab.py's convention. Uses the isolated db_session
fixture (never the real app DB), and separately confirms the whole
fixture-driven run never touches AtlasEntry (real user memory)."""

from app.models import AtlasEntry, DecisionCase, Goal, Plan, TaskUnderstanding
from app.services import evaluation_lab


def _case(check_type, **overrides):
    base = {"id": "test-case", "category": "test", "user_message": "test message", "check_type": check_type}
    base.update(overrides)
    return base


# ---- task_understanding_category ----


def test_task_understanding_category_pass(db_session):
    case = _case(
        "task_understanding_category",
        user_message="Implement a new feature that lets users export their tasks as a CSV file, including error handling.",
        check_expected="coding",
    )
    status, reason = evaluation_lab._check_task_understanding_category(db_session, case)
    assert status == "pass"


def test_task_understanding_category_warns_for_simple_message(db_session):
    case = _case("task_understanding_category", user_message="hi", check_expected="question")
    status, _reason = evaluation_lab._check_task_understanding_category(db_session, case)
    assert status == "warning"  # never a false pass/fail for a message too simple to classify


def test_task_understanding_category_fail_on_mismatch(db_session):
    case = _case(
        "task_understanding_category",
        user_message="The login test is failing with a 500 error, can you find the bug?",
        check_expected="coding",  # wrong on purpose — this is genuinely debugging
    )
    status, _reason = evaluation_lab._check_task_understanding_category(db_session, case)
    assert status == "fail"


# ---- context_relevance ----


def test_context_relevance_pass_for_current_info(db_session):
    case = _case("context_relevance", user_message="What's the latest breaking news on quantum computing today?", check_expected="tool_evidence")
    status, _reason = evaluation_lab._check_context_relevance(db_session, case)
    assert status == "pass"


def test_context_relevance_warns_when_category_absent(db_session):
    case = _case("context_relevance", user_message="hello", check_expected="goal_context")
    status, _reason = evaluation_lab._check_context_relevance(db_session, case)
    assert status == "warning"  # honestly empty, never a fabricated pass


# ---- plan_validity ----


def test_plan_validity_pass_for_clean_chain(db_session):
    case = _case(
        "plan_validity",
        steps=[
            {"title": "Design"},
            {"title": "Implement", "depends_on_titles": ["Design"]},
        ],
        check_expected=True,
    )
    status, _reason = evaluation_lab._check_plan_validity(db_session, case)
    assert status == "pass"


def test_plan_validity_detects_real_cycle(db_session):
    case = _case(
        "plan_validity",
        steps=[
            {"title": "A", "depends_on_titles": ["B"]},
            {"title": "B", "depends_on_titles": ["A"]},
        ],
        check_expected=False,
    )
    status, _reason = evaluation_lab._check_plan_validity(db_session, case)
    assert status == "pass"  # correctly matched the expected "invalid" outcome


# ---- decision_transparency ----


def test_decision_transparency_pass(db_session):
    case = _case("decision_transparency", options=[{"label": "Postgres"}, {"label": "SQLite"}])
    status, _reason = evaluation_lab._check_decision_transparency(db_session, case)
    assert status == "pass"


# ---- tool_efficiency ----


def test_tool_efficiency_no_tools_for_creative(db_session):
    case = _case("tool_efficiency", user_message="Write me a short haiku about autumn leaves.", max_expected_tools=0)
    status, _reason = evaluation_lab._check_tool_efficiency(db_session, case)
    assert status == "pass"


def test_tool_efficiency_fails_when_exceeding_budget(db_session):
    case = _case("tool_efficiency", user_message="what are my active projects and open tasks?", max_expected_tools=0)
    status, reason = evaluation_lab._check_tool_efficiency(db_session, case)
    assert status == "fail"
    assert "expected at most 0" in reason


# ---- layer2_context_comparison ("with vs without Layer 2 features") ----


def test_layer2_context_comparison_pass(db_session):
    case = _case("layer2_context_comparison", user_message="What should I focus on next?")
    status, _reason = evaluation_lab._check_layer2_context_comparison(db_session, case)
    assert status == "pass"


# ---- Full suite run + fixture isolation from real user memory ----


def test_full_evaluation_run_includes_layer2_cases(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    assert run.total_cases >= 21
    assert run.status == "completed"


def test_evaluation_fixtures_never_create_atlas_entries(db_session):
    """Phase 8's explicit 'prevent benchmark fixtures from leaking into real
    user memory' rule — none of the new checks touch AtlasEntry."""
    before = db_session.query(AtlasEntry).count()
    evaluation_lab.run_evaluation(db_session)
    after = db_session.query(AtlasEntry).count()
    assert after == before


def test_evaluation_run_isolates_all_fixture_domain_rows(db_session):
    tracked_models = (Goal, Plan, DecisionCase, TaskUnderstanding)
    before = {model: db_session.query(model).count() for model in tracked_models}

    run = evaluation_lab.run_evaluation(db_session)

    after = {model: db_session.query(model).count() for model in tracked_models}
    assert run.status == "completed"
    assert after == before
