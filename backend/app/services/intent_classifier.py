"""ECHO Local Intelligence Engine v1 — Phase 3: rich intent classification.

Deterministic, regex-only, no model call — same style as app/search_intent.py.
Deliberately layered on top of the existing classifiers rather than
re-deriving their logic: app/services/context_router.py already decides
which context source(s) a message needs (Atlas/previous-conversation/wiki/
web/rss/projects/tasks/library), and app/search_intent.py already decides
current-vs-stable-info routing. This module adds the categories those two
don't cover (coding/code_review/study_tutor/troubleshooting/release_testing/
emotional_support/creative_writing/prompt_generation/image_generation) and
maps everything onto the richer per-message profile the engine's pipeline
needs (difficulty, source_need, reasoning_need, freshness_need, answer_style,
can_answer_local_only, should_ask_clarifying_question).
"""

import re
from dataclasses import dataclass
from typing import Literal

from app.services import context_router

IntentCategory = Literal[
    "normal_chat",
    "personal_memory",
    "previous_conversation",
    "project_task",
    "schedule",
    "library_file",
    "coding",
    "code_review",
    "study_tutor",
    "current_info",
    "web_search_needed",
    "wiki_background",
    "rss_headlines",
    "troubleshooting",
    "release_testing",
    "emotional_support",
    "creative_writing",
    "prompt_generation",
    "image_generation",
    "unknown",
]

Difficulty = Literal["easy", "medium", "hard"]
SourceNeed = Literal["none", "memory", "file", "wiki", "rss", "web", "mixed"]
ReasoningNeed = Literal["low", "medium", "high"]
FreshnessNeed = Literal["stable", "current", "live"]
AnswerStyle = Literal["short", "normal", "detailed", "prompt", "checklist"]


@dataclass(frozen=True)
class IntentClassification:
    intent: IntentCategory
    difficulty: Difficulty
    source_need: SourceNeed
    reasoning_need: ReasoningNeed
    freshness_need: FreshnessNeed
    answer_style: AnswerStyle
    can_answer_local_only: bool
    should_ask_clarifying_question: bool
    reason: str
    confidence: float
    # Carried through from context_router.classify_context() so the Context
    # Gatherer doesn't have to re-classify — one source of truth per message.
    context_route: context_router.ContextRoute


# ---- New categories context_router/search_intent don't already cover ----

_PROMPT_GENERATION_PATTERN = re.compile(
    r"\b(claude code prompt|write me a prompt|give me a (detailed )?prompt|structured prompt|"
    r"prompt (for|to) (build|create|test|implement))\b",
    re.IGNORECASE,
)
_IMAGE_GENERATION_PATTERN = re.compile(
    r"\b(generate an? image|create a picture|draw me|make an image|generate a (picture|photo|drawing))\b",
    re.IGNORECASE,
)
_CODE_REVIEW_PATTERN = re.compile(
    r"\b(review (this|my) (code|function|pr|pull request)|debug this|fix this bug|"
    r"what'?s wrong with this (code|function))\b",
    re.IGNORECASE,
)
_CODING_PATTERN = re.compile(
    r"\b(write (a |some )?(function|class|script|code)|implement (a|this)|refactor this|"
    r"how do i (code|program|write)\b|```)",
    re.IGNORECASE,
)
_STUDY_TUTOR_PATTERN = re.compile(
    r"\b(teach me|help me (understand|learn)|explain (this )?(like i'?m|simply)|study session|"
    r"quiz me|walk me through (this|the) concept)\b",
    re.IGNORECASE,
)
_TROUBLESHOOTING_PATTERN = re.compile(
    r"\b(not working|won'?t start|keeps crashing|broken|stopped working|throwing an? error|"
    r"can'?t connect|failing to)\b",
    re.IGNORECASE,
)
_RELEASE_TESTING_PATTERN = re.compile(
    r"\b(is (echo|this|it) (green|ready|stable)\??|release candidate|run the tests|"
    r"build status|is (this |it )?production ready\??)\b",
    re.IGNORECASE,
)
_CREATIVE_WRITING_PATTERN = re.compile(
    r"\b(write (me )?a\b.{0,20}\b(story|poem|song|joke)|creative writing|make up a (story|character))\b",
    re.IGNORECASE,
)
_EMOTIONAL_SUPPORT_PATTERN = re.compile(
    r"\b(i'?m (overwhelmed|stressed|anxious|struggling|exhausted|burnt? out)|"
    r"what should i do next\??|i don'?t know what to do|feeling (down|lost|stuck))\b",
    re.IGNORECASE,
)

