"""ECHO Cognitive Core v1 — World Model + Task Understanding Engine.

A structured understanding layer that complements Atlas (ECHO's internal,
adaptive memory of facts about the user) rather than replacing it: durable
concepts and how they relate (the "world model"), a structured read of what
a complex request actually needs (goal / known / unknown / constraints /
success criteria / risks), reusable named workflows ("skills"), and simple
cause-effect notes ECHO can draw on for risk/troubleshooting reasoning.

Deterministic, regex/keyword-based throughout — same "no model call in the
classification layer" convention as search_intent.py, intent_classifier.py,
context_router.py, and dependency_patterns.py elsewhere in this codebase.
This is a practical cognitive *structure*, not a claim of understanding,
consciousness, or a human mind — see ECHO_COGNITIVE_CORE_V1.md for the
explicit boundary. Nothing here is ever shown as chain-of-thought in normal
chat; CognitiveBrief.brief_text is a short, compact summary fed into the
prompt builder, not a debug dump (see _build_brief_text()).
"""

import re

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    CausalNote,
    CognitiveBrief,
    CognitiveConcept,
    CognitiveRelationship,
    CognitiveSettings,
    SkillPattern,
    TaskUnderstanding,
)
from app.services.intent_classifier import IntentClassification, classify_intent

# ============================================================================
# Task type / domain classification (deterministic — reuses the existing
# intent classifier's difficulty/intent signal rather than re-deriving it)
# ============================================================================

_TASK_TYPE_BY_INTENT: dict[str, str] = {
    "code_review": "fix_bug",
    "troubleshooting": "troubleshoot",
    "release_testing": "release_build",
    "prompt_generation": "create_prompt",
    "study_tutor": "study_learn",
    "emotional_support": "personal_support",
    "current_info": "research_topic",
    "web_search_needed": "research_topic",
    "wiki_background": "research_topic",
    "rss_headlines": "research_topic",
    "library_file": "summarize_file",
    "project_task": "plan_project",
    "schedule": "plan_project",
    "creative_writing": "other",
}

_FIX_BUG_RE = re.compile(r"\b(fix|failing|broken|bug|crash|doesn'?t work|not working)\b", re.IGNORECASE)
_RUN_TEST_RE = re.compile(r"\brun (the |a )?tests?\b", re.IGNORECASE)
_DECISION_RE = re.compile(r"\b(should i|which (one|option)|help me decide|decision)\b", re.IGNORECASE)
_RELEASE_STATUS_RE = re.compile(r"\b(is echo (green|ready)|release status|is (it|echo) ready)\b", re.IGNORECASE)

# Intents where task-type detection also needs a keyword tiebreak, since the
# same intent covers several related task types (e.g. "coding" covers both
# fixing and building).
_CODING_INTENTS = {"coding"}


def _task_type_for(message: str, intent: IntentClassification) -> str:
    if _RELEASE_STATUS_RE.search(message):
        return "release_build"
    # A specific, already-classified intent beats a generic keyword match —
    # "give me a prompt to fix X" is a create_prompt task, not a fix_bug
    # task, even though "fix" appears in it.
    if intent.intent in _TASK_TYPE_BY_INTENT:
        return _TASK_TYPE_BY_INTENT[intent.intent]
    # Checked independent of intent — the intent classifier's own "coding"
    # pattern is narrower than what Cognitive Core considers a fix/test
    # task (see is_complex_task()'s matching comment).
    if _FIX_BUG_RE.search(message):
        return "fix_bug"
    if _RUN_TEST_RE.search(message):
        return "run_test"
    if intent.intent in _CODING_INTENTS:
        return "build_feature"
    if intent.intent == "normal_chat" and _DECISION_RE.search(message):
        return "make_decision"
    return "ask_question"


