"""ECHO Layer 2A — Cognitive Core v2 / Task Understanding.

Additional deterministic passes over the same `TaskUnderstanding` row
`cognitive_core.py` already builds — this is not a second engine, it's
Phase 2-6 of the milestone layered on top of v1's existing goal/domain/
task_type/known/unknown/constraints/success-criteria machinery. No model
call anywhere, same "classification stays deterministic" convention as
cognitive_core.py, search_intent.py, intent_classifier.py, and
dependency_patterns.py elsewhere in this codebase.
"""

import re

# ============================================================================
# Phase 1 — legacy task_type -> Layer 2A task_category mapping (compatibility
# adapter, same pattern as Layer 1's atlas.legacy_type_to_category()).
# ============================================================================

_TASK_TYPE_TO_CATEGORY: dict[str, str] = {
    "ask_question": "question",
    "build_feature": "coding",
    "fix_bug": "debugging",
    "run_test": "coding",
    "plan_project": "planning",
    "research_topic": "research",
    "summarize_file": "document",
    "make_decision": "decision",
    "create_prompt": "document",
    "release_build": "action",
    "troubleshoot": "debugging",
    "study_learn": "learning",
    "personal_support": "emotional_support",
    "other": "mixed",
}


def map_task_type_to_category(task_type: str) -> str:
    return _TASK_TYPE_TO_CATEGORY.get(task_type, "mixed")


def compute_fingerprint(message: str) -> str:
    """A short, non-reversible fingerprint of the normalized request — used
    to detect whether a task has "materially changed" (Phase 7) without
    storing anything sensitive twice."""
    import hashlib

    normalized = re.sub(r"\s+", " ", message.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


# ============================================================================
# Phase 2 — Intent hierarchy and scope
# ============================================================================

# Quoted/example content that should never be mistaken for a user instruction
# — fenced code blocks, blockquote lines, explicit "example:"/"e.g." framing,
# and "the log/error says: ..." framing.
_FENCED_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>.*$", re.MULTILINE)
_QUOTED_SPAN_RE = re.compile(r'"[^"]{15,}"')
_EXAMPLE_PREFIX_RE = re.compile(r"\b(for example|e\.g\.?|such as|like this)\s*[:,]", re.IGNORECASE)
_LOG_QUOTE_RE = re.compile(r"\b(the (log|error|output|traceback|message) says?)\s*[:,]", re.IGNORECASE)

_SCOPE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("long_term_goal", re.compile(r"\b(my goal is to|eventually|long[- ]term|over the next (month|year))\b", re.IGNORECASE)),
    ("recurring_workflow", re.compile(r"\b(every time|each time|from now on,? (always|every)|whenever)\b", re.IGNORECASE)),
    ("project", re.compile(r"\b(for (this|the) project|project[- ]wide|across the (project|repo|codebase))\b", re.IGNORECASE)),
    ("conversation", re.compile(r"\b(as (i|we) (said|discussed)|earlier|before|continu(e|ing) (this|our))\b", re.IGNORECASE)),
]

# Segment separators used for multi-intent detection — deliberately narrow
# (strong coordination signals only, not every comma) to avoid splitting a
# single coherent request into false-positive fragments.
_INTENT_SEPARATOR_RE = re.compile(r"\band also\b|\balso,? please\b|;\s|\n\s*[-*]\s|\n\s*\d+[.)]\s", re.IGNORECASE)


def strip_quoted_content(message: str) -> str:
    """Removes fenced code blocks, blockquote lines, quoted spans, and
    example/log-quote framing — what's left is the instruction-bearing part
    of the message. Used so quoted content is never treated as a user
    command (rule: "Distinguish instructions from quoted content...")."""
    text = _FENCED_BLOCK_RE.sub(" ", message)
    text = _BLOCKQUOTE_LINE_RE.sub(" ", text)
    text = _QUOTED_SPAN_RE.sub(" ", text)
    text = _EXAMPLE_PREFIX_RE.sub("", text)
    text = _LOG_QUOTE_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def has_quoted_content(message: str) -> bool:
    return bool(
        _FENCED_BLOCK_RE.search(message)
        or _BLOCKQUOTE_LINE_RE.search(message)
        or _QUOTED_SPAN_RE.search(message)
        or _EXAMPLE_PREFIX_RE.search(message)
        or _LOG_QUOTE_RE.search(message)
    )


