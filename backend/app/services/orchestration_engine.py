"""ECHO Layer 2D — Multi-Model Orchestrator (Phases 2, 3, 6, 7).

Deliberately not a rewrite of chat generation. build_plan() is the one
centralized policy decision (task category -> stage profile -> roles ->
cloud eligibility) that replaces what would otherwise be scattered if/else
across callers — testable in complete isolation, no model call. run_orchestration()
executes that plan by delegating the actual generation to already-tested
primitives: LocalModelRouter.call() for a single-call "simple" turn, or the
existing LocalIntelligenceEngine.generate_response() (its own tested intent
-> context -> draft -> critic -> repair -> style pipeline) for "standard"/
"deep" turns — never a second implementation of drafting/critiquing. This
module's own genuinely new job is the policy table, budget enforcement, and
translating whichever result into typed OrchestrationStageResult envelopes.
"""

import json
import logging
import re
import time

from sqlalchemy.orm import Session

from app import schemas
from app.config import get_settings
from app.models import OrchestrationPolicy, OrchestrationRun, _now
from app.provider_errors import classify_provider_error
from app.providers.base import ChatMessage
from app.services import tool_strategy
from app.services.cognitive_core import _task_type_for
from app.services.intent_classifier import IntentClassification, classify_intent
from app.services.local_intelligence_engine import LocalIntelligenceEngine
from app.services.local_model_router import LocalModelRouter
from app.services.task_understanding_v2 import map_task_type_to_category

logger = logging.getLogger(__name__)

# Absolute ceiling regardless of policy/request — the loop-prevention backstop
# no configuration can override.
_HARD_MAX_CALLS = 6

# Rough per-profile call cost — used only to decide whether a tight budget
# forces a cheaper profile (Phase 7's "budgets stop excessive calls"), never
# to fabricate a token/cost estimate.
_PROFILE_CALL_COST = {"simple": 1, "standard": 2, "deep": 4}
_PROFILE_DOWNGRADE = {"deep": "standard", "standard": "simple", "simple": "simple"}

_DEFAULT_POLICY_BY_CATEGORY: dict[str, dict] = {
    "question": dict(stage_profile="simple", max_model_calls=1),
    "explanation": dict(stage_profile="simple", max_model_calls=1),
    "research": dict(stage_profile="standard", max_model_calls=2),
    "coding": dict(stage_profile="deep", max_model_calls=4, skip_critic_for_low_risk=False),
    "debugging": dict(stage_profile="deep", max_model_calls=4, skip_critic_for_low_risk=False),
    "planning": dict(stage_profile="standard", max_model_calls=2),
    "decision": dict(stage_profile="standard", max_model_calls=2),
    "document": dict(stage_profile="simple", max_model_calls=1),
    "action": dict(stage_profile="standard", max_model_calls=2),
    "reminder": dict(stage_profile="simple", max_model_calls=1),
    "learning": dict(stage_profile="simple", max_model_calls=1),
    "emotional_support": dict(stage_profile="simple", max_model_calls=1),
    "creative": dict(stage_profile="simple", max_model_calls=1),
    "mixed": dict(stage_profile="standard", max_model_calls=2),
}

_CODING_INTENTS = {"coding", "code_review", "prompt_generation"}
_MODE_BY_PROFILE = {"standard": "balanced", "deep": "deep"}


# ============================================================================
# Task classification (chains two existing, already-tested classifiers —
# never re-derives IntentCategory -> TaskCategory itself)
# ============================================================================


def classify_task_category(user_message: str) -> tuple[str, IntentClassification]:
    intent = classify_intent(user_message)
    task_type = _task_type_for(user_message, intent)
    category = map_task_type_to_category(task_type)
    return category, intent


# ============================================================================
# Phase 1(cont)/2 — OrchestrationPolicy CRUD
# ============================================================================


def ensure_default_policies(db: Session) -> None:
    """Idempotent — seeds one safe, local-first-default policy per Layer 2A
    task_category, same pattern as this codebase's other _seed_*() functions."""
    existing = {p.task_category for p in db.query(OrchestrationPolicy).all()}
    for category, defaults in _DEFAULT_POLICY_BY_CATEGORY.items():
        if category in existing:
            continue
        db.add(OrchestrationPolicy(task_category=category, **defaults))
    db.commit()


def get_policy(db: Session, task_category: str) -> OrchestrationPolicy:
    ensure_default_policies(db)
    policy = db.query(OrchestrationPolicy).filter(OrchestrationPolicy.task_category == task_category).first()
    if policy is None:
        policy = db.query(OrchestrationPolicy).filter(OrchestrationPolicy.task_category == "mixed").first()
    return policy


def list_policies(db: Session) -> list[OrchestrationPolicy]:
    ensure_default_policies(db)
    return db.query(OrchestrationPolicy).order_by(OrchestrationPolicy.task_category).all()