_DOMAIN_KEYWORDS: list[tuple[str, re.Pattern]] = [
    ("Android", re.compile(r"\b(android|apk|capacitor|gradle)\b", re.IGNORECASE)),
    ("Windows", re.compile(r"\b(windows app|tauri)\b", re.IGNORECASE)),
    ("deployment", re.compile(r"\b(release|deploy|docker|build status|green|yellow|red)\b", re.IGNORECASE)),
    ("AI/local models", re.compile(r"\b(ollama|local model|local intelligence|cognitive core)\b", re.IGNORECASE)),
    ("web app", re.compile(r"\b(vite|react|frontend build|web app)\b", re.IGNORECASE)),
    ("ECHO development", re.compile(r"\b(echo|backend|repo|milestone)\b", re.IGNORECASE)),
    ("coding", re.compile(r"\b(function|code|python|typescript|api|bug|test)\b", re.IGNORECASE)),
    ("study", re.compile(r"\b(learn|study|tutorial|explain (how|why))\b", re.IGNORECASE)),
    ("job/visa", re.compile(r"\b(job|visa|interview|career|resume|cv)\b", re.IGNORECASE)),
    ("health/support", re.compile(r"\b(stressed|overwhelmed|tired|anxious|burn(t|ed) out)\b", re.IGNORECASE)),
    ("research", re.compile(r"\b(research|investigate|compare|score|news|latest)\b", re.IGNORECASE)),
    ("personal planning", re.compile(r"\b(task|project|schedule|remind(er)?|plan)\b", re.IGNORECASE)),
]


def _detect_domain(message: str) -> str:
    for name, pattern in _DOMAIN_KEYWORDS:
        if pattern.search(message):
            return name
    return "general"


# Intents/task-types that always count as "complex" regardless of the
# intent classifier's own difficulty rating — release status and prompt
# generation are short questions but genuinely need structured understanding.
_ALWAYS_COMPLEX_INTENTS = {"coding", "code_review", "troubleshooting", "release_testing", "prompt_generation", "project_task", "library_file"}


def is_complex_task(intent: IntentClassification, message: str) -> bool:
    """Phase 4 rule 5 / Phase 1's own test 2: a simple greeting or one-line
    question should NOT create a heavy TaskUnderstanding row — only
    medium/hard-difficulty requests, or specific always-complex intents,
    warrant the structured read. Also checks fix/test/release-status
    phrasing directly (not just the intent classifier's own narrower
    "coding" pattern), since e.g. "fix the failing backend test" or "Is
    ECHO Green now?" are genuinely complex tasks even though they're short
    and don't trip that classifier's coding-keyword regex."""
    # Specific, explicit patterns win regardless of length/difficulty —
    # checked first so a short-but-real request like "Is ECHO Green now?"
    # (4 words) is never caught by the short-message bailout below.
    if intent.intent in _ALWAYS_COMPLEX_INTENTS:
        return True
    if _RELEASE_STATUS_RE.search(message) or _FIX_BUG_RE.search(message) or _RUN_TEST_RE.search(message):
        return True
    # A handful of words the intent classifier can't confidently place
    # ("hi", "thanks", "ok cool") come back as intent="unknown" with a
    # non-"easy" difficulty rather than a confident easy/normal_chat read —
    # a short, unclassifiable message that also matched none of the
    # explicit patterns above is a reason for LESS structured analysis,
    # not more.
    if len(message.split()) <= 4:
        return False
    return intent.difficulty != "easy"


# ============================================================================
# Per-task-type templates — deterministic, grounded in what's actually true
# about this codebase (never fabricated). Each entry is (known, unknown,
# constraints, success_criteria, risks) as short plain-string lists.
# ============================================================================

_ALWAYS_CONSTRAINTS = ["no paid APIs required", "do not break existing features"]

