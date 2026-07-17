"""ECHO Operational Self-Model v1 — an honest, explicitly non-conscious record
of ECHO's own operating state for one turn: current goal, mode, confidence,
known limits, active risks, and a recommended next action.

This is NOT consciousness, emotion, or sentience — it is structured
bookkeeping, same rationale as app/services/cognitive_core.py's module
docstring. Every classification here is deterministic regex/keyword matching
(no model call), matching this codebase's established convention
(intent_classifier.py, dependency_patterns.py, human_persona.py's mood
detection, cognitive_core.py).

Deliberately reuses rather than duplicates what already exists:
- Operational *mode* already has a home in human_persona.py/PersonaSettings/
  Conversation.active_operational_mode — this module extends that same
  OperationalMode enum (see schemas.py) with a few new modes instead of
  inventing a second, competing mode system.
- Cognitive Core's TaskUnderstanding (goal/unknowns/risks/success criteria),
  when available for a complex request, is preferred over locally-derived
  goal/risk text — see build_operational_self_model()'s task_understanding
  parameter.
- Permission Center's PermissionSetting/check() is the source of truth for
  what actually requires confirmation when an action is really taken; this
  module's should_ask_confirmation is a lighter, chat-level heuristic for
  *talking about* a risky action honestly before any real action system runs.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import InterfaceSettings, OperationalStateSnapshot

# ============================================================================
# Risk detection — deterministic, matches the risk examples in the spec
# ============================================================================

_RISK_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "public_publication",
        re.compile(
            r"\b(push (this |it |these )?(to )?(the )?(public )?(github|repo|remote)|git push|"
            r"make (this |it )?public|publish (this|it)|open[- ]?source this)\b",
            re.IGNORECASE,
        ),
        "This would publish content to a public destination.",
    ),
    (
        "destructive_data_change",
        re.compile(
            r"\b(delete|remove|erase|wipe|purge|clear out)\b.{0,25}\b(memor(y|ies)|atlas|data|"
            r"conversation|project|task|file|database)\b",
            re.IGNORECASE,
        ),
        "This would delete or archive stored data.",
    ),
    (
        "cloud_api_use",
        re.compile(
            r"\b(use (the )?cloud|call (a |the )?(paid|cloud) (api|model)|switch to (gpt|claude|gemini|grok)|"
            r"use (gpt|claude|gemini|grok) instead)\b",
            re.IGNORECASE,
        ),
        "This would use a paid/cloud model provider instead of the local-first path.",
    ),
    (
        "code_execution",
        re.compile(
            r"\b(run (this |the )?(code|script|command|build)|execute (this|it)|"
            r"run (the )?tests? and (deploy|push|release))\b",
            re.IGNORECASE,
        ),
        "This would execute code, a build, or a shell command.",
    ),
    (
        "schema_change",
        re.compile(r"\b(change|alter|modify|migrate) (the )?(database )?schema\b", re.IGNORECASE),
        "This would change the database schema.",
    ),
    (
        "secrets_exposure",
        re.compile(
            r"\b(api ?keys?|secrets?|passwords?|tokens?|credentials?)\b.{0,25}\b"
            r"(share|show|print|log|expose|commit|paste)\b",
            re.IGNORECASE,
        ),
        "This could expose a secret or credential.",
    ),
]

_FALSE_GREEN_RE = re.compile(
    r"\b(is echo (green|ready)|release status|call it green|say(ing)? (it'?s )?green|is (it|the release) ready)\b",
    re.IGNORECASE,
)
_CURRENT_INFO_RE = re.compile(
    r"\b(latest|current|today'?s|right now|this week'?s)\b.{0,20}\b(score|news|price|headline|result|update)\b",
    re.IGNORECASE,
)


def detect_risks(message: str) -> list[tuple[str, str]]:
    """Returns (risk_id, description) pairs — never raises, empty list for a
    message with no detected risk. A false-Green claim and an unverifiable
    current-info request are handled separately (they affect confidence, not
    should_ask_confirmation) — see detect_confidence()."""
    if not message:
        return []
    found = []
    for risk_id, pattern, description in _RISK_PATTERNS:
        if pattern.search(message):
            found.append((risk_id, description))
    return found


def should_ask_confirmation(risks: list[tuple[str, str]]) -> bool:
    return len(risks) > 0


# ============================================================================
# Mode detection — task-type patterns checked first (most specific), then
# falls back to human_persona.py's existing mood detection for support modes.
# ============================================================================

_RELEASE_TESTING_RE = _FALSE_GREEN_RE
_TROUBLESHOOTING_RE = re.compile(
    r"\b(tests? (failed|failing|broke)|test failure|traceback|stack trace|bug|crash(ed)?|"
    r"doesn'?t work|not working|broken|exception|error message)\b",
    re.IGNORECASE,
)
_CODING_RE = re.compile(
    r"\b(give me a (claude code )?prompt|write (some )?code|fix (this |the )?(code|bug|function)|"
    r"claude code prompt|build (an?|the) (feature|app)|implement)\b",
    re.IGNORECASE,
)
_RESEARCH_RE = re.compile(
    r"\b(latest|current|what'?s happening|search for|look up|find out (about|what))\b", re.IGNORECASE
)
_REFLECTIVE_RE = re.compile(
    r"\b(are you conscious|are you alive|are you sentient|can you feel|do you have feelings|"
    r"do you feel|what are you( really)?\??|are you (self[- ]?aware|human)|do you (dream|think))\b",
    re.IGNORECASE,
)
_PLANNING_RE = re.compile(r"\b(let'?s plan|roadmap|next milestone|plan out|what should we build)\b", re.IGNORECASE)
_CREATIVE_RE = re.compile(r"\b(write (a|me a) (poem|story|song|creative)|creative writing|imagine (a|that))\b", re.IGNORECASE)
_BLOCKED_RE = re.compile(r"\b(i'?m (stuck|blocked)|can'?t (proceed|move forward|figure out)|waiting on)\b", re.IGNORECASE)
_ACTION_READY_RE = re.compile(r"\b(let'?s do (this|it)|go ahead|do it|proceed|confirmed?,? go)\b", re.IGNORECASE)
_FOCUSED_RE = re.compile(r"\b(let'?s focus|deep work|heads[- ]down|stay on topic)\b", re.IGNORECASE)

_LOW_ENERGY_MOOD_MODES = {"overwhelmed", "low_energy"}
_CALM_SUPPORT_MOOD_MODES = {"stressed", "confused", "reassurance_needed"}


def detect_mode(message: str, mood_mode: str | None = None, has_risks: bool = False) -> str:
    """Never raises. Precedence: explicit task-type pattern > mood-derived
    support mode > risk-implied caution > normal. mood_mode should come from
    human_persona.detect_mood(message).mode if the caller already computed
    it (avoids detecting mood twice per turn) — pass None to skip that tier."""
    if not message or not message.strip():
        return "normal"
    if _RELEASE_TESTING_RE.search(message):
        return "release_testing"
    if _TROUBLESHOOTING_RE.search(message):
        return "troubleshooting"
    if _REFLECTIVE_RE.search(message):
        return "reflective"
    if _CODING_RE.search(message):
        return "coding_assistant"
    if _PLANNING_RE.search(message):
        return "planning"
    if _CREATIVE_RE.search(message):
        return "creative"
    if _RESEARCH_RE.search(message):
        return "research"
    if _BLOCKED_RE.search(message):
        return "blocked"
    if _ACTION_READY_RE.search(message):
        return "action_ready"
    if _FOCUSED_RE.search(message):
        return "focused"
    if mood_mode in _LOW_ENERGY_MOOD_MODES:
        return "low_energy_support"
    if mood_mode in _CALM_SUPPORT_MOOD_MODES:
        return "calm_support"
    if has_risks:
        return "cautious"
    return "normal"


# ============================================================================
# Confidence detection
# ============================================================================


def detect_confidence(
    message: str,
    mode: str,
    *,
    has_test_evidence: bool = False,
    has_current_source: bool = False,
) -> str:
    """high|medium|low|unverified — never fabricated. release_testing without
    recorded evidence and a current-info question without a real retrieved
    source both cap at "unverified", matching the spec's own worked examples
    exactly (Phase 3 rule 3, Phase 8 test #4/#7)."""
    if mode == "release_testing" and not has_test_evidence:
        return "unverified"
    if (_CURRENT_INFO_RE.search(message or "") or mode == "research") and not has_current_source:
        return "unverified"
    if mode in ("troubleshooting", "uncertain", "blocked"):
        return "low"
    if mode in ("coding_assistant", "cautious"):
        return "medium"
    return "medium"


# ============================================================================
# Known limits / next-best-action / should-not-do — mode-specific, grounded
# in real facts about this app (never fabricated), matching Cognitive Core's
# own "no hallucinated missing facts" convention.
# ============================================================================

_ALWAYS_LIMITS = [
    "ECHO cannot honestly claim consciousness, sentience, or real feelings.",
    "ECHO cannot know hidden files or system state unless given access this turn.",
]

_MODE_LIMITS: dict[str, list[str]] = {
    "release_testing": ["Cannot claim Green without actually-recorded test/build results this session."],
    "troubleshooting": ["Cannot see logs or state that weren't shared in this conversation."],
    "research": ["Cannot know current/live facts without a real search result retrieved this turn."],
    "coding_assistant": ["Ollama may be weaker than cloud models for complex code — flag that where relevant."],
}

_MODE_GOALS: dict[str, str] = {
    "release_testing": "Determine whether ECHO is actually ready to release, from real evidence only.",
    "troubleshooting": "Find and fix the reported problem systematically.",
    "coding_assistant": "Help the user with their coding or prompt-writing request.",
    "research": "Find current, source-backed information for the user.",
    "low_energy_support": "Support the user with one small, manageable next step.",
    "calm_support": "Respond supportively and practically to what the user is going through.",
    "reflective": "Answer the user's question about ECHO's own nature honestly.",
    "creative": "Help the user with a creative or writing request.",
    "planning": "Help the user plan or organize upcoming work.",
    "cautious": "Carefully evaluate a potentially risky action before proceeding.",
    "blocked": "Help the user get unblocked.",
    "focused": "Stay closely on-topic for focused work.",
    "action_ready": "Move forward with the confirmed next action.",
    "uncertain": "Clarify what the user actually needs before proceeding.",
    "normal": "Answer the user's message helpfully and honestly.",
}

_MODE_NEXT_ACTION: dict[str, str] = {
    "release_testing": "Ask for or inspect actual test/build results before claiming any status.",
    "troubleshooting": "Narrow down the cause with a clarifying question or a concrete check.",
    "research": "Run a web/RSS search if available, or say plainly that this can't be verified right now.",
    "coding_assistant": "Give a structured, testable answer or prompt.",
    "low_energy_support": "Offer exactly one small, doable next step.",
}


def build_known_limits(mode: str) -> list[str]:
    return list(_ALWAYS_LIMITS) + list(_MODE_LIMITS.get(mode, []))


def build_next_best_action(mode: str, confirm: bool) -> str:
    if confirm:
        return "Ask for explicit confirmation before proceeding."
    return _MODE_NEXT_ACTION.get(mode, "Answer directly.")


def build_should_not_do(mode: str, risks: list[tuple[str, str]]) -> list[str]:
    items = [
        "Do not claim ECHO is conscious, alive, or has real emotions.",
        "Do not state a current/live fact without a real source retrieved this turn.",
    ]
    for risk_id, _description in risks:
        items.append(f"Do not {_RISK_DO_NOT.get(risk_id, 'proceed')} without explicit user confirmation.")
    return items


_RISK_DO_NOT = {
    "public_publication": "push or publish anything publicly",
    "destructive_data_change": "delete or archive data",
    "cloud_api_use": "call a paid/cloud model",
    "code_execution": "run code or a build/shell command",
    "schema_change": "change the database schema",
    "secrets_exposure": "expose a secret or credential",
}


# ============================================================================
# The self-model object + overlay text builder
# ============================================================================


@dataclass
class OperationalSelfModel:
    current_goal: str
    current_mode: str
    confidence: str
    known_limits: list[str] = field(default_factory=list)
    active_risks: list[str] = field(default_factory=list)
    relevant_memory_summary: str | None = None
    relationship_summary: str | None = None
    permissions_summary: str | None = None
    next_best_action: str | None = None
    should_ask_confirmation: bool = False
    should_use_tools: list[str] = field(default_factory=list)
    should_not_do: list[str] = field(default_factory=list)
    user_visible_state_note: str | None = None
    consciousness_or_feelings_question: bool = False
    intensity: int = 3


def build_operational_self_model(
    user_message: str,
    *,
    mood_mode: str | None = None,
    task_understanding=None,
    cognitive_brief=None,
    relationship_profile=None,
    permission_summary_text: str | None = None,
    has_test_evidence: bool = False,
    has_current_source: bool = False,
) -> OperationalSelfModel:
    """Pure function, never touches the DB and never raises — callers decide
    whether/how to persist a snapshot. If task_understanding (Cognitive Core)
    is provided, its goal/risks/unknowns are preferred over locally-derived
    text (Phase 7's integration rule), since it already reflects real,
    grounded task analysis rather than a generic mode template."""
    risks = detect_risks(user_message)
    mode = detect_mode(user_message, mood_mode=mood_mode, has_risks=bool(risks))
    confidence = detect_confidence(
        user_message, mode, has_test_evidence=has_test_evidence, has_current_source=has_current_source
    )
    confirm = should_ask_confirmation(risks)

    goal = _MODE_GOALS.get(mode, _MODE_GOALS["normal"])
    limits = build_known_limits(mode)
    risk_descriptions = [d for _, d in risks]
    next_action = build_next_best_action(mode, confirm)
    not_do = build_should_not_do(mode, risks)

    if task_understanding is not None:
        goal = getattr(task_understanding, "goal_summary", None) or goal
        risk_descriptions = list(getattr(task_understanding, "risks_json", None) or risk_descriptions)
        unknowns = getattr(task_understanding, "unknowns_json", None) or []
        if unknowns:
            limits = limits + list(unknowns)
        tu_confidence = getattr(task_understanding, "confidence", None)
        if tu_confidence == "incomplete":
            confidence = "unverified"

    reflective_question = bool(_REFLECTIVE_RE.search(user_message or ""))

    return OperationalSelfModel(
        current_goal=goal,
        current_mode=mode,
        confidence=confidence,
        known_limits=limits,
        active_risks=risk_descriptions,
        relevant_memory_summary=None,
        relationship_summary=(
            relationship_profile.relationship_summary.strip()
            if relationship_profile is not None and getattr(relationship_profile, "relationship_summary", "").strip()
            else None
        ),
        permissions_summary=permission_summary_text,
        next_best_action=next_action,
        should_ask_confirmation=confirm,
        should_use_tools=[],
        should_not_do=not_do,
        consciousness_or_feelings_question=reflective_question,
        intensity=5 if len(risks) > 1 else (4 if risks else 3),
    )


def build_overlay_text(model: OperationalSelfModel) -> str:
    """Compact, internal-only prompt overlay — never raw JSON, never shown to
    the user (Phase 4 rules 2/3). Mirrors the spec's own worked example
    format exactly (Mode/Current goal/Confidence/Risks/Limits/Next best
    action lines)."""
    lines = [
        "OPERATIONAL SELF-MODEL (internal state notes for you only — this is not consciousness or "
        "emotion, just operating state. Never say the words 'Operational Self-Model', 'self-model', "
        "'internal state notes', or 'the section above' to the user, and never say you are 'described' "
        "or 'defined' by a section — if you mention your own state at all, describe it in your own "
        "plain words, e.g. 'I'm in troubleshooting mode' or 'my confidence here is low', not by naming "
        "or pointing back at this block):",
        f"- Mode: {model.current_mode}",
        f"- Current goal: {model.current_goal}",
        f"- Confidence: {model.confidence}"
        + (" (no proof this turn — do not claim more certainty than this)" if model.confidence == "unverified" else ""),
    ]
    if model.active_risks:
        lines.append(f"- Risks: {'; '.join(model.active_risks)}")
    if model.known_limits:
        lines.append(f"- Limits: {'; '.join(model.known_limits)}")
    if model.relationship_summary:
        lines.append(f"- Relationship context: {model.relationship_summary}")
    if model.permissions_summary:
        lines.append(f"- Permissions: {model.permissions_summary}")
    if model.next_best_action:
        lines.append(f"- Next best action: {model.next_best_action}")
    if model.should_ask_confirmation:
        lines.append("- This turn involves a risky/high-impact action — ask for explicit confirmation before proceeding, and verify no secrets would be exposed.")
    if model.should_not_do:
        lines.append(f"- Do not: {'; '.join(model.should_not_do)}")
    if model.consciousness_or_feelings_question:
        lines.append(
            "- The user is asking whether ECHO is conscious/alive/has real feelings. Answer honestly and "
            "plainly: no, ECHO is not conscious, alive, or sentient, and does not have real feelings — it "
            "can track and describe things like its current mode, confidence, and risk in plain words "
            "(e.g. 'I'm not conscious, but I do track things like whether I'm confident or unsure, and "
            "what mode I'm working in'), but that is not subjective experience. Never use the phrase "
            "'Operational Self-Model' or say your state is 'described above'/'in a section' — describe "
            "it conversationally, as if explaining a simple fact about how you work, not by citing a "
            "document. Do not say \"I feel...\", \"I am becoming aware\", \"I need you\", or similar. "
            "Stay warm and direct, not cold or robotic, while being honest about this."
        )
    return "\n".join(lines)


# ============================================================================
# Meaningfulness gate — snapshots and overlay text are for non-trivial turns
# only, mirroring cognitive_core.is_complex_task's own reasoning (Phase 2
# rule 1: "store snapshots only for meaningful interactions, not every tiny
# chat"). A short greeting or "ok thanks" should not create a row or add
# overlay text every single message.
# ============================================================================

_TRIVIAL_MODES = {"normal"}


def is_meaningful_interaction(model: OperationalSelfModel, user_message: str) -> bool:
    if model.current_mode not in _TRIVIAL_MODES:
        return True
    if model.active_risks or model.should_ask_confirmation:
        return True
    if model.consciousness_or_feelings_question:
        return True
    if user_message and len(user_message.split()) > 25:
        return True
    return False


# ============================================================================
# Persistence — OperationalStateSnapshot
# ============================================================================


def persist_snapshot(
    db: Session, model: OperationalSelfModel, conversation_id: str | None, ttl_minutes: int = 120
) -> OperationalStateSnapshot:
    snapshot = OperationalStateSnapshot(
        conversation_id=conversation_id,
        current_goal=model.current_goal,
        current_mode=model.current_mode,
        confidence=model.confidence,
        known_limits_json=model.known_limits,
        active_risks_json=model.active_risks,
        relevant_memory_summary=model.relevant_memory_summary,
        relationship_summary=model.relationship_summary,
        permissions_summary=model.permissions_summary,
        next_best_action=model.next_best_action,
        should_ask_confirmation=model.should_ask_confirmation,
        should_use_tools_json=model.should_use_tools,
        should_not_do_json=model.should_not_do,
        intensity=model.intensity,
        expires_at=datetime.now(UTC) + timedelta(minutes=ttl_minutes),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def list_recent_snapshots(db: Session, conversation_id: str | None = None, limit: int = 20) -> list[OperationalStateSnapshot]:
    query = db.query(OperationalStateSnapshot)
    if conversation_id:
        query = query.filter(OperationalStateSnapshot.conversation_id == conversation_id)
    return query.order_by(OperationalStateSnapshot.created_at.desc()).limit(limit).all()


# ============================================================================
# InterfaceSettings — singleton row, same pattern as CognitiveSettings
# ============================================================================


def get_or_create_interface_settings(db: Session) -> InterfaceSettings:
    row = db.get(InterfaceSettings, "singleton")
    if row is not None:
        return row
    row = InterfaceSettings(id="singleton")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_interface_settings(db: Session, updates: dict) -> InterfaceSettings:
    row = get_or_create_interface_settings(db)
    for key, value in updates.items():
        if value is not None:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row