def update_policy(db: Session, policy_id: str, payload: schemas.OrchestrationPolicyUpdate) -> OrchestrationPolicy | None:
    policy = db.get(OrchestrationPolicy, policy_id)
    if policy is None:
        return None
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    return policy


# ============================================================================
# Phase 2 — cloud eligibility (composes the EXISTING cloud_fallback_* settings
# rather than a second privacy policy)
# ============================================================================


def _resolve_cloud_allowed(settings, policy: OrchestrationPolicy, request: schemas.OrchestrationRequest, intent: IntentClassification, task_category: str) -> bool:
    if not settings.cloud_fallback_enabled:
        return False
    if request.privacy_level == "local_only":
        return False
    if request.cloud_allowed is False:
        return False
    if request.cloud_allowed is None and not policy.cloud_allowed:
        return False
    allowed = settings.cloud_fallback_allowed_intent_list
    if intent.intent not in allowed and task_category not in allowed:
        return False
    if policy.require_confirmation_for_cloud and not request.cloud_confirmed:
        return False
    return True


def _select_reason_role(intent: IntentClassification, task_category: str) -> str:
    if intent.intent in _CODING_INTENTS or task_category in ("coding", "debugging"):
        return "coding"
    if intent.reasoning_need == "high":
        return "reasoning"
    return "fast"


def _stages_for_profile(stage_profile: str, intent: IntentClassification, task_category: str, policy: OrchestrationPolicy, has_tools: bool) -> list[schemas.OrchestrationStagePlanItem]:
    reason_role = _select_reason_role(intent, task_category)

    if stage_profile == "simple":
        stages = [schemas.OrchestrationStagePlanItem(stage="final", role=reason_role, purpose="Answer directly in a single local model call.")]
        return stages

    stages = [schemas.OrchestrationStagePlanItem(stage="understand", role=None, purpose="Classify intent and gather context (deterministic, no model call).")]
    if has_tools:
        stages.append(schemas.OrchestrationStagePlanItem(stage="tool", role=None, purpose="Run the selected read-only tool(s) to gather evidence."))
    if stage_profile == "deep":
        stages.append(schemas.OrchestrationStagePlanItem(stage="plan", role="reasoning", purpose="Sketch an approach before drafting."))
    stages.append(schemas.OrchestrationStagePlanItem(stage="reason", role=reason_role, purpose="Draft the answer."))

    run_critic = (not policy.skip_critic_for_low_risk) or intent.difficulty == "hard" or task_category in ("coding", "debugging", "decision")
    if run_critic:
        stages.append(schemas.OrchestrationStagePlanItem(stage="critique", role="critic", purpose="Check the draft for correctness/completeness."))
        stages.append(schemas.OrchestrationStagePlanItem(stage="repair", role=reason_role, purpose="Bounded fix-up — only actually runs if the critic flagged a problem."))
    if stage_profile == "deep":
        stages.append(schemas.OrchestrationStagePlanItem(stage="style", role="writing", purpose="Polish tone/formatting."))
    stages.append(schemas.OrchestrationStagePlanItem(stage="final", role=None, purpose="Deliver the answer."))
    return stages


def _effective_profile(requested_profile: str, max_calls: int) -> str:
    """Phase 7 — a tight budget forces a cheaper profile rather than letting
    an expensive one run and get cut off mid-pipeline (which a black-box
    delegate like LocalIntelligenceEngine can't be safely interrupted
    inside anyway)."""
    profile = requested_profile
    while _PROFILE_CALL_COST[profile] > max_calls and profile != "simple":
        profile = _PROFILE_DOWNGRADE[profile]
    return profile