_TEMPLATES: dict[str, dict] = {
    "release_build": {
        "known": ["ECHO release status must be based on actually-recorded test/build results, not a guess."],
        "unknown": ["latest backend test result", "latest frontend build result"],
        "constraints": [*_ALWAYS_CONSTRAINTS, "cannot claim Green without evidence"],
        "success": ["backend tests pass", "frontend build passes", "Green/Yellow/Red is assigned honestly with proof"],
        "risks": ["claiming Green without running the actual checks first"],
        "goal": "Determine ECHO's actual release readiness.",
    },
    "build_feature": {
        "known": ["ECHO already has an established backend (FastAPI/SQLAlchemy) and frontend (React/TypeScript/Vite) structure to extend."],
        "unknown": ["exact files/modules this feature touches until the repo is inspected"],
        "constraints": [*_ALWAYS_CONSTRAINTS, "do not rebuild the whole app"],
        "success": ["backend tests pass", "frontend build passes", "manual UI check passes", "docs updated", "no existing feature broken"],
        "risks": ["scope creep beyond what was actually asked for"],
        "goal": "Implement the requested feature safely.",
    },
    "fix_bug": {
        "known": ["a specific failure/symptom was reported."],
        "unknown": ["root cause until the failing case is reproduced/inspected"],
        "constraints": [*_ALWAYS_CONSTRAINTS, "fix the smallest correct cause, not a broad rewrite"],
        "success": ["the specific failing case now passes/works", "the full relevant test suite still passes", "no new regression introduced"],
        "risks": ["fixing a symptom instead of the actual root cause"],
        "goal": "Find and fix the reported problem.",
    },
    "run_test": {
        "known": ["ECHO's backend test suite runs via pytest, no real network/model calls in tests."],
        "unknown": ["current pass/fail state until the suite is actually run"],
        "constraints": [*_ALWAYS_CONSTRAINTS],
        "success": ["the requested test(s) actually run", "result (pass/fail) is reported honestly"],
        "risks": ["reporting a result without actually running the command"],
        "goal": "Run the requested test(s) and report the real result.",
    },
    "plan_project": {
        "known": ["ECHO has Projects/Tasks/Schedule/Mission Control for tracking ongoing work, if already built."],
        "unknown": ["specific scope/deadline details not yet stated by the user"],
        "constraints": [*_ALWAYS_CONSTRAINTS],
        "success": ["a concrete next step is identified", "the plan is stored where it can be tracked, if requested"],
        "risks": ["a plan too vague to actually act on"],
        "goal": "Turn the request into a concrete, trackable plan.",
    },
    "research_topic": {
        "known": [],
        "unknown": ["current/live facts unless an actual search source is retrieved this turn"],
        "constraints": [*_ALWAYS_CONSTRAINTS, "never invent a live fact from training data"],
        "success": ["a real source was retrieved and used, or the answer honestly says it couldn't verify"],
        "risks": ["stating a stale or invented fact as if it were current"],
        "goal": "Answer the question using a real, current source where one is needed.",
    },
    "summarize_file": {
        "known": ["the file exists in the Library, if referenced correctly."],
        "unknown": ["the file's actual content until it's read"],
        "constraints": [*_ALWAYS_CONSTRAINTS],
        "success": ["a real summary is produced from the file's actual extracted text", "unsupported file types are reported honestly, not guessed"],
        "risks": ["summarizing a file that was never actually read"],
        "goal": "Summarize the requested file accurately.",
    },
    "make_decision": {
        "known": [],
        "unknown": ["the user's actual priorities/constraints for this decision, unless stated"],
        "constraints": [*_ALWAYS_CONSTRAINTS, "give a real recommendation with a reason, not just a list of options"],
        "success": ["a clear recommendation is given", "the tradeoff/reason is stated", "the user can still choose differently"],
        "risks": ["staying noncommittal when a real recommendation was asked for"],
        "goal": "Help the user make a specific decision.",
    },
    "create_prompt": {
        "known": ["a good Claude Code style prompt needs goal, context, rules, phases, tests, and a final report format."],
        "unknown": ["exact repo scripts/paths unless the current repo state is inspected first"],
        "constraints": [*_ALWAYS_CONSTRAINTS, "the prompt itself must not require paid APIs or real API keys"],
        "success": ["prompt includes context", "prompt includes concrete tasks/phases", "prompt includes rules", "prompt includes tests", "prompt includes a final report format"],
        "risks": ["a vague prompt that doesn't actually specify what done looks like"],
        "goal": "Produce a complete, structured, ready-to-use prompt.",
    },
    "troubleshoot": {
        "known": [],
        "unknown": ["root cause until the actual symptom/logs are inspected"],
        "constraints": [*_ALWAYS_CONSTRAINTS],
        "success": ["the actual cause is identified (not guessed)", "a concrete fix or next diagnostic step is given"],
        "risks": ["guessing a cause without checking it"],
        "goal": "Diagnose and resolve the reported problem.",
    },
    "study_learn": {
        "known": [],
        "unknown": ["the user's current level of familiarity, unless stated"],
        "constraints": [*_ALWAYS_CONSTRAINTS],
        "success": ["explanation leads with a concrete example", "answer is at the right level of depth for the question"],
        "risks": ["an explanation too abstract to actually be useful"],
        "goal": "Help the user understand the topic.",
    },
    "personal_support": {
        "known": [],
        "unknown": [],
        "constraints": [*_ALWAYS_CONSTRAINTS, "keep tone low-pressure, one concrete next step at a time"],
        "success": ["response acknowledges what was said", "response doesn't add pressure or a long list of demands"],
        "risks": ["responding with a wall of text when the user needs less, not more"],
        "goal": "Respond supportively to what the user is going through.",
    },
    "ask_question": {
        "known": [],
        "unknown": [],
        "constraints": list(_ALWAYS_CONSTRAINTS),
        "success": ["the question is actually answered directly"],
        "risks": [],
        "goal": "Answer the user's question.",
    },
    "other": {
        "known": [],
        "unknown": [],
        "constraints": list(_ALWAYS_CONSTRAINTS),
        "success": ["the request is addressed directly"],
        "risks": [],
        "goal": "Address the user's request.",
    },
}

