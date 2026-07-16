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