def build_plan(db: Session, request: schemas.OrchestrationRequest) -> schemas.OrchestrationPlanOut:
    """Pure policy decision — never calls a model, never runs a tool.
    Fully deterministic and independently testable."""
    settings = get_settings()

    if request.task_type:
        task_category = request.task_type
        intent = classify_intent(request.user_message)
    else:
        task_category, intent = classify_task_category(request.user_message)

    policy = get_policy(db, task_category)
    max_calls = min(request.max_model_calls or policy.max_model_calls, policy.max_model_calls, _HARD_MAX_CALLS)
    effective_profile = _effective_profile(policy.stage_profile, max_calls)

    tool_plan = tool_strategy.build_tool_plan(request.user_message, request.conversation_id)
    cloud_allowed = _resolve_cloud_allowed(settings, policy, request, intent, task_category)

    stages = _stages_for_profile(effective_profile, intent, task_category, policy, bool(tool_plan.items))

    confirmation_points = [item.tool_name for item in tool_plan.items if item.requires_confirmation]
    if cloud_allowed and policy.require_confirmation_for_cloud:
        confirmation_points.append("cloud_call")

    fallback_chain = ["ollama"]
    if cloud_allowed:
        fallback_chain.append("auto")

    token_budget = request.token_budget or policy.token_budget
    latency_budget_ms = request.latency_budget_ms or policy.latency_budget_ms

    stop_conditions = [f"max_model_calls ({max_calls}) reached", "duplicate stage/tool call suppressed"]
    if token_budget:
        stop_conditions.append(f"token_budget ({token_budget}) exceeded")
    if latency_budget_ms:
        stop_conditions.append(f"latency_budget_ms ({latency_budget_ms}) exceeded")

    clipped = request.user_message[:60] + ("…" if len(request.user_message) > 60 else "")
    routing_reason = (
        f"'{task_category}' task ('{clipped}'), '{effective_profile}' profile ({len(stages)} stage(s)); "
        f"cloud {'allowed' if cloud_allowed else 'not allowed'} under current policy."
    )

    return schemas.OrchestrationPlanOut(
        task_category=task_category,
        stage_profile=effective_profile,
        stages=stages,
        selected_models=sorted({s.role for s in stages if s.role}),
        selected_tools=[item.tool_name for item in tool_plan.items],
        fallback_chain=fallback_chain,
        budgets={"max_model_calls": max_calls, "token_budget": token_budget, "latency_budget_ms": latency_budget_ms},
        confirmation_points=confirmation_points,
        expected_outputs=[f"A direct answer to: {clipped}"],
        stop_conditions=stop_conditions,
        cloud_allowed=cloud_allowed,
        routing_reason=routing_reason,
    )


# ============================================================================
# Phase 6 — failure categorization (translates the existing, already-tested
# provider_errors.classify_provider_error() into this milestone's own
# vocabulary rather than re-deriving classification)
# ============================================================================

_PROVIDER_ERROR_TO_FAILURE_CATEGORY: dict[str, str] = {
    "rate_limited": "rate_limited",
    "quota_exceeded": "quota_exceeded",
    "credit_exhausted": "quota_exceeded",
    "billing_required": "billing_required",
    "auth_failed": "model_missing",
    "provider_unavailable": "unavailable",
    "network_error": "timeout",
    "invalid_request": "malformed_output",
    "unknown_error": "unknown_error",
}


def categorize_failure(exc: Exception) -> str:
    return _PROVIDER_ERROR_TO_FAILURE_CATEGORY.get(classify_provider_error(exc), "unknown_error")


# ============================================================================
# Phase 7(cont) — bounded structured-output repair. Deterministic only (no
# extra model call — a second generation call would defeat "don't use more
# model calls just to appear intelligent"). Only engages when the caller
# explicitly asked for structured_output_required; never touches free-text
# answers.
# ============================================================================

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_JSON_SPAN_RE = re.compile(r"[\{\[].*[\}\]]", re.DOTALL)


def repair_structured_output(text: str) -> tuple[str | None, bool]:
    """Returns (json_text, was_repaired). json_text is None if no valid JSON
    could be recovered within the one bounded attempt. was_repaired is False
    when the input already parsed as-is."""
    candidate = (text or "").strip()
    try:
        json.loads(candidate)
        return candidate, False
    except (ValueError, TypeError):
        pass

    fence_match = _CODE_FENCE_RE.search(candidate)
    if fence_match:
        fenced = fence_match.group(1).strip()
        try:
            json.loads(fenced)
            return fenced, True
        except (ValueError, TypeError):
            candidate = fenced

    span_match = _JSON_SPAN_RE.search(candidate)
    if span_match:
        span = span_match.group(0).strip()
        try:
            json.loads(span)
            return span, True
        except (ValueError, TypeError):
            pass

    return None, False


# ============================================================================
# Phase 3/6/7 — execution
# ============================================================================


