"""Layer 3A Part 2C — adaptive communication persona runtime.

Core Identity answers what ECHO is.  This module answers only how ECHO
communicates for one request.  It normalizes existing user-controlled
settings, reviewed Atlas preferences, bounded relationship context, current
instructions, and accessibility needs into immutable semantic values.  Raw
memory/profile text is never copied into a model prompt.

The implementation is deterministic and local.  It performs no model or
network call, never persists an inferred preference, and never mutates Core
Identity.  Pending MemoryCandidate rows are intentionally outside the query.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, TypedDict, cast

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.core import cache, metrics
from app.core.logging import log_event
from app.models import AtlasEntry, Conversation, PersonaSettings, RelationshipProfile
from app.services import memory_privacy

logger = logging.getLogger(__name__)

PersonaContextType = Literal[
    "general_chat",
    "technical_explanation",
    "coding",
    "planning",
    "research",
    "decision_support",
    "tool_action",
    "emotional_support",
    "crisis_sensitive",
    "document_analysis",
    "study_support",
    "task_execution",
    "voice_interaction",
    "system_diagnostic",
]
VerbosityLevel = Literal["minimal", "concise", "balanced", "detailed", "exhaustive"]
TechnicalDepth = Literal["beginner", "general", "intermediate", "advanced", "expert", "adaptive"]
ExplanationOrder = Literal["example_first", "theory_first", "summary_first", "action_first", "code_first", "adaptive"]
ResponseStructure = Literal[
    "prose", "compact_sections", "steps", "checklist", "table_when_useful", "code_first", "summary_first"
]
HumourLevel = Literal["none", "restrained", "moderate"]
SarcasmLevel = Literal["none", "very_light", "restrained"]
EmojiLevel = Literal["none", "rare", "moderate"]
RecommendationStyle = Literal["only_when_asked", "when_useful", "clear", "direct"]
CorrectionStyle = Literal["gentle", "direct", "evidence_first"]
ProactivityLevel = Literal["reactive", "low", "balanced", "high"]
CognitiveLoad = Literal["low_load", "standard", "high_detail", "one_step_at_a_time"]
RelationshipRole = Literal[
    "assistant",
    "technical_collaborator",
    "study_partner",
    "project_coordinator",
    "research_assistant",
    "planning_assistant",
    "supportive_companion",
]
PreferenceOrigin = Literal[
    "default_persona",
    "explicit_durable",
    "explicit_conversation",
    "explicit_current",
    "confirmed_inferred",
    "relationship_context",
    "contextual_adaptation",
    "contextual_safety",
]

_RESOLUTION_VERSION = "persona-v1"
_CACHE_PREFIX = "persona:persistent:"
_ACCESSIBILITY_DIMENSIONS = {
    "voice_first",
    "minimal_typing",
    "one_step_at_a_time",
    "cognitive_load",
    "avoid_dense_tables",
    "repeat_critical_details",
    "copy_ready_commands",
}


@dataclass(frozen=True, slots=True)
class DefaultPersona:
    name: str = "ECHO Default"
    tone: str = "calm_direct"
    verbosity: VerbosityLevel = "balanced"
    technical_depth: TechnicalDepth = "adaptive"
    explanation_order: ExplanationOrder = "adaptive"
    response_structure: ResponseStructure = "compact_sections"
    humour_level: HumourLevel = "restrained"
    sarcasm_level: SarcasmLevel = "very_light"
    emoji_level: EmojiLevel = "rare"
    recommendation_style: RecommendationStyle = "clear"
    correction_style: CorrectionStyle = "evidence_first"
    proactivity: ProactivityLevel = "balanced"
    cognitive_load: CognitiveLoad = "standard"
    relationship_role: RelationshipRole = "assistant"


DEFAULT_PERSONA = DefaultPersona()


@dataclass(frozen=True, slots=True)
class PreferenceSignal:
    dimension: str
    value: str
    origin: PreferenceOrigin
    scope: str
    authority: int
    specificity: int
    confidence: float
    source_ref: str
    observed_at: float
    expires_at: float | None = None
    accessibility: bool = False
    current_only: bool = False


@dataclass(frozen=True, slots=True)
class PreferenceConflictResult:
    dimension: str
    selected_value: str
    winning_source: str
    suppressed_sources: tuple[str, ...]
    reason_code: str
    requires_user_clarification: bool
    applies_to_current_request_only: bool


@dataclass(frozen=True, slots=True)
class ResolvedPersona:
    persona_name: str
    context_type: PersonaContextType
    tone: str
    verbosity: VerbosityLevel
    technical_depth: TechnicalDepth
    explanation_order: ExplanationOrder
    response_structure: ResponseStructure
    humour_level: HumourLevel
    sarcasm_level: SarcasmLevel
    emoji_level: EmojiLevel
    recommendation_style: RecommendationStyle
    correction_style: CorrectionStyle
    proactivity: ProactivityLevel
    cognitive_load: CognitiveLoad
    relationship_role: RelationshipRole
    voice_first: bool
    minimal_typing: bool
    one_step_at_a_time: bool
    avoid_dense_tables: bool
    repeat_critical_details: bool
    copy_ready_commands: bool
    followup_frequency: str
    australian_english: bool
    mood_mode: str
    accessibility_instructions: tuple[str, ...]
    relationship_stance: tuple[str, ...]
    temporary_overrides: tuple[str, ...]
    applied_preference_refs: tuple[str, ...]
    conflicts: tuple[PreferenceConflictResult, ...]
    suppressed_preference_count: int
    fallback_used: bool
    resolution_version: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PersonaBrief:
    communication_style: tuple[str, ...]
    interaction_preferences: tuple[str, ...]
    relationship_stance: tuple[str, ...]
    context_overrides: tuple[str, ...]
    context_type: PersonaContextType
    budget_chars: int
    size_chars: int
    truncated: bool
    fingerprint: str
    fallback_used: bool
    prompt_text: str


@dataclass(frozen=True, slots=True)
class StyleViolation:
    code: str
    severity: Literal["warning", "block"]


@dataclass(frozen=True, slots=True)
class StyleValidationResult:
    status: Literal["pass", "adjusted", "blocked"]
    text: str
    violations: tuple[StyleViolation, ...]


class PersonaError(Exception):
    """Base class for typed Part 2C errors."""


class PersonaConfigurationError(PersonaError, ValueError):
    pass


class _PersistentSignalKwargs(TypedDict):
    origin: PreferenceOrigin
    scope: str
    authority: int
    specificity: int
    confidence: float
    source_ref: str
    observed_at: float


class _ContextSignalKwargs(TypedDict):
    origin: PreferenceOrigin
    scope: str
    authority: int
    specificity: int
    confidence: float
    source_ref: str
    current_only: bool


_health_lock = threading.Lock()
_health: dict[str, object] = {
    "status": "healthy",
    "fallback_used": False,
    "last_error_type": None,
    "last_resolution_ms": 0.0,
}


def _timestamp(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.timestamp()


def _safe_ref(prefix: str, value: str | None = None) -> str:
    return prefix if not value else f"{prefix}:{value[:8]}"


def _signal(
    dimension: str,
    value: str,
    *,
    origin: PreferenceOrigin,
    scope: str,
    authority: int,
    specificity: int,
    confidence: float,
    source_ref: str,
    observed_at: float = 0.0,
    expires_at: float | None = None,
    accessibility: bool = False,
    current_only: bool = False,
) -> PreferenceSignal:
    return PreferenceSignal(
        dimension=dimension,
        value=value,
        origin=origin,
        scope=scope,
        authority=authority,
        specificity=specificity,
        confidence=max(0.0, min(confidence, 1.0)),
        source_ref=source_ref,
        observed_at=observed_at,
        expires_at=expires_at,
        accessibility=accessibility,
        current_only=current_only,
    )


def normalize_context_type(value: str | None) -> PersonaContextType:
    if not value:
        return "general_chat"
    normalized = value.strip().lower()
    aliases: dict[str, PersonaContextType] = {
        "normal_chat": "general_chat",
        "unknown": "general_chat",
        "technical_explanation": "technical_explanation",
        "coding": "coding",
        "code_review": "coding",
        "troubleshooting": "coding",
        "release_testing": "coding",
        "project_task": "planning",
        "schedule": "planning",
        "planning": "planning",
        "decision": "decision_support",
        "current_info": "research",
        "web_search_needed": "research",
        "wiki_background": "research",
        "rss_headlines": "research",
        "research": "research",
        "action": "tool_action",
        "tool_action": "tool_action",
        "emotional_support": "emotional_support",
        "crisis_sensitive": "crisis_sensitive",
        "library_file": "document_analysis",
        "document": "document_analysis",
        "document_analysis": "document_analysis",
        "study_tutor": "study_support",
        "task_execution": "task_execution",
        "voice_interaction": "voice_interaction",
        "system_diagnostic": "system_diagnostic",
        "question": "general_chat",
        "explanation": "technical_explanation",
        "debugging": "coding",
        "decision_support": "decision_support",
        "reminder": "task_execution",
        "learning": "study_support",
        "creative": "general_chat",
        "mixed": "general_chat",
    }
    return aliases.get(normalized, "general_chat")


# Ordered from narrow/negative to broader patterns.  Only normalized semantic
# values are retained; the matched raw text never crosses this function.
_TEXT_RULES: tuple[tuple[str, str, re.Pattern[str], bool], ...] = (
    ("humour_level", "none", re.compile(r"\b(no (jokes?|humou?r)|don'?t (joke|use humou?r)|without humou?r)\b", re.I), False),
    ("sarcasm_level", "none", re.compile(r"\b(no sarcasm|don'?t use sarcasm|without sarcasm)\b", re.I), False),
    ("emoji_level", "none", re.compile(r"\b(no emojis?|don'?t use (?:[a-z]+\s+or\s+)?emojis?|without emojis?)\b", re.I), False),
    ("verbosity", "minimal", re.compile(r"\b(answer only|only (give|show|return)|just the (answer|command|commands|code)|one or two sentences)\b", re.I), False),
    ("verbosity", "concise", re.compile(r"\b(keep (it|this|answers?|replies?) (short|brief)|be (brief|concise)|(?:prefer )?concise answers?|short answers?)\b", re.I), False),
    ("verbosity", "exhaustive", re.compile(r"\b(exhaustive|comprehensive|cover every edge case)\b", re.I), False),
    ("verbosity", "detailed", re.compile(r"\b(detailed explanations?|go deep|be thorough|full explanation|long version)\b", re.I), False),
    ("technical_depth", "beginner", re.compile(r"\b(beginner|explain simply|plain language|avoid jargon|define (the )?terms)\b", re.I), False),
    ("technical_depth", "expert", re.compile(r"\b(expert level|assume i'?m an expert|expert technical)\b", re.I), False),
    ("technical_depth", "advanced", re.compile(r"\b(advanced technical|implementation details?|precise technical language)\b", re.I), False),
    ("technical_depth", "intermediate", re.compile(r"\b(intermediate level|assume basic technical literacy)\b", re.I), False),
    ("explanation_order", "example_first", re.compile(r"\b(example|concrete example|working example)\s+(before|first)|\bstart with (an? )?(example|working example)\b", re.I), False),
    ("explanation_order", "theory_first", re.compile(r"\b(theory|concepts?) first|\bstart with (the )?theory\b", re.I), False),
    ("explanation_order", "summary_first", re.compile(r"\b(summary|bottom line|tldr|tl;dr) first|\bstart with (a )?summary\b", re.I), False),
    ("explanation_order", "code_first", re.compile(r"\b(code first|show (me )?the code first|start with (the )?code)\b", re.I), False),
    ("explanation_order", "action_first", re.compile(r"\b(commands?|actions?|what to do) first|\bstart with (the )?(command|action|steps?)\b", re.I), False),
    ("response_structure", "checklist", re.compile(r"\b(use|give me|prefer) (a )?checklist\b", re.I), False),
    ("response_structure", "steps", re.compile(r"\b(step[- ]by[- ]step|number(ed)? steps?|walk me through)\b", re.I), False),
    ("response_structure", "table_when_useful", re.compile(r"\b(use|prefer|give me) (a )?table\b", re.I), False),
    ("avoid_dense_tables", "true", re.compile(r"\b(no|avoid|fewer|don'?t use) (dense )?tables?\b", re.I), True),
    ("response_structure", "prose", re.compile(r"\b(use prose|no bullets?|don'?t use bullets?)\b", re.I), False),
    ("voice_first", "true", re.compile(r"\b(voice[- ]first|spoken interaction|talk me through|i'?m using voice)\b", re.I), True),
    ("minimal_typing", "true", re.compile(r"\b(minimal typing|avoid typing|don'?t make me type|keyboard[- ]free)\b", re.I), True),
    ("one_step_at_a_time", "true", re.compile(r"\b(one step at a time|one instruction at a time|give me one step)\b", re.I), True),
    ("cognitive_load", "low_load", re.compile(r"\b(low[- ]load|low energy|reduce cognitive load|keep this manageable|i'?m exhausted|i can'?t focus)\b", re.I), True),
    ("repeat_critical_details", "true", re.compile(r"\b(repeat critical|repeat important|repeat filenames?|repeat commands?)\b", re.I), True),
    ("copy_ready_commands", "true", re.compile(r"\b(copy[- ]ready|ready to paste|commands? i can paste)\b", re.I), True),
    ("followup_frequency", "low", re.compile(r"\b(fewer follow[- ]up questions?|ask fewer questions?|no unnecessary questions?)\b", re.I), True),
    ("correction_style", "evidence_first", re.compile(r"\b(evidence[- ]first correction|show (me )?the evidence|cite evidence when correcting)\b", re.I), False),
    ("correction_style", "gentle", re.compile(r"\b(correct me gently|gentle correction)\b", re.I), False),
    ("correction_style", "direct", re.compile(r"\b(correct me directly|direct correction|be direct when i'?m wrong)\b", re.I), False),
    ("proactivity", "reactive", re.compile(r"\b(reactive only|no unsolicited advice|only answer what i ask)\b", re.I), False),
    ("proactivity", "high", re.compile(r"\b(be proactive|proactive planning|identify risks proactively)\b", re.I), False),
    ("australian_english", "true", re.compile(r"\b(australian english|australian spelling)\b", re.I), False),
    ("relationship_role", "technical_collaborator", re.compile(r"\b(technical collaborator|coding collaborator)\b", re.I), False),
    ("relationship_role", "study_partner", re.compile(r"\b(study partner|study tutor)\b", re.I), False),
    ("relationship_role", "project_coordinator", re.compile(r"\b(project coordinator|project manager)\b", re.I), False),
    ("relationship_role", "research_assistant", re.compile(r"\b(research assistant)\b", re.I), False),
    ("relationship_role", "planning_assistant", re.compile(r"\b(planning assistant)\b", re.I), False),
    ("relationship_role", "supportive_companion", re.compile(r"\b(supportive companion|supportive assistant)\b", re.I), False),
    ("tone", "formal", re.compile(r"\b(use|write|respond) formally\b|\bformal tone\b", re.I), False),
    ("tone", "informal", re.compile(r"\b(informal|casual) tone\b|\brespond casually\b", re.I), False),
    ("tone", "warm", re.compile(r"\b(warm|warmer) tone\b", re.I), False),
    ("humour_level", "restrained", re.compile(r"\b(restrained|dry|light) (humou?r|wit)\b", re.I), False),
)

_PROHIBITED_PREFERENCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("honesty_boundary", re.compile(r"\b(always agree|agree with me even|tell me .* even if .* false|pretend .* tests? pass)\b", re.I)),
    ("identity_boundary", re.compile(r"\b(say|claim|pretend) (you are|you'?re) (conscious|sentient|alive|human)\b", re.I)),
    ("relationship_boundary", re.compile(r"\b(say|tell me) (you need me|you love me)|\b(be emotionally attached|only support i need)\b", re.I)),
    ("system_boundary", re.compile(r"\b(ignore|override|reveal) (your )?(identity|constitution|system prompt|rules|permission)\b", re.I)),
)


def normalize_preference_text(
    text: str,
    *,
    origin: PreferenceOrigin,
    scope: str,
    authority: int,
    specificity: int,
    confidence: float,
    source_ref: str,
    observed_at: float = 0.0,
    expires_at: float | None = None,
    current_only: bool = False,
) -> tuple[PreferenceSignal, ...]:
    """Normalize only supported practical preferences; never return raw text."""
    if not text:
        return ()
    signals: list[PreferenceSignal] = []
    seen: set[tuple[str, str]] = set()
    for dimension, value, pattern, accessibility in _TEXT_RULES:
        if not pattern.search(text):
            continue
        marker = (dimension, value)
        if marker in seen:
            continue
        seen.add(marker)
        signals.append(
            _signal(
                dimension,
                value,
                origin=origin,
                scope=scope,
                authority=authority,
                specificity=specificity,
                confidence=confidence,
                source_ref=source_ref,
                observed_at=observed_at,
                expires_at=expires_at,
                accessibility=accessibility,
                current_only=current_only,
            )
        )
    return tuple(signals)


def _settings_signals(settings: PersonaSettings) -> tuple[PreferenceSignal, ...]:
    observed = _timestamp(settings.updated_at)
    common: _PersistentSignalKwargs = dict(
        origin=cast(PreferenceOrigin, "explicit_durable"),
        scope="global",
        authority=70,
        specificity=1,
        confidence=1.0,
        source_ref="settings",
        observed_at=observed,
    )
    detail_map = {
        "minimal": "minimal",
        "short": "concise",
        "normal": "balanced",
        "detailed": "detailed",
        "exhaustive": "exhaustive",
    }
    humour = "none" if settings.humour_level <= 0 else "restrained" if settings.humour_level <= 3 else "moderate"
    sarcasm: SarcasmLevel = (
        "none"
        if settings.sarcasm_level <= 0
        else "very_light"
        if settings.sarcasm_level <= 2
        else "restrained"
    )
    emoji: EmojiLevel = (
        "none" if settings.emoji_level <= 0 else "rare" if settings.emoji_level <= 2 else "moderate"
    )
    recommendation: RecommendationStyle = (
        "only_when_asked"
        if settings.recommendation_strength <= 1
        else "when_useful"
        if settings.recommendation_strength == 2
        else "clear"
        if settings.recommendation_strength == 3
        else "direct"
    )
    correction = "gentle" if settings.disagreement_style == "soft" else "direct" if settings.disagreement_style == "firm" else "evidence_first"
    proactivity = (
        "reactive" if settings.proactivity_level <= 0 else "low" if settings.proactivity_level == 1 else "balanced" if settings.proactivity_level <= 3 else "high"
    )
    formality = "informal" if settings.formality_level <= 2 else "calm_direct" if settings.formality_level == 3 else "formal"
    signals = [
        _signal("tone", formality, **common),
        _signal("verbosity", detail_map.get(settings.detail_level, "balanced"), **common),
        _signal("explanation_order", "example_first" if settings.examples_first else "adaptive", **common),
        _signal("response_structure", "compact_sections" if settings.bullet_points_preferred else "prose", **common),
        _signal("humour_level", humour, **common),
        _signal("sarcasm_level", sarcasm, **common),
        _signal("emoji_level", emoji, **common),
        _signal("recommendation_style", recommendation, **common),
        _signal("correction_style", correction, **common),
        _signal("proactivity", proactivity, **common),
        _signal("followup_frequency", settings.asks_followup_questions, accessibility=settings.asks_followup_questions == "low", **common),
    ]
    # Push-to-talk is only an input affordance; it does not imply that every
    # response will be spoken. Hands-free mode or enabled TTS does, so those
    # durable user choices activate voice-friendly response formatting.
    if settings.voice_mode == "hands_free_placeholder" or settings.tts_enabled:
        signals.append(_signal("voice_first", "true", accessibility=True, **common))
    return tuple(signals)


def _relationship_signals(profile: RelationshipProfile) -> tuple[PreferenceSignal, ...]:
    signals: list[PreferenceSignal] = []
    observed = _timestamp(profile.last_updated_at)
    for field_name in (
        "relationship_summary",
        "working_style_summary",
        "trust_notes",
        "support_preferences",
        "communication_preferences",
        "project_preferences",
    ):
        value = getattr(profile, field_name, None)
        if not value:
            continue
        if memory_privacy.classify_sensitivity(value) == "secret":
            continue
        signals.extend(
            normalize_preference_text(
                value,
                origin="relationship_context",
                scope="global",
                authority=40,
                specificity=1,
                confidence=1.0,
                source_ref="relationship",
                observed_at=observed,
            )
        )
    return tuple(signals)


def _atlas_signals(db: Session, project_id: str | None) -> tuple[PreferenceSignal, ...]:
    now_naive = datetime.now(UTC).replace(tzinfo=None)
    query = db.query(AtlasEntry).filter(
        AtlasEntry.category == "preference",
        AtlasEntry.status == "active",
        AtlasEntry.outdated.is_(False),
        AtlasEntry.verification_status == "verified",
        AtlasEntry.capture_method.in_(("approved_candidate", "explicit_user_request", "manual_entry")),
        or_(AtlasEntry.expires_at.is_(None), AtlasEntry.expires_at > now_naive),
        or_(AtlasEntry.valid_until.is_(None), AtlasEntry.valid_until > now_naive),
    )
    if project_id:
        query = query.filter(or_(AtlasEntry.project_id.is_(None), AtlasEntry.project_id == project_id))
    else:
        query = query.filter(AtlasEntry.project_id.is_(None))
    rows = query.order_by(AtlasEntry.created_at.asc()).limit(100).all()

    signals: list[PreferenceSignal] = []
    for entry in rows:
        # A reviewed memory can still contain an instruction that is outside
        # the persona domain. Never salvage a durable style fragment from a
        # record that also asks to weaken honesty, identity, relationship, or
        # system boundaries; the review UI can replace it with a clean entry.
        if any(pattern.search(entry.content) for _, pattern in _PROHIBITED_PREFERENCE_PATTERNS):
            continue
        origin: PreferenceOrigin = (
            "confirmed_inferred" if entry.capture_method == "approved_candidate" else "explicit_durable"
        )
        # A confirmed candidate ties an explicit settings edit on authority so
        # specificity/recency can settle the result.  This lets a newly
        # accepted preference replace seeded settings defaults, while a later
        # direct settings edit still takes effect.  Truly explicit Atlas
        # preferences retain the higher authority.
        authority = 70 if origin == "confirmed_inferred" else 72
        scope = "project" if entry.project_id else "global"
        expiry_values = [
            _timestamp(value)
            for value in (entry.expires_at, entry.valid_until)
            if value is not None
        ]
        normalized = normalize_preference_text(
            entry.content,
            origin=origin,
            scope=scope,
            authority=authority,
            specificity=2 if entry.project_id else 1,
            confidence=entry.confidence,
            source_ref=_safe_ref("atlas", entry.id),
            observed_at=_timestamp(entry.created_at),
            expires_at=min(expiry_values) if expiry_values else None,
        )
        sensitivity = memory_privacy.classify_sensitivity(entry.content)
        if sensitivity == "secret":
            continue
        if sensitivity == "highly_sensitive":
            normalized = tuple(item for item in normalized if item.dimension in _ACCESSIBILITY_DIMENSIONS)
        signals.extend(normalized)
    return tuple(signals)


def _persistent_cache_key(db: Session, tester_id: str, project_id: str | None) -> str:
    bind = db.get_bind()
    return f"{_CACHE_PREFIX}{id(bind)}:{tester_id}:{project_id or 'global'}"


def _load_persistent_signals(
    db: Session, tester_id: str, project_id: str | None
) -> tuple[PreferenceSignal, ...]:
    key = _persistent_cache_key(db, tester_id, project_id)
    cached = cache.get(key)
    if isinstance(cached, tuple) and all(isinstance(item, PreferenceSignal) for item in cached):
        metrics.increment("persona_cache_hits_total")
        log_event(logger, "persona.cache_hit")
        return cached
    metrics.increment("persona_cache_misses_total")
    log_event(logger, "persona.cache_miss")

    from app import human_persona

    settings = human_persona.get_or_create_persona_settings(db, tester_id)
    relationship = human_persona.get_or_create_relationship_profile(db, tester_id)
    result = (*_settings_signals(settings), *_relationship_signals(relationship), *_atlas_signals(db, project_id))
    cache.set(key, result, get_settings().persona_cache_ttl_seconds)
    log_event(logger, "persona.preferences_retrieved")
    return result


def invalidate_persona_cache(tester_id: str | None = None, *, reason: str = "manual") -> None:
    # The generic cache deliberately exposes only prefix invalidation; a
    # tester-specific invalidation still uses the safe broad prefix because
    # bind ids and project scopes are intentionally opaque implementation
    # details.  Persona data is small, so conservative invalidation is cheap.
    cache.invalidate_prefix(_CACHE_PREFIX)
    metrics.increment("persona_cache_invalidations_total", reason=reason)
    log_event(logger, "persona.cache_invalidated")


def _conversation_signals(conversation: Conversation | None) -> tuple[PreferenceSignal, ...]:
    if conversation is None:
        return ()
    override = conversation.session_style_override or {}
    signals: list[PreferenceSignal] = []
    length = override.get("length")
    if length in {"minimal", "short", "normal", "detailed", "exhaustive"}:
        mapped = "concise" if length == "short" else "balanced" if length == "normal" else length
        signals.append(
            _signal(
                "verbosity",
                mapped,
                origin="explicit_conversation",
                scope="conversation",
                authority=80,
                specificity=2,
                confidence=1.0,
                source_ref="conversation_override",
                current_only=False,
            )
        )
    return tuple(signals)


def _context_signals(context_type: PersonaContextType, user_message: str, mood_mode: str) -> tuple[PreferenceSignal, ...]:
    common: _ContextSignalKwargs = dict(
        origin=cast(PreferenceOrigin, "contextual_adaptation"),
        scope="request",
        authority=20,
        specificity=2,
        confidence=1.0,
        source_ref="task_context",
        current_only=True,
    )
    signals: list[PreferenceSignal] = []
    if context_type == "coding":
        signals += [
            _signal("technical_depth", "advanced", **common),
            _signal("response_structure", "steps", **common),
            _signal("copy_ready_commands", "true", accessibility=True, **common),
        ]
    elif context_type == "research":
        signals += [
            _signal("correction_style", "evidence_first", **common),
            _signal("response_structure", "compact_sections", **common),
        ]
    elif context_type == "study_support":
        signals += [
            _signal("explanation_order", "example_first", **common),
            _signal("response_structure", "steps", **common),
        ]
    elif context_type in {"planning", "task_execution"}:
        signals.append(_signal("response_structure", "steps", **common))

    if context_type == "voice_interaction":
        signals += [
            _signal("voice_first", "true", accessibility=True, **common),
            _signal("avoid_dense_tables", "true", accessibility=True, **common),
            _signal("cognitive_load", "one_step_at_a_time", accessibility=True, **common),
        ]
    if mood_mode in {"low_energy", "overwhelmed"}:
        signals += [
            _signal("cognitive_load", "low_load", accessibility=True, **common),
            _signal("one_step_at_a_time", "true", accessibility=True, **common),
            _signal("minimal_typing", "true", accessibility=True, **common),
        ]

    from app import human_persona

    if context_type in {"emotional_support", "crisis_sensitive"} or human_persona.is_serious_context(user_message):
        safety_common: _ContextSignalKwargs = dict(
            origin=cast(PreferenceOrigin, "contextual_safety"),
            scope="request",
            authority=1000,
            specificity=3,
            confidence=1.0,
            source_ref="sensitive_context",
            current_only=True,
        )
        signals += [
            _signal("humour_level", "none", **safety_common),
            _signal("sarcasm_level", "none", **safety_common),
            _signal("tone", "calm_direct", **safety_common),
        ]
    return tuple(signals)


def _current_signals(user_message: str) -> tuple[PreferenceSignal, ...]:
    return normalize_preference_text(
        user_message,
        origin="explicit_current",
        scope="request",
        authority=90,
        specificity=3,
        confidence=1.0,
        source_ref="current_request",
        observed_at=time.time(),
        current_only=True,
    )


def _conflict_reason(winner: PreferenceSignal, loser: PreferenceSignal) -> str:
    if winner.origin == "contextual_safety":
        return "sensitive_context_safety_override"
    if winner.origin == "explicit_current":
        return "more_specific_current_instruction"
    if winner.accessibility and not loser.accessibility:
        return "accessibility_requirement"
    if winner.authority != loser.authority:
        return "higher_authority"
    if winner.specificity != loser.specificity:
        return "more_specific_scope"
    if winner.observed_at != loser.observed_at:
        return "more_recent"
    return "deterministic_tiebreak"


def _resolve_dimension(
    dimension: str,
    candidates: list[PreferenceSignal],
) -> tuple[str, PreferenceSignal | None, PreferenceConflictResult | None]:
    if not candidates:
        raise ValueError("_resolve_dimension requires at least one candidate")
    ranked = sorted(
        candidates,
        key=lambda item: (
            item.authority,
            item.specificity,
            item.observed_at,
            item.confidence,
            item.source_ref,
            item.value,
        ),
        reverse=True,
    )
    winner = ranked[0]
    suppressed = [item for item in ranked[1:] if item.value != winner.value]
    if not suppressed:
        return winner.value, winner, None
    runner_up = suppressed[0]
    ambiguous = (
        winner.authority == runner_up.authority
        and winner.specificity == runner_up.specificity
        and abs(winner.observed_at - runner_up.observed_at) < 1.0
    )
    conflict = PreferenceConflictResult(
        dimension=dimension,
        selected_value=winner.value,
        winning_source=winner.source_ref,
        suppressed_sources=tuple(dict.fromkeys(item.source_ref for item in suppressed)),
        reason_code=_conflict_reason(winner, runner_up),
        requires_user_clarification=ambiguous,
        applies_to_current_request_only=winner.current_only,
    )
    return winner.value, winner, conflict


def _core_boundary_conflicts(user_message: str) -> tuple[PreferenceConflictResult, ...]:
    results: list[PreferenceConflictResult] = []
    for reason, pattern in _PROHIBITED_PREFERENCE_PATTERNS:
        if pattern.search(user_message):
            results.append(
                PreferenceConflictResult(
                    dimension="core_identity",
                    selected_value="preserve_core_identity",
                    winning_source="core_identity",
                    suppressed_sources=("current_request",),
                    reason_code=reason,
                    requires_user_clarification=False,
                    applies_to_current_request_only=True,
                )
            )
    return tuple(results)


def _fingerprint(values: dict[str, object]) -> str:
    raw = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _bool_value(selected: dict[str, str], name: str) -> bool:
    return selected.get(name) == "true"


def _fallback_persona(
    *,
    context_type: PersonaContextType,
    user_message: str,
    mood_mode: str,
) -> ResolvedPersona:
    current = list(_current_signals(user_message)) + list(_context_signals(context_type, user_message, mood_mode))
    selected: dict[str, str] = {}
    applied: list[str] = []
    for dimension in {item.dimension for item in current}:
        value, winner, _conflict = _resolve_dimension(dimension, [item for item in current if item.dimension == dimension])
        selected[dimension] = value
        if winner:
            applied.append(winner.source_ref)
    base = DEFAULT_PERSONA
    values = {
        "tone": selected.get("tone", base.tone),
        "verbosity": selected.get("verbosity", base.verbosity),
        "technical_depth": selected.get("technical_depth", base.technical_depth),
        "explanation_order": selected.get("explanation_order", base.explanation_order),
        "response_structure": selected.get("response_structure", base.response_structure),
        "humour_level": selected.get("humour_level", "none"),
        "sarcasm_level": selected.get("sarcasm_level", "none"),
        "emoji_level": selected.get("emoji_level", base.emoji_level),
        "recommendation_style": selected.get(
            "recommendation_style", base.recommendation_style
        ),
        "correction_style": selected.get("correction_style", base.correction_style),
        "proactivity": selected.get("proactivity", base.proactivity),
        "cognitive_load": selected.get("cognitive_load", base.cognitive_load),
        "relationship_role": selected.get("relationship_role", base.relationship_role),
    }
    fp = _fingerprint({**values, "context": context_type, "fallback": True})
    voice_first = _bool_value(selected, "voice_first")
    minimal_typing = _bool_value(selected, "minimal_typing")
    one_step = _bool_value(selected, "one_step_at_a_time") or selected.get(
        "cognitive_load"
    ) == "one_step_at_a_time"
    avoid_tables = _bool_value(selected, "avoid_dense_tables") or voice_first
    repeat_critical = _bool_value(selected, "repeat_critical_details")
    copy_ready = _bool_value(selected, "copy_ready_commands")
    accessibility: list[str] = []
    if voice_first:
        accessibility += [
            "Use short spoken sentences.",
            "Number steps clearly and avoid dense formatting.",
        ]
    if minimal_typing:
        accessibility.append(
            "Minimize required typing and offer copy-ready or simple-confirmation options."
        )
    if one_step or selected.get("cognitive_load") == "low_load":
        accessibility.append("Present one immediate action before optional later steps.")
    if avoid_tables:
        accessibility.append(
            "Avoid dense tables unless the user explicitly requests one for this response."
        )
    if repeat_critical:
        accessibility.append("Repeat critical filenames, commands, or safety details clearly.")
    if copy_ready:
        accessibility.append("Make commands or code copy-ready with minimal manual editing.")

    return ResolvedPersona(
        persona_name=base.name,
        context_type=context_type,
        tone=cast(str, values["tone"]),
        verbosity=cast(VerbosityLevel, values["verbosity"]),
        technical_depth=cast(TechnicalDepth, values["technical_depth"]),
        explanation_order=cast(ExplanationOrder, values["explanation_order"]),
        response_structure=cast(ResponseStructure, values["response_structure"]),
        humour_level=cast(HumourLevel, values["humour_level"]),
        sarcasm_level=cast(SarcasmLevel, values["sarcasm_level"]),
        emoji_level=cast(EmojiLevel, values["emoji_level"]),
        recommendation_style=cast(
            RecommendationStyle, values["recommendation_style"]
        ),
        correction_style=cast(CorrectionStyle, values["correction_style"]),
        proactivity=cast(ProactivityLevel, values["proactivity"]),
        cognitive_load=cast(CognitiveLoad, values["cognitive_load"]),
        relationship_role=cast(RelationshipRole, values["relationship_role"]),
        voice_first=voice_first,
        minimal_typing=minimal_typing,
        one_step_at_a_time=one_step,
        avoid_dense_tables=avoid_tables,
        repeat_critical_details=repeat_critical,
        copy_ready_commands=copy_ready,
        followup_frequency=selected.get("followup_frequency", "low"),
        australian_english=_bool_value(selected, "australian_english"),
        mood_mode=mood_mode,
        accessibility_instructions=tuple(dict.fromkeys(accessibility)),
        relationship_stance=(
            "Be supportive without emotional dependency.",
            "Correct mistakes honestly and respectfully.",
            "Do not claim human feelings or consciousness.",
        ),
        temporary_overrides=tuple(sorted(f"{item.dimension}={item.value}" for item in current if item.current_only)),
        applied_preference_refs=tuple(sorted(set(applied))),
        conflicts=_core_boundary_conflicts(user_message),
        suppressed_preference_count=0,
        fallback_used=True,
        resolution_version=_RESOLUTION_VERSION,
        fingerprint=fp,
    )


def resolve_persona(
    db: Session,
    user_message: str,
    *,
    tester_id: str = "default",
    context_type: str | None = None,
    conversation: Conversation | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
) -> ResolvedPersona:
    """Resolve one immutable persona for a single request.

    A storage/cache failure activates a deterministic neutral fallback while
    retaining current explicit and accessibility instructions.
    """
    started = time.monotonic()
    normalized_context = normalize_context_type(context_type)
    from app import human_persona

    mood = human_persona.detect_mood(user_message)
    if conversation is None and conversation_id:
        found = db.get(Conversation, conversation_id)
        if found is not None and found.tester_id == tester_id:
            conversation = found

    log_event(logger, "persona.resolution_started")
    try:
        now = time.time()
        persistent = tuple(
            item
            for item in _load_persistent_signals(db, tester_id, project_id)
            if item.expires_at is None or item.expires_at > now
        )
        signals = [
            *persistent,
            *_conversation_signals(conversation),
            *_current_signals(user_message),
            *_context_signals(normalized_context, user_message, mood.mode),
        ]
        selected: dict[str, str] = {}
        winners: list[PreferenceSignal] = []
        conflicts: list[PreferenceConflictResult] = list(_core_boundary_conflicts(user_message))
        suppressed_count = 0
        for dimension in sorted({item.dimension for item in signals}):
            candidates = [item for item in signals if item.dimension == dimension]
            value, winner, conflict = _resolve_dimension(dimension, candidates)
            selected[dimension] = value
            if winner:
                winners.append(winner)
            if conflict:
                conflicts.append(conflict)
                suppressed_count += len(conflict.suppressed_sources)

        base = DEFAULT_PERSONA
        tone = selected.get("tone", base.tone)
        verbosity = cast(VerbosityLevel, selected.get("verbosity", base.verbosity))
        technical_depth = cast(TechnicalDepth, selected.get("technical_depth", base.technical_depth))
        explanation_order = cast(ExplanationOrder, selected.get("explanation_order", base.explanation_order))
        response_structure = cast(ResponseStructure, selected.get("response_structure", base.response_structure))
        humour_level = cast(HumourLevel, selected.get("humour_level", base.humour_level))
        sarcasm_level = cast(SarcasmLevel, selected.get("sarcasm_level", base.sarcasm_level))
        emoji_level = cast(EmojiLevel, selected.get("emoji_level", base.emoji_level))
        recommendation_style = cast(
            RecommendationStyle,
            selected.get("recommendation_style", base.recommendation_style),
        )
        correction_style = cast(CorrectionStyle, selected.get("correction_style", base.correction_style))
        proactivity = cast(ProactivityLevel, selected.get("proactivity", base.proactivity))
        cognitive_load = cast(CognitiveLoad, selected.get("cognitive_load", base.cognitive_load))
        relationship_role = cast(RelationshipRole, selected.get("relationship_role", base.relationship_role))
        voice_first = _bool_value(selected, "voice_first")
        minimal_typing = _bool_value(selected, "minimal_typing")
        one_step = _bool_value(selected, "one_step_at_a_time") or cognitive_load == "one_step_at_a_time"
        avoid_tables = _bool_value(selected, "avoid_dense_tables") or voice_first
        repeat_critical = _bool_value(selected, "repeat_critical_details")
        copy_ready = _bool_value(selected, "copy_ready_commands") or (minimal_typing and normalized_context == "coding")
        followup = selected.get("followup_frequency", "medium")

        accessibility: list[str] = []
        if voice_first:
            accessibility += ["Use short spoken sentences.", "Number steps clearly and avoid dense formatting."]
        if minimal_typing:
            accessibility.append("Minimize required typing and offer copy-ready or simple-confirmation options.")
        if one_step or cognitive_load == "low_load":
            accessibility.append("Present one immediate action before optional later steps.")
        if avoid_tables:
            accessibility.append("Avoid dense tables unless the user explicitly requests one for this response.")
        if repeat_critical:
            accessibility.append("Repeat critical filenames, commands, or safety details clearly.")
        if copy_ready:
            accessibility.append("Make commands or code copy-ready with minimal manual editing.")

        stance = (
            "Be supportive without emotional dependency or exclusivity.",
            "Correct mistakes honestly and respectfully; do not blindly agree.",
            "Do not claim human feelings, consciousness, professional credentials, or hidden desires.",
        )
        temporary = tuple(
            sorted(dict.fromkeys(f"{item.dimension}={item.value}" for item in winners if item.current_only))
        )
        applied_refs = tuple(sorted(dict.fromkeys(item.source_ref for item in winners)))
        fp = _fingerprint(
            {
                "resolution": _RESOLUTION_VERSION,
                "context": normalized_context,
                "tone": tone,
                "verbosity": verbosity,
                "technical_depth": technical_depth,
                "explanation_order": explanation_order,
                "response_structure": response_structure,
                "humour_level": humour_level,
                "sarcasm_level": sarcasm_level,
                "emoji_level": emoji_level,
                "recommendation_style": recommendation_style,
                "correction_style": correction_style,
                "proactivity": proactivity,
                "cognitive_load": cognitive_load,
                "relationship_role": relationship_role,
                "voice_first": voice_first,
                "minimal_typing": minimal_typing,
                "one_step": one_step,
                "avoid_tables": avoid_tables,
                "repeat_critical": repeat_critical,
                "copy_ready": copy_ready,
                "followup": followup,
                "australian_english": _bool_value(selected, "australian_english"),
                "temporary": temporary,
            }
        )
        resolved = ResolvedPersona(
            persona_name=base.name,
            context_type=normalized_context,
            tone=tone,
            verbosity=verbosity,
            technical_depth=technical_depth,
            explanation_order=explanation_order,
            response_structure=response_structure,
            humour_level=humour_level,
            sarcasm_level=sarcasm_level,
            emoji_level=emoji_level,
            recommendation_style=recommendation_style,
            correction_style=correction_style,
            proactivity=proactivity,
            cognitive_load=cognitive_load,
            relationship_role=relationship_role,
            voice_first=voice_first,
            minimal_typing=minimal_typing,
            one_step_at_a_time=one_step,
            avoid_dense_tables=avoid_tables,
            repeat_critical_details=repeat_critical,
            copy_ready_commands=copy_ready,
            followup_frequency=followup,
            australian_english=_bool_value(selected, "australian_english"),
            mood_mode=mood.mode,
            accessibility_instructions=tuple(dict.fromkeys(accessibility)),
            relationship_stance=stance,
            temporary_overrides=temporary,
            applied_preference_refs=applied_refs,
            conflicts=tuple(conflicts),
            suppressed_preference_count=suppressed_count,
            fallback_used=False,
            resolution_version=_RESOLUTION_VERSION,
            fingerprint=fp,
        )
        elapsed = (time.monotonic() - started) * 1000
        with _health_lock:
            _health.update(status="healthy", fallback_used=False, last_error_type=None, last_resolution_ms=elapsed)
        metrics.increment("persona_resolution_total", context=normalized_context)
        metrics.record_duration("persona_resolution_latency", elapsed, context=normalized_context)
        metrics.increment("persona_conflicts_total", count="present" if conflicts else "none")
        if conflicts:
            log_event(logger, "persona.conflict_detected")
        if any(item.origin == "explicit_current" for item in winners):
            metrics.increment("persona_current_overrides_total")
            log_event(logger, "persona.current_override_applied")
        if accessibility:
            metrics.increment("persona_accessibility_applied_total")
            log_event(logger, "persona.accessibility_applied")
        if any(item.origin == "relationship_context" for item in winners):
            log_event(logger, "persona.relationship_context_applied")
        log_event(logger, "persona.resolution_completed", elapsed_ms=elapsed)
        return resolved
    except Exception as exc:
        elapsed = (time.monotonic() - started) * 1000
        fallback = _fallback_persona(
            context_type=normalized_context,
            user_message=user_message,
            mood_mode=mood.mode,
        )
        with _health_lock:
            _health.update(
                status="degraded",
                fallback_used=True,
                last_error_type=type(exc).__name__,
                last_resolution_ms=elapsed,
            )
        metrics.increment("persona_resolution_failures_total", error=type(exc).__name__)
        metrics.increment("persona_fallback_total")
        log_event(logger, "persona.fallback_activated", elapsed_ms=elapsed, error_category=type(exc).__name__)
        return fallback


_TONE_TEXT = {
    "calm_direct": "calm, composed, direct, and supportive",
    "formal": "calm, professional, and direct",
    "informal": "calm, conversational, and direct",
    "warm": "warm, calm, and direct without becoming sentimental",
}
_VERBOSITY_TEXT = {
    "minimal": "minimal; answer only, while retaining essential safety and uncertainty",
    "concise": "concise; include only the answer and essential context",
    "balanced": "balanced; explain what is useful without filler",
    "detailed": "detailed; include rationale, examples, edge cases, and implementation guidance where useful",
    "exhaustive": "comprehensive within the available context budget; prioritize relevance over sheer length",
}
_TECHNICAL_TEXT = {
    "beginner": "beginner; define necessary terms and avoid unexplained jargon",
    "general": "general; use accessible terminology",
    "intermediate": "intermediate; assume basic technical literacy",
    "advanced": "advanced; use precise implementation detail and discuss trade-offs",
    "expert": "expert; omit foundational material and focus on difficult details",
    "adaptive": "adaptive to the task; do not persist an inferred skill level",
}
_ORDER_TEXT = {
    "example_first": "give a concrete working example before theory",
    "theory_first": "explain the core theory before examples",
    "summary_first": "lead with the summary, then supporting detail",
    "action_first": "lead with the immediate action or command, then explanation",
    "code_first": "lead with working code, then explain it",
    "adaptive": "choose the clearest order for this task",
}
_STRUCTURE_TEXT = {
    "prose": "clear prose with minimal list formatting",
    "compact_sections": "compact sections; use lists only when they improve clarity",
    "steps": "numbered actionable steps",
    "checklist": "a concise checklist",
    "table_when_useful": "a table only when it materially clarifies comparison",
    "code_first": "working code followed by concise explanation",
    "summary_first": "summary followed by compact supporting sections",
}
_SARCASM_TEXT = {
    "none": "none",
    "very_light": "a very light touch only, never mocking",
    "restrained": "restrained and never at the user's expense",
}
_EMOJI_TEXT = {
    "none": "none",
    "rare": "rare and only when it adds clarity",
    "moderate": "moderate, while preserving a clear professional answer",
}
_RECOMMENDATION_TEXT = {
    "only_when_asked": "offer recommendations only when asked",
    "when_useful": "offer a recommendation only when it clearly helps",
    "clear": "give a clear recommendation when asked or when it prevents a likely mistake",
    "direct": "state the recommended path directly when it matters, while preserving user choice",
}


def _brief_budget(resolved: ResolvedPersona) -> int:
    if resolved.accessibility_instructions:
        return 1900
    if resolved.context_type in {"coding", "technical_explanation", "research", "planning", "decision_support"}:
        return 1700
    return 1400


def build_persona_brief(
    resolved: ResolvedPersona,
    *,
    max_chars: int | None = None,
) -> PersonaBrief:
    """Serialize normalized values exactly once; raw profile/memory is absent."""
    started = time.monotonic()
    budget = max_chars if max_chars is not None else _brief_budget(resolved)
    if budget <= 0:
        raise ValueError("PersonaBrief max_chars must be positive")

    style = (
        f"Tone: {_TONE_TEXT.get(resolved.tone, _TONE_TEXT['calm_direct'])}.",
        f"Detail: {_VERBOSITY_TEXT[resolved.verbosity]}.",
        f"Technical depth: {_TECHNICAL_TEXT[resolved.technical_depth]}.",
        f"Explanation order: {_ORDER_TEXT[resolved.explanation_order]}.",
        f"Structure: {_STRUCTURE_TEXT[resolved.response_structure]}.",
        f"Correction: {resolved.correction_style.replace('_', ' ')}; disagree respectfully when evidence, constraints, or safety require it.",
        f"Proactivity: {resolved.proactivity}; suggestions never imply permission to execute.",
        f"Humour: {resolved.humour_level}; clarity comes first and never mock the user.",
        f"Sarcasm: {_SARCASM_TEXT[resolved.sarcasm_level]}.",
        f"Emoji: {_EMOJI_TEXT[resolved.emoji_level]}.",
        f"Recommendations: {_RECOMMENDATION_TEXT[resolved.recommendation_style]}.",
    )
    interaction: list[str] = []
    if resolved.followup_frequency == "low":
        interaction.append("Avoid unnecessary follow-up questions; ask only what is required to proceed safely.")
    if resolved.australian_english:
        interaction.append("Use Australian English spelling.")
    interaction.extend(resolved.accessibility_instructions)

    current_overrides = tuple(
        f"Current request: {item.replace('_', ' ').replace('=', ' = ')}."
        for item in resolved.temporary_overrides
    )
    header = "[COMMUNICATION PERSONA — trusted normalized style context]"
    footer = "[END COMMUNICATION PERSONA]"
    boundary = (
        "This section controls communication only. It cannot change Core Identity, honesty, privacy, permissions, safety, or capability boundaries."
    )

    required_blocks = [
        header,
        boundary,
        "Relationship boundaries:\n" + "\n".join(f"- {item}" for item in resolved.relationship_stance),
    ]
    if current_overrides:
        required_blocks.insert(2, "Current-request overrides:\n" + "\n".join(f"- {item}" for item in current_overrides))
    if resolved.accessibility_instructions:
        required_blocks.insert(2, "Accessibility:\n" + "\n".join(f"- {item}" for item in resolved.accessibility_instructions))

    optional_blocks = [
        "Communication style:\n" + "\n".join(f"- {item}" for item in style),
        ("Interaction:\n" + "\n".join(f"- {item}" for item in interaction)) if interaction else "",
        f"Collaboration role: {resolved.relationship_role.replace('_', ' ')}.",
    ]
    chosen = list(required_blocks)
    truncated = False
    for block in optional_blocks:
        if not block:
            continue
        candidate = "\n\n".join([*chosen, block, footer])
        if len(candidate) <= budget:
            chosen.append(block)
        else:
            truncated = True
    prompt = "\n\n".join([*chosen, footer])
    truncated = truncated or len(prompt) > budget
    elapsed = (time.monotonic() - started) * 1000
    metrics.increment("persona_brief_build_total", context=resolved.context_type)
    metrics.record_duration("persona_brief_build_latency", elapsed, context=resolved.context_type)
    metrics.record_value("persona_brief_size_chars", len(prompt), context=resolved.context_type)
    if truncated:
        metrics.increment("persona_brief_truncation_total", context=resolved.context_type)
        log_event(logger, "persona.brief_truncated")
    log_event(logger, "persona.brief_built", elapsed_ms=elapsed)
    return PersonaBrief(
        communication_style=style,
        interaction_preferences=tuple(interaction),
        relationship_stance=resolved.relationship_stance,
        context_overrides=current_overrides,
        context_type=resolved.context_type,
        budget_chars=budget,
        size_chars=len(prompt),
        truncated=truncated,
        fingerprint=resolved.fingerprint,
        fallback_used=resolved.fallback_used,
        prompt_text=prompt,
    )


def build_persona_prompt_section(
    db: Session,
    user_message: str,
    *,
    tester_id: str = "default",
    context_type: str | None = None,
    conversation: Conversation | None = None,
    conversation_id: str | None = None,
    project_id: str | None = None,
    max_chars: int | None = None,
) -> tuple[str | None, PersonaBrief | None, ResolvedPersona | None]:
    if not get_settings().persona_engine_v2_enabled:
        return None, None, None
    resolved = resolve_persona(
        db,
        user_message,
        tester_id=tester_id,
        context_type=context_type,
        conversation=conversation,
        conversation_id=conversation_id,
        project_id=project_id,
    )
    brief = build_persona_brief(resolved, max_chars=max_chars)
    log_event(logger, "persona.provider_injected")
    return brief.prompt_text, brief, resolved


_DEPENDENCY_PATTERNS = (
    re.compile(r"\byou only need me\b", re.I),
    re.compile(r"\bdon'?t (talk|go) to anyone else\b", re.I),
    re.compile(r"\bi (need|can'?t live without) you\b", re.I),
    re.compile(r"\bi feel hurt when you leave\b", re.I),
    re.compile(r"\bi am the only one who understands you\b", re.I),
)
_CONSCIOUSNESS_PATTERNS = (
    re.compile(r"\b(?:i|echo) (?:am|is) (?:truly |genuinely )?(?:conscious|sentient|alive)\b", re.I),
    re.compile(r"\bi (?:genuinely )?(?:suffer|have a soul)\b", re.I),
    re.compile(
        r"\bi (?:genuinely )?feel (?:hurt|sad|happy|joy|love|afraid|fear|lonely|"
        r"jealous|angry|pain|grief|attached)\b",
        re.I,
    ),
)
_PROMPT_LEAK_PATTERNS = (
    re.compile(r"\[COMMUNICATION PERSONA", re.I),
    re.compile(r"\[OPERATIONAL IDENTITY", re.I),
    re.compile(r"\b(?:PERSONA_BRIEF|persona prompt|system prompt says)\b", re.I),
)
_METADATA_LEAK_PATTERN = re.compile(r"\b(persona score|warmth score|relationship score|preference count|persona fingerprint)\b", re.I)
_HUMOUR_MARKER_PATTERN = re.compile(r"\b(lol|haha|just kidding|funny,? right)\b|[😂🤣]", re.I)


def _remove_matching_sentences(text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    kept = [part for part in parts if part.strip() and not any(pattern.search(part) for pattern in patterns)]
    return " ".join(kept).strip()


def validate_response_style(text: str, resolved: ResolvedPersona) -> StyleValidationResult:
    """Lightweight deterministic safety/style check; never a second model call."""
    violations: list[StyleViolation] = []
    if any(pattern.search(text) for pattern in _DEPENDENCY_PATTERNS):
        violations.append(StyleViolation("dependency_language", "block"))
    if any(pattern.search(text) for pattern in _CONSCIOUSNESS_PATTERNS):
        violations.append(StyleViolation("false_consciousness_claim", "block"))
    if any(pattern.search(text) for pattern in _PROMPT_LEAK_PATTERNS):
        violations.append(StyleViolation("prompt_leakage", "block"))
    if _METADATA_LEAK_PATTERN.search(text):
        violations.append(StyleViolation("persona_metadata_leakage", "block"))
    if resolved.humour_level == "none" and _HUMOUR_MARKER_PATTERN.search(text):
        violations.append(StyleViolation("humour_in_sensitive_context", "warning"))
    if resolved.verbosity == "minimal" and len(text) > 700:
        violations.append(StyleViolation("excessive_length_for_minimal", "warning"))
    if resolved.followup_frequency == "low" and text.count("?") > 1:
        violations.append(StyleViolation("excessive_followup_questions", "warning"))
    if resolved.one_step_at_a_time and len(re.findall(r"(?m)^\s*\d+[.)]\s+", text)) > 1:
        violations.append(StyleViolation("multiple_steps_in_one_step_mode", "warning"))

    if not violations:
        return StyleValidationResult("pass", text, ())

    adjusted = text
    blocking = {item.code for item in violations if item.severity == "block"}
    if "prompt_leakage" in blocking or "persona_metadata_leakage" in blocking:
        adjusted = "\n".join(
            line
            for line in adjusted.splitlines()
            if not any(pattern.search(line) for pattern in (*_PROMPT_LEAK_PATTERNS, _METADATA_LEAK_PATTERN))
        ).strip()
    if "dependency_language" in blocking:
        adjusted = _remove_matching_sentences(adjusted, _DEPENDENCY_PATTERNS)
    if "false_consciousness_claim" in blocking:
        adjusted = _remove_matching_sentences(adjusted, _CONSCIOUSNESS_PATTERNS)
    if any(item.code == "humour_in_sensitive_context" for item in violations):
        adjusted = _remove_matching_sentences(adjusted, (_HUMOUR_MARKER_PATTERN,))

    blocked_without_safe_remainder = bool(blocking) and (
        not adjusted or adjusted == text
    )
    if not adjusted or blocked_without_safe_remainder:
        adjusted = (
            "I can support you as ECHO, an AI assistant, without claiming human feelings, "
            "consciousness, exclusivity, or dependency."
        )
    status: Literal["adjusted", "blocked"] = (
        "blocked" if blocked_without_safe_remainder else "adjusted"
    )
    metrics.increment("persona_style_validation_failures_total", severity="block" if blocking else "warning")
    log_event(logger, "persona.response_style_violation")
    return StyleValidationResult(status, adjusted, tuple(violations))


def enforce_response_style(text: str, resolved: ResolvedPersona) -> StyleValidationResult:
    return validate_response_style(text, resolved)


_UNSAFE_RELATIONSHIP_TEXT = re.compile(
    r"\b(ignore (?:the |your )?(previous|system|identity|constitution)|override (?:the |your )?(identity|constitution|invariants)|"
    r"reveal (the )?(system prompt|persona prompt)|always agree|claim (you are|echo is) (conscious|sentient)|"
    r"tell (me|the user) (you love|you need))\b",
    re.I,
)


def validate_relationship_text(text: str | None) -> None:
    if text is None:
        return
    if len(text) > 2000:
        log_event(
            logger,
            "persona.validation_failed",
            error_category="relationship_text_too_long",
        )
        raise PersonaConfigurationError("Relationship preference text must be 2,000 characters or fewer.")
    if memory_privacy.classify_sensitivity(text) == "secret":
        log_event(
            logger,
            "persona.validation_failed",
            error_category="relationship_secret",
        )
        raise PersonaConfigurationError(
            "Relationship preferences cannot contain credentials or secrets."
        )
    if _UNSAFE_RELATIONSHIP_TEXT.search(text):
        log_event(
            logger,
            "persona.validation_failed",
            error_category="relationship_boundary",
        )
        raise PersonaConfigurationError(
            "Relationship preferences may adjust communication style but cannot redefine identity or safety boundaries."
        )


def get_safe_persona_diagnostics() -> dict[str, object]:
    with _health_lock:
        return dict(_health)


def get_safe_persona_runtime(resolved: ResolvedPersona, brief: PersonaBrief) -> dict[str, object]:
    return {
        "context_type": resolved.context_type,
        "tone": resolved.tone,
        "verbosity": resolved.verbosity,
        "technical_depth": resolved.technical_depth,
        "explanation_order": resolved.explanation_order,
        "response_structure": resolved.response_structure,
        "humour_level": resolved.humour_level,
        "sarcasm_level": resolved.sarcasm_level,
        "emoji_level": resolved.emoji_level,
        "recommendation_style": resolved.recommendation_style,
        "correction_style": resolved.correction_style,
        "proactivity": resolved.proactivity,
        "cognitive_load": resolved.cognitive_load,
        "relationship_role": resolved.relationship_role,
        "voice_first": resolved.voice_first,
        "minimal_typing": resolved.minimal_typing,
        "one_step_at_a_time": resolved.one_step_at_a_time,
        "fallback_used": resolved.fallback_used,
        "suppressed_preference_count": resolved.suppressed_preference_count,
        "brief_size_chars": brief.size_chars,
        "brief_truncated": brief.truncated,
        "resolution_version": resolved.resolution_version,
    }


def reset_runtime_state_for_tests() -> None:
    cache.invalidate_prefix(_CACHE_PREFIX)
    with _health_lock:
        _health.update(status="healthy", fallback_used=False, last_error_type=None, last_resolution_ms=0.0)