_VAGUE_MESSAGE_PATTERN = re.compile(r"^(help|idk|hmm+|what|\?+|hi|hey)\.?\??$", re.IGNORECASE)

# Static per-intent profile — the inherent nature of the intent category,
# independent of whether a given source happens to be configured right now
# (that's the Context Gatherer's concern, not this classifier's).
_INTENT_PROFILES: dict[IntentCategory, dict] = {
    "normal_chat": dict(difficulty="easy", source_need="none", reasoning_need="low", freshness_need="stable", answer_style="normal", can_answer_local_only=True),
    "personal_memory": dict(difficulty="easy", source_need="memory", reasoning_need="low", freshness_need="stable", answer_style="normal", can_answer_local_only=True),
    "previous_conversation": dict(difficulty="easy", source_need="memory", reasoning_need="low", freshness_need="stable", answer_style="normal", can_answer_local_only=True),
    "project_task": dict(difficulty="easy", source_need="memory", reasoning_need="low", freshness_need="stable", answer_style="short", can_answer_local_only=True),
    "schedule": dict(difficulty="easy", source_need="memory", reasoning_need="low", freshness_need="stable", answer_style="short", can_answer_local_only=True),
    "library_file": dict(difficulty="medium", source_need="file", reasoning_need="medium", freshness_need="stable", answer_style="normal", can_answer_local_only=True),
    "coding": dict(difficulty="medium", source_need="none", reasoning_need="high", freshness_need="stable", answer_style="detailed", can_answer_local_only=True),
    "code_review": dict(difficulty="hard", source_need="none", reasoning_need="high", freshness_need="stable", answer_style="checklist", can_answer_local_only=True),
    "study_tutor": dict(difficulty="medium", source_need="none", reasoning_need="medium", freshness_need="stable", answer_style="detailed", can_answer_local_only=True),
    "current_info": dict(difficulty="medium", source_need="web", reasoning_need="low", freshness_need="live", answer_style="short", can_answer_local_only=False),
    "web_search_needed": dict(difficulty="medium", source_need="web", reasoning_need="low", freshness_need="current", answer_style="normal", can_answer_local_only=False),
    "wiki_background": dict(difficulty="easy", source_need="wiki", reasoning_need="low", freshness_need="stable", answer_style="normal", can_answer_local_only=True),
    "rss_headlines": dict(difficulty="easy", source_need="rss", reasoning_need="low", freshness_need="live", answer_style="short", can_answer_local_only=False),
    "troubleshooting": dict(difficulty="hard", source_need="none", reasoning_need="high", freshness_need="stable", answer_style="checklist", can_answer_local_only=True),
    "release_testing": dict(difficulty="medium", source_need="memory", reasoning_need="medium", freshness_need="stable", answer_style="checklist", can_answer_local_only=True),
    "emotional_support": dict(difficulty="easy", source_need="none", reasoning_need="low", freshness_need="stable", answer_style="short", can_answer_local_only=True),
    "creative_writing": dict(difficulty="medium", source_need="none", reasoning_need="medium", freshness_need="stable", answer_style="detailed", can_answer_local_only=True),
    "prompt_generation": dict(difficulty="hard", source_need="none", reasoning_need="medium", freshness_need="stable", answer_style="prompt", can_answer_local_only=True),
    "image_generation": dict(difficulty="easy", source_need="none", reasoning_need="low", freshness_need="stable", answer_style="short", can_answer_local_only=True),
    "unknown": dict(difficulty="medium", source_need="none", reasoning_need="medium", freshness_need="stable", answer_style="normal", can_answer_local_only=True),
}