def detect_scope(message: str) -> str:
    for scope, pattern in _SCOPE_PATTERNS:
        if pattern.search(message):
            return scope
    return "current_turn"


def detect_multiple_intents(message: str) -> list[str]:
    """Returns each distinct request segment when the message plausibly
    contains more than one (e.g. "fix the bug and also write the docs for
    it") — a single-segment list for an ordinary single-intent message.
    Never flattens a genuinely multi-part request into one vague label."""
    instruction_text = strip_quoted_content(message)
    segments = [s.strip() for s in _INTENT_SEPARATOR_RE.split(instruction_text) if s.strip()]
    if len(segments) <= 1:
        return [instruction_text] if instruction_text else [message.strip()]
    return segments


def build_intent_hierarchy(message: str, task_type: str, task_category: str) -> dict:
    """literal_request / underlying_objective / requested_output /
    implied_constraints — kept as short strings/lists, never a full
    re-derivation of the whole message. This is the compact structure
    stored on TaskUnderstanding.intent_hierarchy_json."""
    instruction_text = strip_quoted_content(message)
    intents = detect_multiple_intents(message)

    # Requested output: what form the answer should take — information,
    # a plan, a file, a real action, or a scheduled future action.
    lowered = instruction_text.lower()
    if re.search(r"\b(remind me|schedule|set (a reminder|an alarm))\b", lowered):
        requested_output = "scheduled_action"
    elif re.search(r"\b(create|make|write|generate|build) (a |an )?(file|document|report)\b", lowered):
        requested_output = "file"
    elif task_category == "action" or re.search(r"\b(do it|go ahead and|please (send|delete|deploy|push))\b", lowered):
        requested_output = "real_action"
    elif re.search(r"\b(plan|steps|roadmap|outline)\b", lowered):
        requested_output = "plan"
    else:
        requested_output = "information"

    return {
        "literal_request": instruction_text[:500],
        "underlying_objective": None,  # filled in by the caller once a goal_summary exists
        "requested_output": requested_output,
        "implied_constraints": [],  # filled in by extract_explicit_constraints's inferred pass
        "multiple_intents": intents if len(intents) > 1 else [],
    }


# ============================================================================
# Phase 3 — Constraint and assumption engine
# ============================================================================

_EXPLICIT_CONSTRAINT_PATTERNS: dict[str, re.Pattern] = {
    "deadline": re.compile(r"\b(by (tomorrow|tonight|today|monday|tuesday|wednesday|thursday|friday|saturday|sunday|next week|end of (day|week)))\b", re.IGNORECASE),
    "budget": re.compile(r"\b(under \$?\d+|budget of \$?\d+|for (free|no cost)|zero[- ]cost)\b", re.IGNORECASE),
    "platform": re.compile(r"\bon (windows|android|linux|mac(os)?|ios)\b", re.IGNORECASE),
    "privacy": re.compile(r"\b(private(ly)?|confidential(ly)?|don'?t share|keep this (private|secret))\b", re.IGNORECASE),
    "local_only": re.compile(r"\blocal[- ]only\b|\bno cloud\b|\boffline only\b", re.IGNORECASE),
    "file_format": re.compile(r"\bas a (pdf|csv|json|markdown|docx|txt) file\b", re.IGNORECASE),
    "approval_required": re.compile(r"\b(need(s)? (my )?approval|ask (me )?before|confirm (with me )?before|don'?t do (this|it) without asking)\b", re.IGNORECASE),
}