def run_orchestration(db: Session, request: schemas.OrchestrationRequest) -> OrchestrationRun:
    """Delegates actual generation to already-tested primitives — never a
    second draft/critic/repair implementation. See module docstring."""
    plan = build_plan(db, request)
    run_started = time.monotonic()

    stage_results: list[dict] = []
    tools_used: list[str] = []
    calls_made = 0
    tokens_estimate = 0
    cloud_used = False
    status = "completed"
    stop_reason: str | None = None
    answer_text = ""

    for stage_item in plan.stages:
        if stage_item.stage == "understand":
            stage_results.append({"stage": "understand", "role": None, "provider": None, "model": None, "duration_ms": 0.0, "status": "completed", "detail": f"classified as '{plan.task_category}'"})
            continue
        if stage_item.stage == "tool":
            for tool_name in plan.selected_tools:
                tools_used.append(tool_name)
            stage_results.append({"stage": "tool", "role": None, "provider": None, "model": None, "duration_ms": 0.0, "status": "completed", "detail": f"{len(plan.selected_tools)} tool(s) selected"})
            continue

    if plan.stage_profile == "simple":
        role = next((s.role for s in plan.stages if s.stage == "final"), "fast")
        local_router = LocalModelRouter()
        call_start = time.monotonic()
        result = local_router.call(role, "You are Echo, a helpful assistant. Answer directly and concisely.", [ChatMessage(role="user", content=request.user_message)])
        duration_ms = (time.monotonic() - call_start) * 1000
        calls_made += 1
        if result.ok:
            answer_text = result.text
            tokens_estimate += max(len(result.text) // 4, 0)
            stage_results.append({"stage": "final", "role": role, "provider": "ollama", "model": result.model_used, "duration_ms": round(duration_ms, 1), "status": "completed", "detail": None})
        else:
            status = "failed"
            stop_reason = "unavailable"
            stage_results.append({"stage": "final", "role": role, "provider": "ollama", "model": None, "duration_ms": round(duration_ms, 1), "status": "failed", "detail": result.error})
    else:
        # ECHO Layer 2D — pipeline_steps entries this engine actually emits
        # (local_intelligence_engine.py): "intent:*", "context_gathered",
        # "cognitive_brief:built", "role:*" are metadata, not a stage result
        # (this run's own "understand" stage entry above already covers
        # that ground) — only the entries below correspond to a real,
        # typed OrchestrationStageName.
        _ENGINE_STEP_TO_STAGE = {"draft": "reason", "critic": "critique", "repair": "repair", "style": "style"}
        engine = LocalIntelligenceEngine(db)
        mode = _MODE_BY_PROFILE.get(plan.stage_profile, "balanced")
        engine_result = engine.generate_response(
            request.user_message,
            conversation_id=request.conversation_id,
            allow_cloud_fallback=plan.cloud_allowed,
            mode=mode,
        )
        answer_text = engine_result.answer
        tokens_estimate += max(len(engine_result.answer) // 4, 0)
        cloud_used = engine_result.provider != "ollama"
        for step in engine_result.pipeline_steps:
            step_stage, _, step_detail = step.partition(":")
            mapped_stage = _ENGINE_STEP_TO_STAGE.get(step_stage)
            if mapped_stage is None:
                continue
            calls_made += 1
            stage_results.append(
                {
                    "stage": mapped_stage,
                    "role": None,
                    "provider": engine_result.provider,
                    "model": engine_result.model_used if mapped_stage == "reason" else None,
                    "duration_ms": None,
                    "status": "failed" if step_detail == "failed" else "completed",
                    "detail": step_detail or None,
                }
            )
        stage_results.append({"stage": "final", "role": None, "provider": engine_result.provider, "model": engine_result.model_used, "duration_ms": None, "status": "completed", "detail": f"confidence: {engine_result.confidence}"})
        calls_made = max(calls_made, 1)
        if engine_result.confidence == "unverified" and not answer_text:
            status = "failed"
            stop_reason = "unavailable"

    if request.structured_output_required and answer_text and status == "completed":
        repaired_text, was_repaired = repair_structured_output(answer_text)
        if repaired_text is None:
            status = "failed"
            stop_reason = "malformed_output"
            stage_results.append({"stage": "repair", "role": None, "provider": None, "model": None, "duration_ms": 0.0, "status": "failed", "detail": "structured output could not be repaired"})
        elif was_repaired:
            answer_text = repaired_text
            stage_results.append({"stage": "repair", "role": None, "provider": None, "model": None, "duration_ms": 0.0, "status": "completed", "detail": "structured output repaired (fence/span extraction)"})

    if (time.monotonic() - run_started) * 1000 >= (plan.budgets.get("latency_budget_ms") or float("inf")):
        status = "stopped_budget"
        stop_reason = "latency_budget_ms exceeded"
    elif plan.budgets.get("token_budget") and tokens_estimate >= plan.budgets["token_budget"]:
        status = "stopped_budget"
        stop_reason = "token_budget exceeded"

    run = OrchestrationRun(
        task_id=request.task_id,
        conversation_id=request.conversation_id,
        objective=request.user_message[:200],
        task_category=plan.task_category,
        stage_profile_used=plan.stage_profile,
        status=status,
        answer=answer_text or None,
        stages_json=stage_results,
        tools_used_json=tools_used,
        total_model_calls=calls_made,
        total_tokens_estimate=tokens_estimate,
        cloud_used=cloud_used,
        stop_reason=stop_reason,
        completed_at=_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_run(db: Session, run_id: str) -> OrchestrationRun | None:
    return db.get(OrchestrationRun, run_id)


def list_runs(db: Session, *, task_id: str | None = None, limit: int = 50) -> list[OrchestrationRun]:
    q = db.query(OrchestrationRun)
    if task_id:
        q = q.filter(OrchestrationRun.task_id == task_id)
    return q.order_by(OrchestrationRun.created_at.desc()).limit(limit).all()