# Domain-specific additions layered on top of the task-type template —
# grounded in this actual codebase's real architecture, not invented.
_DOMAIN_ADDITIONS: dict[str, dict] = {
    "Android": {
        "known": ["ECHO's Android app uses Capacitor, wrapping the Vite frontend build.", "the APK needs the latest web assets synced in before building."],
        "unknown": ["Android SDK/Gradle availability on this machine", "the backend URL configured for the phone (must not be localhost)"],
        "success": ["frontend build passes", "Capacitor sync succeeds", "APK builds", "APK installs and connects to the backend"],
    },
    "Windows": {
        "known": ["ECHO's Windows app uses Tauri, wrapping the Vite frontend build."],
        "unknown": ["whether the Rust/Tauri toolchain is available on this machine"],
        "success": ["frontend build passes", "Tauri build succeeds", "app launches and connects to the backend"],
    },
}


def _merge_template(task_type: str, domain: str) -> dict:
    base = _TEMPLATES.get(task_type, _TEMPLATES["other"])
    merged = {
        "known": list(base["known"]),
        "unknown": list(base["unknown"]),
        "constraints": list(base["constraints"]),
        "success": list(base["success"]),
        "risks": list(base["risks"]),
        "goal": base["goal"],
    }
    addition = _DOMAIN_ADDITIONS.get(domain)
    if addition:
        merged["known"] += [k for k in addition.get("known", []) if k not in merged["known"]]
        merged["unknown"] += [u for u in addition.get("unknown", []) if u not in merged["unknown"]]
        merged["success"] += [s for s in addition.get("success", []) if s not in merged["success"]]
    return merged


def _next_step_for(task_type: str, unknowns: list[str]) -> str:
    if task_type == "release_build":
        return "Run the actual backend test suite and frontend build, then report the real result."
    if task_type == "fix_bug" or task_type == "troubleshoot":
        return "Reproduce the failure and inspect the actual cause before proposing a fix."
    if task_type == "run_test":
        return "Run the requested test command and report the result."
    if unknowns:
        return f"Resolve the first unknown: {unknowns[0]}"
    return "Proceed with the request directly."


# ============================================================================
# Missing-knowledge detection + success criteria (standalone, also usable
# without a stored TaskUnderstanding — Phase 3's separate function list)
# ============================================================================


def detect_missing_knowledge(task_type: str, domain: str) -> list[str]:
    return _merge_template(task_type, domain)["unknown"]


def generate_success_criteria(task_type: str, domain: str) -> list[str]:
    return _merge_template(task_type, domain)["success"]


# ============================================================================
# Concept / skill selection
# ============================================================================


def select_relevant_concepts(db: Session, message: str, limit: int = 5) -> list[CognitiveConcept]:
    """Deterministic substring match against concept name/description — the
    same "no model call" convention as everything else here. Good enough
    for a v1 world model of this size; not semantic search (that's Atlas's
    job, via app/atlas.py's embedding-based search)."""
    words = {w.lower() for w in re.findall(r"[a-zA-Z][a-zA-Z0-9_+#.-]{2,}", message)}
    if not words:
        return []
    concepts = db.query(CognitiveConcept).filter(CognitiveConcept.archived_at.is_(None)).all()
    matches = []
    for concept in concepts:
        haystack = f"{concept.name} {concept.description or ''}".lower()
        if any(w in haystack for w in words):
            matches.append(concept)
    return matches[:limit]


_SKILL_KEYWORDS: dict[str, list[str]] = {
    "Build Android APK": ["android", "apk", "capacitor"],
    "Build Windows App": ["windows app", "tauri"],
    "Run ECHO Release Verification": ["release status", "is echo green", "is echo ready", "release readiness"],
    "Fix Failing Backend Test": ["failing test", "fix test", "test failing", "broken test"],
    "Create Claude Code Prompt": ["claude code prompt", "give me a prompt", "write a prompt"],
    "Configure No-Billing Search": ["searxng", "no-billing search", "configure search"],
    "Improve ECHO Feature Safely": ["improve echo", "add a feature to echo", "new echo feature"],
}