_CONSTRAINT_LABELS: dict[str, str] = {
    "deadline": "Has a stated deadline",
    "budget": "Has a stated budget/cost constraint",
    "platform": "Must target a specific platform",
    "privacy": "Must be handled privately/confidentially",
    "local_only": "Must stay local-only, no cloud calls",
    "file_format": "Must be delivered in a specific file format",
    "approval_required": "Requires explicit approval before proceeding",
}

# Opposing constraint pairs — a simple, curated table (not exhaustive
# NLU), good enough to flag the clearest, highest-value contradictions.
_CONTRADICTORY_PAIRS: list[tuple[str, str]] = [
    ("local_only", "cloud_required"),
    ("budget", "no_budget_limit"),
]


def extract_explicit_constraints(message: str) -> list[dict]:
    """Returns [{"type": ..., "label": ..., "source": "explicit"}] for every
    matched pattern — deterministic, no inference. Distinct from
    cognitive_core.py's own _ALWAYS_CONSTRAINTS (structural, ECHO-wide
    rules), these are per-request constraints extracted from the user's
    actual words."""
    instruction_text = strip_quoted_content(message)
    found = []
    for ctype, pattern in _EXPLICIT_CONSTRAINT_PATTERNS.items():
        if pattern.search(instruction_text):
            found.append({"type": ctype, "label": _CONSTRAINT_LABELS[ctype], "source": "explicit"})
    return found


def infer_soft_constraints(task_type: str, domain: str, explicit_types: set[str]) -> list[dict]:
    """Only infers when there's real evidence — never converts a one-off
    preference into a universal rule. Each entry is labelled "inferred"
    with a stated basis, never presented as if the user said it."""
    inferred: list[dict] = []
    if domain == "Android" and "platform" not in explicit_types:
        inferred.append({
            "type": "platform", "label": "Likely targets Android (domain match)",
            "source": "inferred", "basis": "message mentions Android/APK/Capacitor", "confidence": "medium",
        })
    if task_type in ("release_build", "run_test") and "approval_required" not in explicit_types:
        inferred.append({
            "type": "evidence_required", "label": "Must not claim a result without actually running the check",
            "source": "inferred", "basis": "release/test-status tasks require real evidence per this repo's own rule", "confidence": "high",
        })
    return inferred


def detect_contradictory_constraints(constraints: list[dict]) -> list[str]:
    """Pairwise scan for known-opposite constraint types among the given
    list. Returns human-readable conflict summaries, never silently
    resolved — downstream planning must see this, not guess past it."""
    types_present = {c["type"] for c in constraints}
    conflicts = []
    for a, b in _CONTRADICTORY_PAIRS:
        if a in types_present and b in types_present:
            conflicts.append(f"Conflicting constraints: '{a}' and '{b}' cannot both hold.")
    return conflicts


# ============================================================================
# Phase 4 — Success criteria and acceptance tests
# ============================================================================

_ENGINEERING_TASK_TYPES = {"build_feature", "fix_bug", "run_test", "release_build", "troubleshoot"}
_RESEARCH_TASK_TYPES = {"research_topic"}
_ACTION_TASK_CATEGORIES = {"action", "reminder"}


def build_acceptance_tests(task_type: str, task_category: str) -> list[str]:
    if task_type in _ENGINEERING_TASK_TYPES:
        return ["Relevant backend tests pass", "Frontend build/typecheck passes (if frontend touched)", "A manual check confirms the actual behavior, not just the code"]
    if task_type in _RESEARCH_TASK_TYPES:
        return ["At least one real, current source was retrieved and cited", "The answer states its own uncertainty if no source could verify a claim"]
    if task_category in _ACTION_TASK_CATEGORIES:
        return ["Required permission was explicitly granted", "The action is reversible, or explicit confirmation was given for an irreversible one"]
    return ["The user's actual question/request is directly addressed"]


def build_failure_conditions(task_type: str, task_category: str) -> list[str]:
    if task_type in _ENGINEERING_TASK_TYPES:
        return ["A test that should pass fails", "The build breaks", "An existing feature regresses"]
    if task_type in _RESEARCH_TASK_TYPES:
        return ["A claim is stated as current fact without a real source", "A stale fact is presented as current"]
    if task_category in _ACTION_TASK_CATEGORIES:
        return ["The action runs without required permission", "An irreversible action runs without confirmation"]
    return ["The reply doesn't actually address what was asked"]


