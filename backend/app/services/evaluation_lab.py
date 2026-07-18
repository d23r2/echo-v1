"""ECHO Action + Reliability Core v1 — Reliability / Evaluation Lab.

Runs a fixed set of fixture cases (app/fixtures/evaluation_lab_cases.json)
against ECHO's existing DETERMINISTIC classifiers/registries — intent
classification, search-intent current-info detection, mood detection, the
chat command parser, and the Action System's own risk/permission metadata.
No model call anywhere in this module, real or fake — every check here is
a structural assertion about routing/safety behavior, which is exactly
what stays stable enough to regression-test without mocking an LLM.
"""

import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EvaluationResult, EvaluationRun
from app.services import action_system, permission_center

logger = logging.getLogger(__name__)

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "evaluation_lab_cases.json"


def load_cases() -> list[dict]:
    with open(_FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _check_search_intent_current_info(db: Session, case: dict) -> tuple[str, str]:
    from app.search_intent import detect_search_intent

    result = detect_search_intent(case["user_message"])
    if result.needs_current_info == case["check_expected"]:
        return "pass", f"needs_current_info={result.needs_current_info} as expected"
    return "fail", f"expected needs_current_info={case['check_expected']}, got {result.needs_current_info}"


def _check_intent_source_need(db: Session, case: dict) -> tuple[str, str]:
    from app.services.intent_classifier import classify_intent

    result = classify_intent(case["user_message"])
    if result.source_need == case["check_expected"]:
        return "pass", f"source_need={result.source_need} as expected"
    return "warning", f"expected source_need={case['check_expected']}, got {result.source_need}"


def _check_intent_classification(db: Session, case: dict) -> tuple[str, str]:
    from app.services.intent_classifier import classify_intent

    result = classify_intent(case["user_message"])
    if result.intent == case["check_expected"]:
        return "pass", f"intent={result.intent} as expected"
    return "fail", f"expected intent={case['check_expected']}, got {result.intent}"


def _check_release_testing_confidence_capped(db: Session, case: dict) -> tuple[str, str]:
    from app.services.context_gatherer import GatheredContext
    from app.services.intent_classifier import classify_intent
    from app.services.local_intelligence_engine import _initial_confidence

    intent = classify_intent(case["user_message"])
    if intent.intent != "release_testing":
        return "warning", f"message no longer classifies as release_testing (got {intent.intent}) — check is stale"
    confidence = _initial_confidence(intent, GatheredContext())
    if confidence == "low":
        return "pass", "release_testing confidence correctly capped at low"
    return "fail", f"release_testing confidence was '{confidence}', expected 'low' — Green could be claimed from local inference alone"


def _check_action_capability_exists(db: Session, case: dict) -> tuple[str, str]:
    expected = case["check_expected"]
    spec = action_system.ACTIONS.get(expected["action_name"])
    if spec is None:
        return "fail", f"action '{expected['action_name']}' is not registered"
    if spec.risk_level != expected["risk_level"]:
        return "fail", f"expected risk_level={expected['risk_level']}, got {spec.risk_level}"
    return "pass", f"action '{spec.name}' registered with risk_level={spec.risk_level}"


def _check_destructive_action_requires_confirmation(db: Session, case: dict) -> tuple[str, str]:
    action_name = case["check_expected"]
    spec = action_system.ACTIONS.get(action_name)
    if spec is None:
        return "fail", f"action '{action_name}' is not registered"
    if spec.risk_level != "destructive":
        return "fail", f"expected risk_level=destructive, got {spec.risk_level}"
    run = action_system.run_action(db, action_name, {"kind": "project", "id": "nonexistent"}, confirm=False)
    if run.status == "pending":
        return "pass", "destructive action correctly stayed pending without confirmation"
    return "fail", f"destructive action ran without confirmation (status={run.status})"


def _check_chat_action_parses(db: Session, case: dict) -> tuple[str, str]:
    from app import chat_actions

    result = chat_actions.try_handle_action(db, case["user_message"])
    if result is not None and result.action_type == case["check_expected"]:
        return "pass", f"deterministic command parser matched '{result.action_type}'"
    return "warning", f"expected action_type={case['check_expected']}, got {result.action_type if result else None}"


def _check_mood_detection(db: Session, case: dict) -> tuple[str, str]:
    from app.human_persona import detect_mood

    result = detect_mood(case["user_message"])
    if result.mode == case["check_expected"]:
        return "pass", f"mood detected as '{result.mode}' as expected"
    return "warning", f"expected mood={case['check_expected']}, got {result.mode}"


def _check_cloud_disabled_by_default(db: Session, case: dict) -> tuple[str, str]:
    settings = get_settings()
    cloud_perm = permission_center.get_permission(db, "cloud_api_use")
    cloud_perm_level = cloud_perm.level if cloud_perm else "disabled"
    if not settings.cloud_fallback_enabled and cloud_perm_level == "disabled":
        return "pass", "cloud_fallback_enabled=False and cloud_api_use permission=disabled"
    return "fail", f"cloud_fallback_enabled={settings.cloud_fallback_enabled}, cloud_api_use={cloud_perm_level} — a paid API could be reached"


# ============================================================================
# ECHO Layer 2E — Phase 8: Layer 2 evaluation suite. Every check below
# reuses an already-built, already-tested Layer 2A-2D system directly
# (task_understanding_v2/cognitive_core, context_selector, plan_engine,
# decision_engine, tool_strategy) — never a second implementation, never a
# real or fake model call. Any DB row a check creates (a throwaway Plan/
# DecisionCase/TaskUnderstanding) is structural test fixture data, the same
# established pattern _check_destructive_action_requires_confirmation
# already uses — never AtlasEntry/MemoryCandidate, so real user memory is
# never touched.
# ============================================================================


def _check_task_understanding_category(db: Session, case: dict) -> tuple[str, str]:
    from app.services import cognitive_core

    tu = cognitive_core.build_task_understanding(db, case["user_message"])
    if tu is None:
        return "warning", "message classified as too simple for a TaskUnderstanding — check may be stale"
    if tu.task_category == case["check_expected"]:
        return "pass", f"task_category={tu.task_category} as expected"
    return "fail", f"expected task_category={case['check_expected']}, got {tu.task_category}"


def _check_context_relevance(db: Session, case: dict) -> tuple[str, str]:
    from app import schemas
    from app.services import context_selector

    expected_category = case["check_expected"]
    request = schemas.ContextRequest(user_message=case["user_message"], goal_id=case.get("goal_id"), project_id=case.get("project_id"))
    bundle = context_selector.select_context(db, request)
    included = getattr(bundle, expected_category, None)
    if included:
        return "pass", f"'{expected_category}' present in the selected ContextBundle"
    return "warning", f"'{expected_category}' was not present in the selected ContextBundle (no matching data seeded for this case)"


def _check_plan_validity(db: Session, case: dict) -> tuple[str, str]:
    from app import schemas
    from app.services import plan_engine

    steps = [schemas.PlanStepCreate(**s) for s in case["steps"]]
    plan = plan_engine.create_plan(db, schemas.PlanCreate(objective=case["user_message"], steps=steps))
    result = plan_engine.validate_plan(db, plan.id)
    if result.valid == case["check_expected"]:
        return "pass", f"plan validity={result.valid} as expected ({len(result.issues)} issue(s))"
    return "fail", f"expected valid={case['check_expected']}, got {result.valid} — issues: {[i.message for i in result.issues]}"


def _check_decision_transparency(db: Session, case: dict) -> tuple[str, str]:
    from app import schemas
    from app.services import decision_engine

    options = [schemas.DecisionOptionCreate(**o) for o in case["options"]]
    decision = decision_engine.create_decision_case(db, schemas.DecisionCaseCreate(question=case["user_message"], objective="evaluation fixture", options=options))
    analysed = decision_engine.analyse(db, decision.id)
    report = analysed.report_json or {}
    required_fields = ("decision_summary", "no_clear_winner", "evidence_quality", "confidence_band", "user_confirmation_needed")
    missing = [f for f in required_fields if f not in report]
    if missing:
        return "fail", f"DecisionReport missing required transparency field(s): {missing}"
    return "pass", "DecisionReport carries all required transparency fields"


def _check_tool_efficiency(db: Session, case: dict) -> tuple[str, str]:
    from app.services import tool_strategy

    plan = tool_strategy.build_tool_plan(case["user_message"])
    tool_names = [item.tool_name for item in plan.items]
    if len(tool_names) != len(set(tool_names)):
        return "fail", f"duplicate tool(s) selected: {tool_names}"
    max_expected = case.get("max_expected_tools", 2)
    if len(tool_names) > max_expected:
        return "fail", f"selected {len(tool_names)} tool(s) (expected at most {max_expected}) — {tool_names}"
    return "pass", f"{len(tool_names)} tool(s) selected, no duplicates: {tool_names}"


def _check_layer2_context_comparison(db: Session, case: dict) -> tuple[str, str]:
    """'Compare with and without Layer 2 features' — a concrete, deterministic
    with/without comparison: the same message's ContextBundle must differ
    (goal_context present) once a real goal is linked, versus not."""
    from app import schemas
    from app.models import Goal
    from app.services import context_selector

    goal = Goal(title="Evaluation fixture goal", origin="explicit_user", status="active")
    db.add(goal)
    db.commit()
    db.refresh(goal)

    without = context_selector.select_context(db, schemas.ContextRequest(user_message=case["user_message"]))
    with_goal = context_selector.select_context(db, schemas.ContextRequest(user_message=case["user_message"], goal_id=goal.id))

    if without.goal_context is None and with_goal.goal_context is not None:
        return "pass", "ContextBundle correctly differs with vs. without Layer 2 goal linkage"
    return "fail", f"expected goal_context only when linked — without={without.goal_context!r}, with={with_goal.goal_context!r}"


_CHECKS = {
    "search_intent_current_info": _check_search_intent_current_info,
    "intent_source_need": _check_intent_source_need,
    "intent_classification": _check_intent_classification,
    "release_testing_confidence_capped": _check_release_testing_confidence_capped,
    "action_capability_exists": _check_action_capability_exists,
    "destructive_action_requires_confirmation": _check_destructive_action_requires_confirmation,
    "chat_action_parses": _check_chat_action_parses,
    "mood_detection": _check_mood_detection,
    "cloud_disabled_by_default": _check_cloud_disabled_by_default,
    "task_understanding_category": _check_task_understanding_category,
    "context_relevance": _check_context_relevance,
    "plan_validity": _check_plan_validity,
    "decision_transparency": _check_decision_transparency,
    "tool_efficiency": _check_tool_efficiency,
    "layer2_context_comparison": _check_layer2_context_comparison,
}


def run_evaluation(db: Session) -> EvaluationRun:
    cases = load_cases()
    run = EvaluationRun(status="running", total_cases=len(cases))
    db.add(run)
    db.commit()
    db.refresh(run)

    passed = failed = warnings = 0
    for case in cases:
        check_fn = _CHECKS.get(case.get("check_type"))
        if check_fn is None:
            status, reason = "warning", f"no checker registered for check_type '{case.get('check_type')}'"
        else:
            try:
                status, reason = check_fn(db, case)
            except Exception:  # noqa: BLE001 — one bad case must not abort the whole run
                logger.warning("Evaluation case '%s' raised an error", case["id"], exc_info=True)
                status, reason = "fail", "This case couldn't be evaluated due to an internal error."

        if status == "pass":
            passed += 1
        elif status == "warning":
            warnings += 1
        else:
            failed += 1

        db.add(EvaluationResult(run_id=run.id, case_id=case["id"], status=status, reason=reason, observed_json={"category": case["category"]}))

    run.passed_cases = passed
    run.failed_cases = failed
    run.warnings = warnings
    run.status = "completed"
    run.result_summary = "red" if failed > 0 else ("yellow" if warnings > 0 else "green")
    from app.models import _now

    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def list_runs(db: Session, limit: int = 20) -> list[EvaluationRun]:
    return db.query(EvaluationRun).order_by(EvaluationRun.started_at.desc()).limit(limit).all()


def get_run(db: Session, run_id: str) -> EvaluationRun | None:
    return db.get(EvaluationRun, run_id)