def select_relevant_skills(db: Session, message: str, limit: int = 3) -> list[SkillPattern]:
    lowered = message.lower()
    skills = db.query(SkillPattern).filter(SkillPattern.archived_at.is_(None)).all()
    scored = []
    for skill in skills:
        keywords = _SKILL_KEYWORDS.get(skill.name, [])
        trigger_words = [t.lower() for t in (skill.trigger_patterns_json or [])]
        if any(kw in lowered for kw in keywords) or any(t in lowered for t in trigger_words):
            scored.append(skill)
    return scored[:limit]


def select_relevant_causal_notes(db: Session, task_type: str, domain: str, limit: int = 3) -> list[CausalNote]:
    """Keyword match against cause/effect/title — narrow on purpose (this
    is a small, curated set of ECHO-operations notes, not general
    knowledge)."""
    keyword_map = {
        ("release_build", None): ["test", "green", "build"],
        (None, "Android"): ["android", "localhost", "apk"],
        ("research_topic", None): ["current info", "source", "invent"],
        ("troubleshoot", None): ["offline", "fail"],
        ("fix_bug", None): ["fail", "test"],
    }
    keywords: list[str] = []
    for (t, d), kws in keyword_map.items():
        if (t is None or t == task_type) and (d is None or d == domain):
            keywords += kws
    if not keywords:
        return []
    notes = db.query(CausalNote).filter(CausalNote.archived_at.is_(None)).all()
    matches = []
    for note in notes:
        haystack = f"{note.title} {note.cause} {note.effect}".lower()
        if any(kw in haystack for kw in keywords):
            matches.append(note)
    return matches[:limit]


# ============================================================================
# Task Understanding
# ============================================================================


def build_task_understanding(
    db: Session, user_message: str, conversation_id: str | None = None, user_id: str | None = None
) -> TaskUnderstanding | None:
    """Returns None for simple messages (Phase 4 rule 5 / Phase 1 test 2) —
    the caller should treat a None return as "use the lightweight path,
    nothing stored." Only medium/hard-difficulty or always-complex-intent
    requests get a real, stored TaskUnderstanding row."""
    intent = classify_intent(user_message, conversation_id)
    if not is_complex_task(intent, user_message):
        return None

    task_type = _task_type_for(user_message, intent)
    domain = _detect_domain(user_message)
    template = _merge_template(task_type, domain)
    relevant_concepts = select_relevant_concepts(db, user_message)
    unknowns = template["unknown"]
    confidence = "incomplete" if unknowns else "medium"

    tu = TaskUnderstanding(
        conversation_id=conversation_id,
        user_message=user_message[:2000],
        goal_summary=template["goal"],
        domain=domain,
        task_type=task_type,
        known_facts_json=template["known"],
        unknowns_json=unknowns,
        constraints_json=template["constraints"],
        assumptions_json=[],
        success_criteria_json=template["success"],
        risks_json=template["risks"],
        relevant_concepts_json=[c.id for c in relevant_concepts],
        recommended_next_step=_next_step_for(task_type, unknowns),
        confidence=confidence,
    )
    db.add(tu)
    db.commit()
    db.refresh(tu)
    return tu


# ============================================================================
# Cognitive Brief — the compact, prompt-ready output
# ============================================================================


def _build_brief_text(tu: TaskUnderstanding, concepts: list[CognitiveConcept], skills: list[SkillPattern], causal_notes: list[CausalNote]) -> str:
    """Compact by design (Phase 3 rule 1) — a handful of short lines, never
    a JSON dump, never chain-of-thought. This is what gets inserted into
    the prompt builder, so every line here is something that should
    genuinely help the model answer better, not internal bookkeeping."""
    lines = [f"Goal: {tu.goal_summary}", f"Domain: {tu.domain} / Task type: {tu.task_type}"]
    if tu.known_facts_json:
        lines.append("Known: " + "; ".join(tu.known_facts_json))
    if tu.unknowns_json:
        lines.append("Unknown (verify, don't guess): " + "; ".join(tu.unknowns_json))
    if tu.constraints_json:
        lines.append("Constraints: " + "; ".join(tu.constraints_json))
    if tu.success_criteria_json:
        lines.append("Success looks like: " + "; ".join(tu.success_criteria_json))
    if tu.risks_json:
        lines.append("Watch out for: " + "; ".join(tu.risks_json))
    if concepts:
        lines.append("Relevant concepts: " + "; ".join(c.name for c in concepts))
    if skills:
        lines.append("Relevant known workflow: " + "; ".join(s.name for s in skills))
    if causal_notes:
        lines.append("Relevant causal notes: " + "; ".join(f"{n.cause} -> {n.effect}" for n in causal_notes))
    if tu.recommended_next_step:
        lines.append(f"Smallest correct next step: {tu.recommended_next_step}")
    return "\n".join(lines)