# context_router's ContextSource selections map onto an IntentCategory when
# none of the more-specific patterns above matched first.
_SOURCE_TO_INTENT: dict[str, IntentCategory] = {
    "atlas_memory": "personal_memory",
    "previous_conversation": "previous_conversation",
    "projects": "project_task",
    "tasks": "project_task",
    "schedule": "schedule",
    "library": "library_file",
    "wiki": "wiki_background",
    "rss": "rss_headlines",
    "web_search": "current_info",
}


def _profile_for(intent: IntentCategory) -> dict:
    return dict(_INTENT_PROFILES[intent])


def classify_intent(
    message: str,
    conversation_id: str | None = None,
    active_project_id: str | None = None,
) -> IntentClassification:
    """Never raises. Falls back to "unknown" (with can_answer_local_only=True,
    a safe default — trying to answer locally is better than blocking) for
    anything genuinely ambiguous."""
    route = context_router.classify_context(message, conversation_id, active_project_id)

    if not message or not message.strip():
        profile = _profile_for("normal_chat")
        return IntentClassification(
            intent="normal_chat", reason="empty message", confidence=1.0, should_ask_clarifying_question=False,
            context_route=route, **profile,
        )

    text = message.strip()

    # Highest priority: explicit, unambiguous request shapes that context_router
    # has no concept of at all.
    for pattern, intent, reason in (
        (_PROMPT_GENERATION_PATTERN, "prompt_generation", "asks for a structured/Claude Code prompt"),
        (_IMAGE_GENERATION_PATTERN, "image_generation", "asks to generate an image"),
        (_CODE_REVIEW_PATTERN, "code_review", "asks to review/debug/fix existing code"),
        (_RELEASE_TESTING_PATTERN, "release_testing", "asks about build/release/test status"),
        (_TROUBLESHOOTING_PATTERN, "troubleshooting", "describes something broken/not working"),
        (_STUDY_TUTOR_PATTERN, "study_tutor", "asks to be taught/tutored through a concept"),
        (_CREATIVE_WRITING_PATTERN, "creative_writing", "asks for creative writing"),
        (_CODING_PATTERN, "coding", "asks to write/implement code"),
    ):
        if pattern.search(text):
            profile = _profile_for(intent)
            return IntentClassification(
                intent=intent, reason=reason, confidence=0.85, should_ask_clarifying_question=False,
                context_route=route, **profile,
            )

    # Memory/project/task/schedule/library/wiki/rss/web routing — reuse
    # context_router's own priority order rather than re-deriving it.
    for source in route.selected_sources:
        if source in _SOURCE_TO_INTENT:
            intent = _SOURCE_TO_INTENT[source]
            profile = _profile_for(intent)
            return IntentClassification(
                intent=intent, reason=route.reason, confidence=route.confidence,
                should_ask_clarifying_question=False, context_route=route, **profile,
            )

    # Emotional support — checked after concrete task/coding/info routing so a
    # message like "I'm stressed about this bug" still routes to coding/
    # troubleshooting first if it names a concrete technical problem.
    if _EMOTIONAL_SUPPORT_PATTERN.search(text):
        profile = _profile_for("emotional_support")
        return IntentClassification(
            intent="emotional_support", reason="message signals distress/overwhelm", confidence=0.75,
            should_ask_clarifying_question=False, context_route=route, **profile,
        )

    if _VAGUE_MESSAGE_PATTERN.match(text) or len(text) < 4:
        profile = _profile_for("unknown")
        return IntentClassification(
            intent="unknown", reason="message is too short/vague to classify confidently", confidence=0.3,
            should_ask_clarifying_question=True, context_route=route, **profile,
        )

    profile = _profile_for("normal_chat")
    return IntentClassification(
        intent="normal_chat", reason=route.reason, confidence=route.confidence,
        should_ask_clarifying_question=False, context_route=route, **profile,
    )