# ============================================================================
# Phase 5 — Missing knowledge and clarification policy
# ============================================================================

# Unknowns matching these patterns have a safe, statable default — never
# worth a clarification question.
_SAFELY_INFERABLE_PATTERNS = [
    re.compile(r"user'?s (current )?(level of familiarity|experience level)", re.IGNORECASE),
    re.compile(r"exact files?/modules? .* until the repo is inspected", re.IGNORECASE),
    re.compile(r"android sdk/gradle availability", re.IGNORECASE),
    re.compile(r"whether the rust/tauri toolchain", re.IGNORECASE),
]

# Unknowns that are always genuinely blocking (nothing safe can be assumed).
_ALWAYS_BLOCKING_PATTERNS = [
    re.compile(r"the user'?s actual priorities/constraints for this decision", re.IGNORECASE),
    re.compile(r"scope/deadline details not yet stated", re.IGNORECASE),
]


def classify_missing_information(unknowns: list[str], *, risk_level: str, consequence_level: str) -> list[dict]:
    """Tags each unknown as blocking/important/optional/safely_inferable.
    High risk/consequence pushes an otherwise-"important" unknown up to
    "blocking" (rule: "High-consequence ambiguity must not be guessed")."""
    high_stakes = risk_level in ("high", "critical") or consequence_level in ("high", "critical")
    tagged = []
    for item in unknowns:
        if any(p.search(item) for p in _SAFELY_INFERABLE_PATTERNS):
            tier = "safely_inferable"
        elif any(p.search(item) for p in _ALWAYS_BLOCKING_PATTERNS):
            tier = "blocking"
        elif high_stakes:
            tier = "blocking"
        else:
            tier = "important"
        tagged.append({"item": item, "tier": tier})
    return tagged


_MAX_CLARIFICATION_QUESTIONS = 2


def build_clarification_policy(missing_info: list[dict]) -> dict:
    """Returns {"needs_clarification", "questions", "blocking_items",
    "safe_assumptions_made"} — the compact "why ECHO needs clarification"
    view. Only blocking items ever trigger a question; important/optional
    items get a stated safe assumption instead of a question."""
    blocking = [m["item"] for m in missing_info if m["tier"] == "blocking"]
    resolvable = [m["item"] for m in missing_info if m["tier"] in ("important", "optional")]

    questions = [f"Could you clarify: {item}?" for item in blocking[:_MAX_CLARIFICATION_QUESTIONS]]
    safe_assumptions = [f"Assuming a reasonable default for: {item}" for item in resolvable]

    return {
        "needs_clarification": len(blocking) > 0,
        "questions": questions,
        "blocking_items": blocking,
        "safe_assumptions_made": safe_assumptions,
    }


# ============================================================================
# Risk/consequence/reversibility derivation — reuses the same signal
# Operational Self-Model already computes rather than re-deriving it
# (rule: reuse Operational Self-Model).
# ============================================================================

_HIGH_RISK_KEYWORDS = re.compile(
    r"\b(delete|remove permanently|push (this )?public(ly)?|deploy|purchase|buy|pay|send (an )?email|"
    r"post publicly|irreversible|production)\b", re.IGNORECASE
)


def derive_risk_profile(message: str, task_category: str) -> dict:
    """Deterministic, conservative: defaults to low/reversible unless real
    signal says otherwise. Mirrors operational_self_model.py's own
    risky-action detection so the two systems agree rather than disagree."""
    high_risk = bool(_HIGH_RISK_KEYWORDS.search(message)) or task_category == "action"
    return {
        "risk_level": "high" if high_risk else "low",
        "consequence_level": "high" if high_risk else "low",
        "reversibility": "hard_to_reverse" if high_risk else "reversible",
        "confirmation_requirement": high_risk,
    }