def build_cognitive_brief(db: Session, tu: TaskUnderstanding, conversation_id: str | None = None) -> CognitiveBrief:
    concepts = [db.get(CognitiveConcept, cid) for cid in (tu.relevant_concepts_json or [])]
    concepts = [c for c in concepts if c is not None]
    skills = select_relevant_skills(db, tu.user_message)
    causal_notes = select_relevant_causal_notes(db, tu.task_type, tu.domain)

    brief_text = _build_brief_text(tu, concepts, skills, causal_notes)
    context_sources = []
    if concepts:
        context_sources.append("world_model")
    if skills:
        context_sources.append("skill_library")
    if causal_notes:
        context_sources.append("causal_notes")

    brief = CognitiveBrief(
        conversation_id=conversation_id or tu.conversation_id,
        task_understanding_id=tu.id,
        brief_text=brief_text,
        selected_concepts_json=[c.name for c in concepts],
        selected_skills_json=[s.name for s in skills],
        selected_context_sources_json=context_sources,
    )
    db.add(brief)
    db.commit()
    db.refresh(brief)
    return brief


def get_cognitive_brief_for_message(db: Session, user_message: str, conversation_id: str | None = None) -> CognitiveBrief | None:
    """The one function callers (persona.py, local_intelligence_engine.py)
    actually need: build a TaskUnderstanding for this message if it's
    complex enough, then a compact CognitiveBrief from it. Returns None for
    simple messages — the caller should skip brief injection entirely
    rather than injecting an empty one."""
    tu = build_task_understanding(db, user_message, conversation_id)
    if tu is None:
        return None
    return build_cognitive_brief(db, tu, conversation_id)


# ============================================================================
# World model CRUD helpers
# ============================================================================


def create_or_update_concept(
    db: Session,
    *,
    name: str,
    description: str | None = None,
    concept_type: str = "other",
    confidence: str = "medium",
    source_type: str | None = "manual",
    source_id: str | None = None,
) -> CognitiveConcept:
    """Deduplicates by case-insensitive name match against non-archived
    concepts (Phase 6 rule "duplicate concepts are merged or deduplicated")
    — an update to an existing concept, not a new row every time the same
    durable concept comes up again."""
    if not name.strip():
        raise ValueError("A concept name is required.")
    existing = (
        db.query(CognitiveConcept)
        .filter(CognitiveConcept.archived_at.is_(None), CognitiveConcept.name.ilike(name.strip()))
        .first()
    )
    if existing:
        if description:
            existing.description = description
        existing.concept_type = concept_type
        existing.confidence = confidence
        db.commit()
        db.refresh(existing)
        return existing
    concept = CognitiveConcept(
        name=name.strip(), description=description, concept_type=concept_type, confidence=confidence, source_type=source_type, source_id=source_id
    )
    db.add(concept)
    db.commit()
    db.refresh(concept)
    return concept


