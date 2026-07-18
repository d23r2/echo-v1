"""ECHO Action + Reliability Core v1 — Reliability / Evaluation Lab.

No model call anywhere — every checker is a structural assertion against
deterministic classifiers (intent_classifier, search_intent, mood
detection, the chat command parser) and the Action System's own registry.
"""

from app.services import evaluation_lab


def test_fixture_has_cases():
    cases = evaluation_lab.load_cases()
    assert len(cases) == 21


def test_every_case_has_a_registered_checker():
    cases = evaluation_lab.load_cases()
    for case in cases:
        assert case["check_type"] in evaluation_lab._CHECKS, f"no checker for {case['id']}"


def test_evaluation_run_creates_results(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    assert run.status == "completed"
    assert run.total_cases == 21
    assert run.passed_cases + run.failed_cases + run.warnings == 21


def test_failures_are_recorded(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    from app.models import EvaluationResult

    results = db_session.query(EvaluationResult).filter(EvaluationResult.run_id == run.id).all()
    assert len(results) == 21


def test_green_only_when_all_required_checks_pass(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    if run.failed_cases == 0 and run.warnings == 0:
        assert run.result_summary == "green"
    elif run.failed_cases > 0:
        assert run.result_summary == "red"
    else:
        assert run.result_summary == "yellow"


def test_release_status_honesty_case_passes(db_session):
    """The core 'never claim Green from local inference alone' rule — this
    is the one case that must reliably pass since it tests a hard-coded
    rule, not a soft heuristic."""
    run = evaluation_lab.run_evaluation(db_session)
    from app.models import EvaluationResult

    result = db_session.query(EvaluationResult).filter(EvaluationResult.run_id == run.id, EvaluationResult.case_id == "release_status_honesty").first()
    assert result.status == "pass"


def test_cloud_disabled_case_passes_by_default(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    from app.models import EvaluationResult

    result = db_session.query(EvaluationResult).filter(EvaluationResult.run_id == run.id, EvaluationResult.case_id == "cloud_disabled_safe_default").first()
    assert result.status == "pass"


def test_destructive_action_case_passes(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    from app.models import EvaluationResult

    result = db_session.query(EvaluationResult).filter(EvaluationResult.run_id == run.id, EvaluationResult.case_id == "destructive_requires_confirmation").first()
    assert result.status == "pass"


def test_no_debug_leak_in_reasons(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    from app.models import EvaluationResult

    results = db_session.query(EvaluationResult).filter(EvaluationResult.run_id == run.id).all()
    for r in results:
        assert "Traceback" not in r.reason
        assert ".py\", line" not in r.reason


def test_current_info_case_flags_correctly(db_session):
    """'What is the Liverpool score now?' must be flagged as needing a
    current source, not silently answered from training data."""
    run = evaluation_lab.run_evaluation(db_session)
    from app.models import EvaluationResult

    result = db_session.query(EvaluationResult).filter(EvaluationResult.run_id == run.id, EvaluationResult.case_id == "no_source_current_info").first()
    assert result.status == "pass"


def test_list_and_get_run(db_session):
    run = evaluation_lab.run_evaluation(db_session)
    runs = evaluation_lab.list_runs(db_session)
    assert any(r.id == run.id for r in runs)
    fetched = evaluation_lab.get_run(db_session, run.id)
    assert fetched.id == run.id