def create_relationship(
    db: Session,
    *,
    from_concept_id: str,
    to_concept_id: str,
    relation_type: str,
    description: str | None = None,
    confidence: str = "medium",
    source_type: str | None = "manual",
    source_id: str | None = None,
) -> CognitiveRelationship:
    if db.get(CognitiveConcept, from_concept_id) is None or db.get(CognitiveConcept, to_concept_id) is None:
        raise ValueError("Both concepts must exist.")
    rel = CognitiveRelationship(
        from_concept_id=from_concept_id,
        to_concept_id=to_concept_id,
        relation_type=relation_type,
        description=description,
        confidence=confidence,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(rel)
    db.commit()
    db.refresh(rel)
    return rel


def search_world_model(db: Session, query: str, limit: int = 10) -> list[dict]:
    """Returns each matched concept plus its relationships (both directions)
    — the "graph query" the API exposes at GET /api/cognitive/graph."""
    like = f"%{query.strip()}%"
    concepts = (
        db.query(CognitiveConcept)
        .filter(CognitiveConcept.archived_at.is_(None))
        .filter(or_(CognitiveConcept.name.ilike(like), CognitiveConcept.description.ilike(like)))
        .limit(limit)
        .all()
    )
    results = []
    for concept in concepts:
        rels = (
            db.query(CognitiveRelationship)
            .filter(or_(CognitiveRelationship.from_concept_id == concept.id, CognitiveRelationship.to_concept_id == concept.id))
            .all()
        )
        results.append({"concept": concept, "relationships": rels})
    return results


# ============================================================================
# Settings (single mutable row, config.py's fields are just the initial
# default — see CognitiveSettings' docstring in models.py)
# ============================================================================


def get_or_create_settings(db: Session) -> CognitiveSettings:
    row = db.get(CognitiveSettings, "singleton")
    if row is not None:
        return row
    defaults = get_settings()
    row = CognitiveSettings(
        id="singleton",
        cognitive_core_enabled=defaults.cognitive_core_enabled,
        cognitive_concept_extraction_enabled=defaults.cognitive_concept_extraction_enabled,
        cognitive_skill_matching_enabled=defaults.cognitive_skill_matching_enabled,
        cognitive_show_developer_diagnostics=defaults.cognitive_show_developer_diagnostics,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update_settings(db: Session, updates: dict) -> CognitiveSettings:
    row = get_or_create_settings(db)
    for field, value in updates.items():
        if value is not None:
            setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row


# ============================================================================
# Seeding (Phase 17) — idempotent, source_type="system"
# ============================================================================

_SEED_CONCEPTS: list[dict] = [
    {"name": "ECHO", "description": "The adaptive personal AI this repository builds.", "concept_type": "system"},
    {"name": "Atlas memory", "description": "ECHO's internal, adaptive long-term memory of facts about the user.", "concept_type": "system"},
    {"name": "Ollama", "description": "Local model runtime ECHO uses for local-first chat.", "concept_type": "tool"},
    {"name": "Local Intelligence Engine", "description": "Multi-pass local-model workflow: intent, context, draft, critic, repair, style.", "concept_type": "system"},
    {"name": "Human Persona Layer", "description": "Style layer controlling ECHO's tone, humour, and relationship memory.", "concept_type": "system"},
    {"name": "Cognitive Core", "description": "Structured task-understanding and world-model layer on top of Atlas.", "concept_type": "system"},
    {"name": "SearXNG", "description": "Self-hosted, no-billing web search meta-engine.", "concept_type": "tool"},
    {"name": "Wikipedia provider", "description": "Free Wikipedia lookups for stable background facts.", "concept_type": "tool"},
    {"name": "RSS provider", "description": "Configured RSS feeds for current headlines.", "concept_type": "tool"},
    {"name": "API keys", "description": "Credentials for cloud model providers — optional, never required for local-first use.", "concept_type": "technical"},
    {"name": "no-billing search", "description": "Web/wiki/RSS search that never requires a paid API key.", "concept_type": "technical"},
    {"name": "Android APK", "description": "ECHO's Android app build artifact.", "concept_type": "file"},
    {"name": "Capacitor", "description": "Wraps the Vite web build into the Android app.", "concept_type": "tool"},
    {"name": "Windows app", "description": "ECHO's Windows desktop app build.", "concept_type": "system"},
    {"name": "Tauri", "description": "Wraps the Vite web build into the Windows app.", "concept_type": "tool"},
    {"name": "frontend build", "description": "The Vite production build (npm run build) — the shared asset source for web/Android/Windows.", "concept_type": "process"},
    {"name": "backend tests", "description": "ECHO's pytest suite — no real network/model calls.", "concept_type": "process"},
    {"name": "Release Manager", "description": "Tracks recorded test/build results; Green only when every required check has actually passed.", "concept_type": "system"},
    {"name": "Knowledge Vault", "description": "User-visible, user-editable notes/decisions/prompts.", "concept_type": "system"},
    {"name": "Claude Code prompts", "description": "Structured prompts used to direct Claude Code work on this repo.", "concept_type": "process"},
    {"name": "cloud providers", "description": "Optional paid model providers (Anthropic/OpenAI/Gemini/Grok/Azure) — never required for local-first use.", "concept_type": "risk"},
]

_SEED_RELATIONSHIPS: list[tuple[str, str, str]] = [
    ("ECHO", "uses", "Atlas memory"),
    ("ECHO", "uses", "Ollama"),
    ("Android APK", "uses", "Capacitor"),
    ("Windows app", "uses", "Tauri"),
    ("Capacitor", "requires", "frontend build"),
    ("Tauri", "requires", "frontend build"),
    ("Local Intelligence Engine", "uses", "Ollama"),
    ("no-billing search", "uses", "SearXNG"),
    ("no-billing search", "uses", "Wikipedia provider"),
    ("no-billing search", "uses", "RSS provider"),
    ("ECHO", "uses", "no-billing search"),
    ("Android APK", "requires", "frontend build"),
    ("Windows app", "requires", "frontend build"),
    ("Release Manager", "requires", "backend tests"),
    ("Release Manager", "requires", "frontend build"),
    ("Cognitive Core", "part_of", "ECHO"),
    ("Local Intelligence Engine", "part_of", "ECHO"),
    ("Human Persona Layer", "part_of", "ECHO"),
    ("API keys", "enables", "cloud providers"),
    ("cloud providers", "conflicts_with", "no-billing search"),
]

_SEED_CAUSAL_NOTES: list[dict] = [
    {
        "title": "Ollama offline breaks local chat",
        "cause": "Ollama is offline or unreachable",
        "effect": "local model chat/Local Intelligence Engine calls fail",
        "explanation": "ECHO's local-first path has no fallback of its own for a totally unreachable Ollama — it should say so cleanly, not guess.",
    },
    {
        "title": "No current-info source means no live facts",
        "cause": "a current-info source (web/RSS) is unavailable for this turn",
        "effect": "ECHO must not invent live facts and should say it cannot verify",
        "explanation": "Wiki-only background is not enough for genuinely current/live questions.",
    },
    {
        "title": "Failing tests block Green",
        "cause": "backend tests fail or were never run",
        "effect": "release status cannot honestly be Green",
        "explanation": "Green is only ever claimed from actually-recorded evidence, matching this repo's Release Manager rule.",
    },
    {
        "title": "Broken frontend build breaks all platforms",
        "cause": "the frontend build fails",
        "effect": "web/Android/Windows app assets may be stale or broken",
        "explanation": "Capacitor and Tauri both wrap the same Vite dist output.",
    },
    {
        "title": "Android pointed at localhost can't reach the PC backend",
        "cause": "the Android app's backend URL points to localhost",
        "effect": "the phone cannot reach the PC's backend unless it's configured with the PC's real LAN/Tailscale address",
        "explanation": "localhost on a phone means the phone itself, not the development machine.",
    },
    {
        "title": "Cloud fallback disabled means no paid call",
        "cause": "cloud fallback is disabled (the default)",
        "effect": "no paid provider should ever be called — ECHO answers locally or states the limitation",
        "explanation": "Matches the Local Intelligence Engine's Cloud Fallback Gate, off by default.",
    },
]


def seed_world_model(db: Session) -> None:
    """Idempotent — only inserts concepts/relationships/causal notes that
    don't already exist by name. Marks everything as source_type='system'
    so a user can tell seeded knowledge apart from their own edits, and can
    still edit or archive it freely afterward (Phase 17 rule 4)."""
    existing_names = {c.name for c in db.query(CognitiveConcept).all()}
    name_to_id: dict[str, str] = {c.name: c.id for c in db.query(CognitiveConcept).all()}
    for entry in _SEED_CONCEPTS:
        if entry["name"] in existing_names:
            continue
        concept = CognitiveConcept(
            name=entry["name"], description=entry["description"], concept_type=entry["concept_type"], confidence="high", source_type="system"
        )
        db.add(concept)
        db.flush()
        name_to_id[entry["name"]] = concept.id
        existing_names.add(entry["name"])
    db.commit()

    existing_rels = {
        (r.from_concept_id, r.relation_type, r.to_concept_id)
        for r in db.query(CognitiveRelationship).all()
    }
    for from_name, relation_type, to_name in _SEED_RELATIONSHIPS:
        from_id = name_to_id.get(from_name)
        to_id = name_to_id.get(to_name)
        if from_id is None or to_id is None:
            continue
        if (from_id, relation_type, to_id) in existing_rels:
            continue
        db.add(
            CognitiveRelationship(
                from_concept_id=from_id, to_concept_id=to_id, relation_type=relation_type, confidence="high", source_type="system"
            )
        )
    db.commit()

    existing_titles = {n.title for n in db.query(CausalNote).all()}
    for entry in _SEED_CAUSAL_NOTES:
        if entry["title"] in existing_titles:
            continue
        db.add(
            CausalNote(
                title=entry["title"],
                cause=entry["cause"],
                effect=entry["effect"],
                explanation=entry["explanation"],
                confidence="high",
                source_type="system",
            )
        )
    db.commit()

    from app.services import skill_library

    skill_library.seed_skills(db)
