from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EpistemicStatus = Literal["Verified", "Inferred", "Hypothesis", "Narrative"]
MemoryType = Literal[
    "fact", "preference", "mood", "goal", "fear", "capability", "project", "relationship", "event"
]

# ---- ECHO Layer 1: Memory Foundation v1 enums (see AtlasEntry/MemoryCandidate) ----
MemoryCategory = Literal[
    "profile", "preference", "project", "task", "episodic", "semantic",
    "skill", "relationship", "environment", "temporary",
]
VerificationStatus = Literal[
    "verified", "partially_verified", "unverified", "disputed", "outdated", "not_applicable"
]
MemoryImportance = Literal["critical", "high", "medium", "low"]
MemoryStability = Literal["durable", "semi_stable", "volatile", "temporary"]
RetentionPolicy = Literal[
    "permanent_until_deleted", "periodic_review", "expire_after_period",
    "conversation_only", "project_lifetime", "manual_only",
]
CaptureMethod = Literal[
    "explicit_user_request", "approved_candidate", "manual_entry", "project_import",
    "document_extraction", "conversation_summary", "system_generated", "migration",
]
MemoryLifecycleStatus = Literal["active", "pending_review", "archived", "superseded", "rejected", "deleted"]
MemoryReviewState = Literal["none", "pending_review", "reviewed"]
SensitivityLevel = Literal["public", "ordinary_personal", "private", "highly_sensitive", "secret"]
CandidateRecommendation = Literal[
    "auto_accept", "ask_user", "merge", "update_existing", "ignore", "reject_sensitive", "temporary_only"
]
RelationshipType = Literal[
    "related_to", "part_of", "belongs_to_project", "supports", "contradicts", "supersedes",
    "derived_from", "depends_on", "caused_by", "preference_for", "skill_for", "person_related_to",
    "task_related_to", "evidence_for", "example_of", "version_of", "duplicates",
    "temporal_predecessor", "temporal_successor",
]
ConflictType = Literal[
    "direct_contradiction", "temporal_update", "scope_conflict", "source_disagreement",
    "user_preference_change", "project_version_conflict", "identity_ambiguity",
    "confidence_conflict", "environment_drift",
]
ConflictSeverity = Literal["low", "medium", "high", "critical"]
ConflictStatus = Literal["open", "auto_resolved", "user_review_required", "resolved", "ignored"]
ConsolidationAction = Literal[
    "keep_both", "merge", "update_existing", "supersede_existing",
    "reject_duplicate", "ask_user", "create_summary_memory",
]
Role = Literal["founder", "guardian_a", "guardian_b", "guardian_c", "verifier"]
VoteDecision = Literal["approve", "reject"]
# Needed early — PersonaSettingsOut (below) references it directly as a
# field type, so it must be defined before that class body executes.
AnswerQualityMode = Literal["fast", "balanced", "deep"]
# Same reason — PersonaSettingsOut also references this one directly.
VoiceMode = Literal["off", "push_to_talk", "hands_free_placeholder"]


# ---- Chat ----
class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    provider: str = "auto"
    # Lightweight tester identity (Human Persona Layer v1) — normally supplied via
    # the X-Tester-Id header (see app/tester.py); this field exists for API callers
    # (docs, tests) that prefer body-level control. The header wins if both are set.
    tester_id: str | None = None


class AtlasCitation(BaseModel):
    id: str
    content: str
    epistemic_status: EpistemicStatus
    confidence: float


class ConversationSnippetOut(BaseModel):
    """A short excerpt from a PAST conversation (not the current one) — raw
    history, distinct from a distilled Atlas memory. See app/conversation_search.py."""

    message_id: str
    conversation_id: str
    conversation_title: str
    role: str
    created_at: datetime | None
    snippet: str
    relevance: float | None = None

    model_config = {"from_attributes": True}


class MemoryUpdate(BaseModel):
    saved: bool
    explicit: bool
    # True when an implicit (auto-extracted) memory was queued as a MemoryCandidate
    # for review rather than saved directly — see app/routers/memory_candidates.py.
    # Explicit "remember that..." requests still save directly (saved=True), same
    # as before; this only applies to the opportunistic extraction path.
    pending_review: bool = False
    content: str | None = None
    error: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    content: str
    reasoning: str | None = None
    provider_used: str
    atlas_citations: list[AtlasCitation] = Field(default_factory=list)
    memory_update: MemoryUpdate | None = None
    fallback_note: str | None = None
    independence_nudge_reason: str | None = None
    conversation_snippets: list[ConversationSnippetOut] = Field(default_factory=list)
    envelope_status: str = "missing"
    envelope_degradation_reason: str | None = None
    sources_used: list[dict] = Field(default_factory=list)
    current_info_intent: str | None = None
    search_failure_reason: str | None = None


class AttachmentOut(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int
    understood: bool
    analysis_status: str = "stored"
    generated: bool = False
    base64_preview: str | None = None

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    reasoning: str | None
    provider: str | None
    atlas_citations: list[dict]
    attachments: list[AttachmentOut] = Field(default_factory=list)
    fallback_note: str | None = None
    independence_nudge_reason: str | None = None
    conversation_snippets: list[dict] = Field(default_factory=list)
    envelope_status: str = "missing"
    envelope_degradation_reason: str | None = None
    sources_used: list[dict] = Field(default_factory=list)
    current_info_intent: str | None = None
    search_failure_reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SendWithFilesResponse(BaseModel):
    conversation_id: str
    message: MessageOut


class ConversationOut(BaseModel):
    id: str
    title: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut]


class WelcomeResponse(BaseModel):
    greeting: str
    # Atlas has no separate "title" field for entries (just `content`), so these are
    # truncated content excerpts standing in for titles.
    referenced_memories: list[str] = Field(default_factory=list)


class DeleteConversationResponse(BaseModel):
    ok: bool
    deleted_id: str


class ConversationSearchResult(BaseModel):
    conversation_id: str
    title: str
    snippet: str
    matched_role: Literal["user", "echo", "title"]
    updated_at: datetime


class ProviderUsageOut(BaseModel):
    requests_today: int
    last_429_at: datetime | None = None


class VerificationCheckOut(BaseModel):
    command: str
    status: str  # "passed" | "failed" | "unavailable"
    exit_code: int | None = None
    stdout_summary: str = ""
    stderr_summary: str = ""
    timestamp: str


class SelfImprovementRequestOut(BaseModel):
    id: str
    title: str
    description: str
    proposed_by: str
    status: str
    patch_summary: str | None = None
    verification_status: str = "pending"
    verification_notes: str | None = None
    verification_checks: list[VerificationCheckOut] = Field(default_factory=list)
    verified_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SelfImprovementRequestCreate(BaseModel):
    title: str
    description: str
    proposed_by: str = "founder"


class SelfImprovementRequestApprove(BaseModel):
    approved: bool
    note: str | None = None


# ---- Atlas ----
class AtlasEntryCreate(BaseModel):
    content: str
    epistemic_status: EpistemicStatus = "Hypothesis"
    memory_type: MemoryType = "fact"
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(0.5, ge=0.0, le=1.0)
    source: str | None = None
    valid_until: datetime | None = None
    # ECHO Layer 1 (all optional — a caller that doesn't know about these gets
    # the model's own defaults, same backward-compatible pattern as memory_type).
    category: MemoryCategory | None = None
    importance: MemoryImportance | None = None
    stability: MemoryStability | None = None
    retention_policy: RetentionPolicy | None = None
    capture_method: CaptureMethod | None = None
    project_id: str | None = None
    task_id: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    expires_at: datetime | None = None


class AtlasEntryUpdate(BaseModel):
    content: str | None = None
    epistemic_status: EpistemicStatus | None = None
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    source: str | None = None
    valid_until: datetime | None = None
    outdated: bool | None = None
    # ECHO Layer 1
    category: MemoryCategory | None = None
    verification_status: VerificationStatus | None = None
    importance: MemoryImportance | None = None
    stability: MemoryStability | None = None
    retention_policy: RetentionPolicy | None = None
    expires_at: datetime | None = None
    status: MemoryLifecycleStatus | None = None
    project_id: str | None = None
    task_id: str | None = None


class AtlasEntryOut(BaseModel):
    id: str
    content: str
    epistemic_status: EpistemicStatus
    memory_type: MemoryType
    tags: list[str]
    confidence: float
    source: str | None
    observed_at: datetime
    valid_until: datetime | None
    outdated: bool = False
    created_at: datetime
    updated_at: datetime
    # ECHO Layer 1
    category: MemoryCategory = "semantic"
    verification_status: VerificationStatus = "unverified"
    importance: MemoryImportance = "medium"
    stability: MemoryStability = "semi_stable"
    retention_policy: RetentionPolicy = "periodic_review"
    capture_method: CaptureMethod = "migration"
    status: MemoryLifecycleStatus = "active"
    review_state: MemoryReviewState = "none"
    project_id: str | None = None
    task_id: str | None = None
    source_type: str | None = None
    source_reference: str | None = None
    expires_at: datetime | None = None
    last_verified_at: datetime | None = None
    last_accessed_at: datetime | None = None
    access_count: int = 0
    parent_memory_id: str | None = None
    supersedes_memory_id: str | None = None
    contradiction_group_id: str | None = None
    duplicate_group_id: str | None = None

    model_config = {"from_attributes": True}


class AtlasSearchResult(AtlasEntryOut):
    distance: float | None = None


class AtlasMergeRequest(BaseModel):
    keep_id: str
    remove_id: str
    merged_content: str | None = None


# ---- Memory extraction diagnostics (Goal 7) ----
class MemoryExtractionLogOut(BaseModel):
    id: str
    conversation_id: str | None
    message_id: str | None
    explicit_request: bool
    memory_block_present: bool
    was_none: bool
    json_detected: bool
    parse_succeeded: bool
    saved: bool
    rejection_reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---- Memory candidates (Goal 8) ----
MemoryCandidateStatus = Literal["pending", "accepted", "rejected"]


class MemoryCandidateOut(BaseModel):
    id: str
    content: str
    epistemic_status: EpistemicStatus
    memory_type: MemoryType
    tags: list[str]
    confidence: float
    source: str | None
    conversation_id: str | None
    status: MemoryCandidateStatus
    conflict_with: list[str]
    review_note: str | None
    created_at: datetime
    updated_at: datetime
    # ECHO Layer 1
    category: MemoryCategory | None = None
    sensitivity_level: SensitivityLevel = "ordinary_personal"
    recommendation: CandidateRecommendation | None = None
    capture_reason: str | None = None
    duplicate_memory_id: str | None = None
    importance: MemoryImportance = "medium"
    stability: MemoryStability = "semi_stable"

    model_config = {"from_attributes": True}


class MemoryCandidateEdit(BaseModel):
    content: str | None = None
    epistemic_status: EpistemicStatus | None = None
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class MemoryCandidateDecision(BaseModel):
    note: str | None = None


# ---- ECHO Layer 1: Memory Foundation v1 — routers/memory.py schemas ----
class MemorySearchRequest(BaseModel):
    query: str
    project_id: str | None = None
    task_id: str | None = None
    allowed_categories: list[MemoryCategory] | None = None
    excluded_categories: list[MemoryCategory] | None = None
    max_results: int = Field(5, ge=1, le=50)
    include_archived: bool = False
    minimum_confidence: float = Field(0.0, ge=0.0, le=1.0)
    purpose: str = "general"


class MemorySearchResultOut(BaseModel):
    memory_id: str
    content: str
    category: MemoryCategory
    relevance_score: float
    confidence: float
    verification_status: VerificationStatus
    provenance_summary: str
    freshness_status: str
    conflict_warning: str | None
    retrieval_reason: str
    epistemic_status: EpistemicStatus
    tags: list[str]


class MemoryConflictOut(BaseModel):
    id: str
    memory_ids_json: list[str]
    conflict_type: ConflictType
    description: str
    severity: ConflictSeverity
    status: ConflictStatus
    recommended_resolution: str | None
    resolution: str | None
    resolved_by: str | None
    resolved_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConflictResolveRequest(BaseModel):
    resolution: str


class MemoryMaintenanceResultOut(BaseModel):
    checked: int
    expired: int
    needs_review: int
    run_at: str


class MemoryIndexStatusOut(BaseModel):
    backend: str
    collection: str
    embedding_model: str
    persist_dir: str
    healthy: bool
    error: str | None
    sql_row_count: int
    indexed_count: int
    in_sync: bool


FeedbackType = Literal[
    "useful", "irrelevant", "incorrect", "outdated", "too_sensitive", "overused", "underused", "wrong_scope"
]


class MemoryFeedbackRequest(BaseModel):
    feedback_type: FeedbackType
    conversation_id: str | None = None
    scope: str | None = None
    reason: str | None = None


class MemoryFeedbackOut(BaseModel):
    id: str
    memory_id: str
    conversation_id: str | None
    feedback_type: FeedbackType
    scope: str | None
    reason: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryMetricsOut(BaseModel):
    retrieval_counters: dict[str, int]
    provenance_coverage_pct: float
    verification_coverage_pct: float
    stale_memory_pct: float
    unresolved_conflict_pct: float
    duplicate_consolidation_events: int
    total_active: int


class MemoryStatsOut(BaseModel):
    total_active: int
    by_category: dict[str, int]
    by_status: dict[str, int]
    pending_candidates: int
    accepted_candidates: int
    rejected_candidates: int
    open_conflicts: int
    resolved_conflicts: int
    consolidation_events: int


# ---- Constitution ----
class ValueInvariantOut(BaseModel):
    id: str
    text: str


class CoreValueOut(BaseModel):
    rank: int
    name: str
    description: str


class EdgeCaseProtocolOut(BaseModel):
    id: str
    scenario: str
    resolution: str


class AmendmentLogEntryOut(BaseModel):
    id: str
    title: str
    text: str
    ratified_at: datetime | None


class ConstitutionOut(BaseModel):
    version: str
    codename: str
    philosophy: str
    core_values: list[CoreValueOut]
    value_invariants: list[ValueInvariantOut]
    edge_case_protocols: list[EdgeCaseProtocolOut]
    amendment_log: list[AmendmentLogEntryOut]
    full_text: str


# ---- Amendments ----
class AmendmentProposeRequest(BaseModel):
    title: str
    text: str
    rationale: str | None = None
    proposed_by: Role = "founder"


class VoteRequest(BaseModel):
    role: Role
    decision: VoteDecision
    comment: str | None = None


class VoteOut(BaseModel):
    role: str
    decision: str
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AmendmentOut(BaseModel):
    id: str
    title: str
    text: str
    rationale: str | None
    proposed_by: str
    status: str
    created_at: datetime
    decided_at: datetime | None
    votes: list[VoteOut]
    tally: dict

    model_config = {"from_attributes": True}


# ---- Models ----
class ProviderStatus(BaseModel):
    name: str
    label: str
    available: bool
    reason: str | None = None


class VisionAvailability(BaseModel):
    available: bool
    provider: str
    reason: str | None = None


class ImageGenerationAvailability(BaseModel):
    available: bool
    active_provider: str | None = None
    reason: str | None = None
    providers: dict[str, str]  # "gemini"/"ollama"/"comfyui" -> short reason or "available"


class FeatureAvailability(BaseModel):
    chat: bool
    voice_input: bool
    file_upload: bool
    image_generation: bool  # kept for backward compatibility — mirrors image_generation_detail.available
    vision: VisionAvailability
    image_generation_detail: ImageGenerationAvailability
    providers: dict[str, str]  # provider name -> "available" | "not_configured" | "unavailable"
    # Config-level flags (WEB_SEARCH_ENABLED/WIKI_SEARCH_ENABLED/RSS_SEARCH_ENABLED),
    # not live reachability — a per-turn failure (SearXNG down, no results) still
    # surfaces honestly via that message's own search_failure_reason. These just let
    # the UI show "search sources currently configured" without waiting for a chat
    # turn to find out. Library/Schedule aren't included: they're plain CRUD with no
    # external dependency, so there's no "unavailable" state to report for them.
    web_search_enabled: bool = False
    wiki_enabled: bool = False
    rss_enabled: bool = False
    # Plain CRUD, same rationale as voice_input/file_upload above — no
    # external dependency, so always true; included so a caller checking
    # "is library/schedule enabled" doesn't need a special case.
    library: bool = True
    schedule: bool = True


class LibraryItemOut(BaseModel):
    # Deliberately no file_path here — that's a server-absolute filesystem
    # path with no meaning to a frontend consumer, and no reason to expose it
    # over the API. Downloading/opening an item goes through
    # GET /api/library/{id}/download (see routers/library.py), keyed by id,
    # never by path. The ORM row still has file_path internally — the route
    # handlers that need it (download/delete) read it straight off that row,
    # not through this schema.
    id: str
    title: str
    file_type: str
    source: str
    conversation_id: str | None
    message_id: str | None
    tags: list[str]
    description: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ScheduleItemCreate(BaseModel):
    title: str
    description: str | None = None
    due_at: datetime | None = None
    recurrence_rule: str | None = None
    source_conversation_id: str | None = None


class ScheduleItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    due_at: datetime | None = None
    recurrence_rule: str | None = None


class ScheduleItemOut(BaseModel):
    id: str
    title: str
    description: str | None
    due_at: datetime | None
    recurrence_rule: str | None
    status: str
    source_conversation_id: str | None
    reminder_type: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("due_at", "created_at", "updated_at", mode="before")
    @classmethod
    def _assume_utc_if_naive(cls, value: datetime | None) -> datetime | None:
        # SQLite drops tzinfo on read-back even for a DateTime(timezone=True)
        # column (same gotcha already documented in app/usage.py's
        # _as_utc_isoformat) — every datetime this app writes to these
        # columns is UTC, so a naive value read back from the DB is UTC that
        # lost its label, not a genuinely tz-naive value. Without this, the
        # API would serialize an offset-less ISO string, and the frontend's
        # `new Date(...)` would parse it as local time instead of UTC —
        # silently shifting a reminder's displayed time by however many
        # hours off UTC the browser is. A reminder created for local 9:00 AM
        # must still say 9:00 AM after a reload.
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


# ---- ECHO Personal OS v1: Projects / Tasks / Mission Control ----
ProjectStatus = Literal["active", "paused", "completed", "archived"]
TaskStatus = Literal["todo", "in_progress", "blocked", "done", "cancelled"]
Priority = Literal["low", "medium", "high"]


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    priority: Priority = "medium"
    category: str | None = None
    tags: list[str] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    priority: Priority | None = None
    category: str | None = None
    tags: list[str] | None = None
    # ECHO Layer 1 (Phase 12) — lightweight project memory profile
    objective: str | None = None
    constraints_json: list[str] | None = None
    decisions_json: list[str] | None = None
    blockers_json: list[str] | None = None


class ProjectOut(BaseModel):
    id: str
    title: str
    description: str | None
    status: ProjectStatus
    priority: Priority
    category: str | None
    tags: list[str]
    last_touched_at: datetime
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    # ECHO Layer 1 (Phase 12)
    objective: str | None = None
    constraints_json: list[str] = Field(default_factory=list)
    decisions_json: list[str] = Field(default_factory=list)
    blockers_json: list[str] = Field(default_factory=list)
    last_reviewed_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("last_touched_at", "created_at", "updated_at", "archived_at", mode="before")
    @classmethod
    def _assume_utc_if_naive(cls, value: datetime | None) -> datetime | None:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    priority: Priority = "medium"
    project_id: str | None = None
    due_at: datetime | None = None
    source_type: str | None = None
    source_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    status: TaskStatus | None = None
    priority: Priority | None = None
    project_id: str | None = None
    due_at: datetime | None = None
    tags: list[str] | None = None
    sort_order: int | None = None


class TaskOut(BaseModel):
    id: str
    title: str
    description: str | None
    status: TaskStatus
    priority: Priority
    project_id: str | None
    # Populated by the router via a single bulk project_id -> title lookup,
    # not stored on the row — avoids N+1 queries and a fragile join in every
    # list endpoint while still letting the frontend show "Project X" next
    # to a task without a second round trip.
    project_title: str | None = None
    due_at: datetime | None
    scheduled_item_id: str | None
    source_type: str | None
    source_id: str | None
    tags: list[str]
    sort_order: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}

    @field_validator("due_at", "created_at", "updated_at", "completed_at", mode="before")
    @classmethod
    def _assume_utc_if_naive(cls, value: datetime | None) -> datetime | None:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class ProjectDetailOut(ProjectOut):
    tasks: list[TaskOut] = Field(default_factory=list)


class ContinueSuggestion(BaseModel):
    id: str
    title: str
    reason: str
    source_type: str  # "project" | "task" | "conversation" | "schedule" | "library" | "atlas"
    source_id: str | None
    action_label: str
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _assume_utc_if_naive(cls, value: datetime | None) -> datetime | None:
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


class SystemStatusOut(BaseModel):
    ollama: bool
    wiki: bool
    rss: bool
    searxng: bool
    image_generation: bool
    library: bool = True
    schedule: bool = True


class MissionControlOut(BaseModel):
    today_tasks: list[TaskOut] = Field(default_factory=list)
    overdue_tasks: list[TaskOut] = Field(default_factory=list)
    upcoming_tasks: list[TaskOut] = Field(default_factory=list)
    active_projects: list[ProjectOut] = Field(default_factory=list)
    recently_touched_projects: list[ProjectOut] = Field(default_factory=list)
    recent_conversations: list[ConversationOut] = Field(default_factory=list)
    recent_library_files: list[LibraryItemOut] = Field(default_factory=list)
    upcoming_schedule_items: list[ScheduleItemOut] = Field(default_factory=list)
    pending_memory_candidates: list[MemoryCandidateOut] = Field(default_factory=list)
    system_status: SystemStatusOut | None = None
    continue_where_left_off: list[ContinueSuggestion] = Field(default_factory=list)
    # Populated per-section: if one section's query fails, its list stays
    # empty and a short, clean message is appended here instead of a raw
    # exception — the rest of the response still returns normally.
    warnings: list[str] = Field(default_factory=list)


# ---- ECHO Human Persona Layer v1 ----
FollowupFrequency = Literal["low", "medium", "high"]
ChallengeStyle = Literal["gentle", "direct", "strict"]
ComfortStyle = Literal["practical", "warm", "minimal"]
DetailLevel = Literal["minimal", "short", "normal", "detailed", "exhaustive"]
DisagreementStyle = Literal["soft", "direct", "firm"]
HumourSafetyMode = Literal["normal", "serious_context_low_humour"]
OperationalMode = Literal[
    "normal",
    "coding_assistant",
    "research",
    "planning",
    "low_energy_support",
    "strict_coach",
    "study_tutor",
    "release_testing",
    "troubleshooting",
    "quick_answer",
    # ECHO Operational Self-Model v1 additions — extends rather than
    # duplicates the existing mode enum above (see human_persona.py's
    # _MODE_STYLE_TEXT / operational_self_model.py's mode detection).
    "focused",
    "reflective",
    "cautious",
    "action_ready",
    "uncertain",
    "blocked",
    "creative",
    "calm_support",
]
MoodMode = Literal[
    "neutral",
    "focused",
    "confused",
    "stressed",
    "excited",
    "low_energy",
    "coding_mode",
    "planning_mode",
    "reassurance_needed",
    "overwhelmed",
    "urgent",
]
MoodConfidence = Literal["low", "medium", "high"]
ThreadStatus = Literal["active", "paused", "completed", "stale"]
RitualType = Literal[
    "morning_check_in",
    "coding_session_start",
    "coding_session_wrap_up",
    "weekly_review",
    "release_checklist",
    "low_energy_reset",
    "study_session_start",
]


class PersonaSettingsOut(BaseModel):
    tester_id: str
    preferred_name: str | None
    allowed_nicknames: list[str]
    disliked_names: list[str]
    formality_level: int
    emoji_level: int
    asks_followup_questions: FollowupFrequency
    bullet_points_preferred: bool
    examples_first: bool
    challenge_style: ChallengeStyle
    comfort_style: ComfortStyle
    humour_level: int
    sarcasm_level: int
    dry_wit_enabled: bool
    humour_safety_mode: HumourSafetyMode
    detail_level: DetailLevel
    proactivity_level: int
    default_operational_mode: OperationalMode
    recommendation_strength: int
    disagreement_style: DisagreementStyle
    local_answer_quality_mode: AnswerQualityMode
    voice_mode: VoiceMode
    tts_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonaSettingsUpdate(BaseModel):
    """Every field optional — a PATCH-style partial update. Truthfulness,
    privacy, and safety are never fields here at all (see human_persona.py's
    CHARACTER_CODE): there is structurally no setting a tester could set to
    weaken them, satisfying Phase 8's "user preference cannot disable
    truthfulness/privacy/safety" rule at the schema level, not just by
    convention."""

    preferred_name: str | None = None
    allowed_nicknames: list[str] | None = None
    disliked_names: list[str] | None = None
    formality_level: int | None = Field(None, ge=0, le=5)
    emoji_level: int | None = Field(None, ge=0, le=5)
    asks_followup_questions: FollowupFrequency | None = None
    bullet_points_preferred: bool | None = None
    examples_first: bool | None = None
    challenge_style: ChallengeStyle | None = None
    comfort_style: ComfortStyle | None = None
    humour_level: int | None = Field(None, ge=0, le=5)
    sarcasm_level: int | None = Field(None, ge=0, le=5)
    dry_wit_enabled: bool | None = None
    humour_safety_mode: HumourSafetyMode | None = None
    detail_level: DetailLevel | None = None
    proactivity_level: int | None = Field(None, ge=0, le=4)
    default_operational_mode: OperationalMode | None = None
    recommendation_strength: int | None = Field(None, ge=0, le=5)
    disagreement_style: DisagreementStyle | None = None
    local_answer_quality_mode: AnswerQualityMode | None = None
    voice_mode: VoiceMode | None = None
    tts_enabled: bool | None = None


class RelationshipProfileOut(BaseModel):
    tester_id: str
    relationship_summary: str
    working_style_summary: str
    trust_notes: str | None
    support_preferences: str | None
    communication_preferences: str | None
    project_preferences: str | None
    version: int
    created_at: datetime
    last_updated_at: datetime

    model_config = {"from_attributes": True}


class RelationshipProfileUpdate(BaseModel):
    relationship_summary: str | None = None
    working_style_summary: str | None = None
    trust_notes: str | None = None
    support_preferences: str | None = None
    communication_preferences: str | None = None
    project_preferences: str | None = None


class ConversationMoodStateOut(BaseModel):
    conversation_id: str
    detected_mode: MoodMode
    confidence: MoodConfidence
    reason_summary: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationThreadStateOut(BaseModel):
    conversation_id: str
    topic: str
    summary: str
    next_step: str | None
    linked_project_id: str | None
    linked_task_id: str | None
    status: ThreadStatus
    updated_at: datetime

    model_config = {"from_attributes": True}


class ConversationModeOut(BaseModel):
    conversation_id: str
    active_operational_mode: OperationalMode | None
    default_operational_mode: OperationalMode
    session_style_override: dict


class ConversationModeUpdate(BaseModel):
    mode: OperationalMode


class PersonalRitualOut(BaseModel):
    id: str
    tester_id: str
    ritual_type: RitualType
    enabled: bool
    preferred_time: str | None
    prompt_text: str
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PersonalRitualUpdate(BaseModel):
    enabled: bool | None = None
    preferred_time: str | None = None
    prompt_text: str | None = None


# ---- ECHO Local Intelligence Engine v1 ----
class LocalModelsOut(BaseModel):
    available: bool
    models: list[str]
    error: str | None = None


ConfidenceLevel = Literal["high", "medium", "low", "unverified"]
CriticStatus = Literal["passed", "repaired", "failed", "skipped"]


class LocalIntelligenceSettingsOut(BaseModel):
    local_intelligence_engine_enabled: bool
    local_model_routing_enabled: bool
    local_answer_quality_mode: AnswerQualityMode
    local_critic_enabled: bool
    cloud_fallback_enabled: bool
    cloud_fallback_require_user_confirmation: bool
    ollama_available: bool
    ollama_status_reason: str | None = None
    installed_models: list[str] = Field(default_factory=list)


class LocalIntelligenceSettingsUpdate(BaseModel):
    local_answer_quality_mode: AnswerQualityMode | None = None


# ============================================================================
# ECHO Action + Reliability Core v1
# ============================================================================


class _UtcAssumingModel(BaseModel):
    """Shared mixin for Out schemas with datetime fields read back from
    SQLite (which stores naive datetimes) — assumes UTC rather than letting
    Pydantic treat a naive value as "no timezone info at all" and have the
    frontend's `new Date(...)` silently parse it as local time. Same fix as
    ProjectOut/TaskOut's per-class validator, generalized so the many new
    schemas below don't each repeat it."""

    model_config = {"from_attributes": True}

    @field_validator("*", mode="before")
    @classmethod
    def _assume_utc_if_naive(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


# ---- Action System v1 ----
RiskLevel = Literal["low", "medium", "high", "destructive"]
ActionRunStatus = Literal["pending", "approved", "running", "completed", "failed", "cancelled"]
ActionCategory = Literal[
    "memory", "task", "project", "schedule", "library", "web", "file", "report", "release", "system", "voice", "camera"
]


class ActionDefinitionOut(_UtcAssumingModel):
    name: str
    description: str
    category: ActionCategory
    risk_level: RiskLevel
    enabled: bool
    requires_confirmation: bool
    requires_permission_key: str | None
    created_at: datetime
    updated_at: datetime


class ActionRunRequest(BaseModel):
    action_name: str
    input: dict = Field(default_factory=dict)
    confirm: bool = False


class ActionRunOut(_UtcAssumingModel):
    id: str
    action_name: str
    status: ActionRunStatus
    risk_level: RiskLevel
    input_json: dict
    result_json: dict | None
    error_summary: str | None
    user_confirmed: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


# ---- Permission Center v1 ----
PermissionLevel = Literal["allowed", "ask_first", "disabled"]


class PermissionSettingOut(_UtcAssumingModel):
    permission_key: str
    level: PermissionLevel
    description: str
    risk_level: RiskLevel
    updated_at: datetime


class PermissionSettingUpdate(BaseModel):
    level: PermissionLevel


# ---- Reliability / Evaluation Lab v1 ----
EvalRunStatus = Literal["running", "completed", "failed"]
EvalResultStatus = Literal["pass", "fail", "warning"]
EvalSummary = Literal["green", "yellow", "red", "unknown"]


class EvaluationCaseOut(BaseModel):
    id: str
    name: str
    category: str
    user_message: str
    notes: str | None = None


class EvaluationResultOut(_UtcAssumingModel):
    id: str
    case_id: str
    status: EvalResultStatus
    reason: str
    observed_json: dict
    created_at: datetime


class EvaluationRunOut(_UtcAssumingModel):
    id: str
    status: EvalRunStatus
    started_at: datetime
    completed_at: datetime | None
    result_summary: EvalSummary
    total_cases: int
    passed_cases: int
    failed_cases: int
    warnings: int


class EvaluationRunDetailOut(EvaluationRunOut):
    results: list[EvaluationResultOut] = Field(default_factory=list)


# ---- Personal Knowledge Vault v1 ----
KnowledgeItemType = Literal[
    "note", "decision", "source", "summary", "idea", "bug", "release_note", "study_note", "prompt", "reference", "personal_rule"
]


class KnowledgeItemCreate(BaseModel):
    title: str
    body: str = ""
    item_type: KnowledgeItemType = "note"
    source_type: str | None = None
    source_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    confidence: ConfidenceLevel = "medium"


class KnowledgeItemUpdate(BaseModel):
    title: str | None = None
    body: str | None = None
    item_type: KnowledgeItemType | None = None
    project_id: str | None = None
    task_id: str | None = None
    tags: list[str] | None = None
    confidence: ConfidenceLevel | None = None


class KnowledgeItemOut(_UtcAssumingModel):
    id: str
    title: str
    body: str
    item_type: KnowledgeItemType
    source_type: str | None
    source_id: str | None
    project_id: str | None
    task_id: str | None
    tags: list[str]
    confidence: ConfidenceLevel
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


# ---- Conversation Auto-Summary v1 ----
class ConversationSummaryOut(_UtcAssumingModel):
    id: str
    conversation_id: str
    title: str
    summary: str
    decisions_json: list[str]
    tasks_json: list[str]
    open_questions_json: list[str]
    next_steps_json: list[str]
    memories_to_review_json: list[str]
    created_at: datetime
    updated_at: datetime


class ConversationSummarizeRequest(BaseModel):
    save_to_knowledge_vault: bool = False


# ---- Release / Build Manager v1 ----
ReleaseStatus = Literal["draft", "testing", "green", "yellow", "red", "released"]
ReleasePlatform = Literal["backend", "web", "android", "windows", "docs", "manual"]
ReleaseCheckStatus = Literal["pass", "fail", "warning", "not_run"]


class ReleaseCreate(BaseModel):
    version_name: str
    summary: str = ""
    git_commit: str | None = None
    git_tag: str | None = None


class ReleaseUpdate(BaseModel):
    summary: str | None = None
    git_commit: str | None = None
    git_tag: str | None = None


class ReleaseCheckCreate(BaseModel):
    check_name: str
    platform: ReleasePlatform
    command: str | None = None
    status: ReleaseCheckStatus = "not_run"
    output_summary: str | None = None
    artifact_path: str | None = None


class ReleaseCheckOut(_UtcAssumingModel):
    id: str
    check_name: str
    platform: ReleasePlatform
    command: str | None
    status: ReleaseCheckStatus
    output_summary: str | None
    artifact_path: str | None
    created_at: datetime


class ReleaseArtifactCreate(BaseModel):
    platform: ReleasePlatform
    artifact_type: str
    path: str


class ReleaseArtifactOut(_UtcAssumingModel):
    id: str
    platform: ReleasePlatform
    artifact_type: str
    path: str
    created_at: datetime


class ReleaseOut(_UtcAssumingModel):
    id: str
    version_name: str
    status: ReleaseStatus
    summary: str
    git_commit: str | None
    git_tag: str | None
    created_at: datetime
    updated_at: datetime


class ReleaseDetailOut(ReleaseOut):
    checks: list[ReleaseCheckOut] = Field(default_factory=list)
    artifacts: list[ReleaseArtifactOut] = Field(default_factory=list)


class ReleaseMarkStatusRequest(BaseModel):
    status: ReleaseStatus


# ---- Internal Plugin / Tool System v1 ----
ToolRunStatus = Literal["pending", "running", "completed", "failed", "blocked"]


class ToolDefinitionOut(_UtcAssumingModel):
    tool_name: str
    display_name: str
    description: str
    category: str
    enabled: bool
    risk_level: RiskLevel
    requires_confirmation: bool
    permission_key: str | None
    input_schema_json: dict
    output_schema_json: dict


class ToolRunRequest(BaseModel):
    input: dict = Field(default_factory=dict)
    confirm: bool = False


class ToolRunOut(_UtcAssumingModel):
    id: str
    tool_name: str
    status: ToolRunStatus
    input_json: dict
    output_json: dict | None
    error_summary: str | None
    created_at: datetime
    completed_at: datetime | None


# ============================================================================
# ECHO Cognitive Core v1 — World Model + Task Understanding Engine
# ============================================================================

ConceptType = Literal[
    "project", "system", "tool", "file", "process", "person_preference", "domain", "technical", "goal", "constraint", "risk", "source", "other"
]
CognitiveConfidence = Literal["high", "medium", "low", "inferred"]
ConceptSourceType = Literal["atlas_memory", "conversation", "knowledge_vault", "library", "project", "task", "manual", "system", "inferred"]
RelationType = Literal[
    "uses", "depends_on", "causes", "blocks", "enables", "part_of", "conflicts_with", "similar_to", "requires", "produces", "verifies", "belongs_to",
    # ---- ECHO Layer 2B: Systems Thinking edge types (additive, same free-text column) ----
    "consumes", "communicates_with", "mitigates", "feedback_to",
]
TaskType = Literal[
    "ask_question", "build_feature", "fix_bug", "run_test", "plan_project", "research_topic", "summarize_file",
    "make_decision", "create_prompt", "release_build", "troubleshoot", "study_learn", "personal_support", "other"
]
TaskConfidence = Literal["high", "medium", "low", "incomplete"]
SkillCategory = Literal["coding", "release", "research", "study", "planning", "troubleshooting", "writing", "personal", "system", "other"]

# ---- ECHO Layer 2A: Cognitive Core v2 / Task Understanding enums ----
# The milestone's broader taxonomy, independent of the legacy TaskType above.
TaskCategory = Literal[
    "question", "explanation", "research", "coding", "debugging", "planning", "decision",
    "document", "action", "reminder", "learning", "emotional_support", "creative", "mixed",
]
TaskUrgency = Literal["low", "normal", "high", "urgent"]
TaskComplexity = Literal["trivial", "simple", "moderate", "complex"]
TaskRiskLevel = Literal["low", "medium", "high", "critical"]
TaskReversibility = Literal["reversible", "hard_to_reverse", "irreversible"]
TaskStatus = Literal["draft", "analyzing", "ready", "needs_clarification", "stale", "superseded"]
TaskScope = Literal["current_turn", "conversation", "project", "recurring_workflow", "long_term_goal"]
MissingInfoTier = Literal["blocking", "important", "optional", "safely_inferable"]


class CognitiveConceptCreate(BaseModel):
    name: str
    description: str | None = None
    concept_type: ConceptType = "other"
    confidence: CognitiveConfidence = "medium"
    source_type: ConceptSourceType | None = "manual"
    source_id: str | None = None


class CognitiveConceptUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    concept_type: ConceptType | None = None
    confidence: CognitiveConfidence | None = None


class CognitiveConceptOut(_UtcAssumingModel):
    id: str
    name: str
    description: str | None
    concept_type: ConceptType
    confidence: CognitiveConfidence
    source_type: str | None
    source_id: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CognitiveRelationshipCreate(BaseModel):
    from_concept_id: str
    to_concept_id: str
    relation_type: RelationType
    description: str | None = None
    confidence: CognitiveConfidence = "medium"
    source_type: ConceptSourceType | None = "manual"
    source_id: str | None = None


class CognitiveRelationshipOut(_UtcAssumingModel):
    id: str
    from_concept_id: str
    to_concept_id: str
    relation_type: RelationType
    description: str | None
    confidence: CognitiveConfidence
    source_type: str | None
    source_id: str | None
    created_at: datetime
    updated_at: datetime


class GraphNodeOut(BaseModel):
    concept: CognitiveConceptOut
    relationships: list[CognitiveRelationshipOut] = Field(default_factory=list)


class TaskUnderstandingRequest(BaseModel):
    user_message: str
    conversation_id: str | None = None
    project_id: str | None = None


class TaskUnderstandingOut(_UtcAssumingModel):
    id: str
    conversation_id: str | None
    user_message: str
    goal_summary: str
    domain: str
    task_type: TaskType
    known_facts_json: list[str]
    unknowns_json: list[str]
    constraints_json: list[str]
    assumptions_json: list[str]
    success_criteria_json: list[str]
    risks_json: list[str]
    relevant_concepts_json: list[str]
    recommended_next_step: str | None
    confidence: TaskConfidence
    created_at: datetime
    # ECHO Layer 2A
    project_id: str | None = None
    parent_task_id: str | None = None
    normalized_request: str | None = None
    task_category: TaskCategory = "mixed"
    urgency: TaskUrgency = "normal"
    complexity: TaskComplexity = "moderate"
    primary_goal: str | None = None
    secondary_goals_json: list[str] = Field(default_factory=list)
    user_intent: str | None = None
    expected_output: str | None = None
    inferred_constraints_json: list[str] = Field(default_factory=list)
    preferences_json: list[str] = Field(default_factory=list)
    forbidden_actions_json: list[str] = Field(default_factory=list)
    uncertainties_json: list[str] = Field(default_factory=list)
    missing_information_json: list[dict] = Field(default_factory=list)
    failure_conditions_json: list[str] = Field(default_factory=list)
    acceptance_tests_json: list[str] = Field(default_factory=list)
    required_capabilities_json: list[str] = Field(default_factory=list)
    candidate_skills_json: list[str] = Field(default_factory=list)
    candidate_tools_json: list[str] = Field(default_factory=list)
    required_sources_json: list[str] = Field(default_factory=list)
    risk_level: TaskRiskLevel = "low"
    consequence_level: TaskRiskLevel = "low"
    reversibility: TaskReversibility = "reversible"
    confirmation_requirement: bool = False
    status: TaskStatus = "ready"
    intent_hierarchy_json: dict = Field(default_factory=dict)
    scope: TaskScope = "current_turn"
    clarification_questions_json: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class TaskUnderstandingCorrection(BaseModel):
    """User-driven correction of a misunderstood goal/constraint (Phase 7 /
    frontend correction control) — never a raw field-by-field PATCH of
    everything, just the handful of things a user would plausibly want to
    fix directly."""

    primary_goal: str | None = None
    expected_output: str | None = None
    explicit_constraints: list[str] | None = None
    forbidden_actions: list[str] | None = None
    scope: TaskScope | None = None


class ClarificationViewOut(BaseModel):
    """The compact 'why ECHO needs clarification' summary — never raw
    reasoning, just the blocking questions and why they're blocking."""

    needs_clarification: bool
    questions: list[str]
    blocking_items: list[str]
    safe_assumptions_made: list[str]


class ContextPreviewRequest(BaseModel):
    user_message: str
    conversation_id: str | None = None
    project_id: str | None = None


class ContextPreviewOut(BaseModel):
    task_understanding: TaskUnderstandingOut | None
    brief_text: str | None
    clarification: ClarificationViewOut


class TaskTypeInfo(BaseModel):
    value: str
    label: str
    description: str


class TaskTypesOut(BaseModel):
    task_types: list[TaskTypeInfo]
    task_categories: list[TaskTypeInfo]


class SkillPatternCreate(BaseModel):
    name: str
    description: str = ""
    category: SkillCategory = "other"
    trigger_patterns: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    common_failures: list[str] = Field(default_factory=list)


class SkillPatternUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: SkillCategory | None = None
    steps: list[str] | None = None
    success_criteria: list[str] | None = None


class SkillPatternOut(_UtcAssumingModel):
    id: str
    name: str
    description: str
    category: SkillCategory
    trigger_patterns_json: list[str]
    steps_json: list[str]
    required_tools_json: list[str]
    success_criteria_json: list[str]
    common_failures_json: list[str]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class SuggestPlanRequest(BaseModel):
    user_message: str


class SuggestPlanOut(BaseModel):
    skill: SkillPatternOut
    plan_steps: list[str]


class CausalNoteCreate(BaseModel):
    title: str
    cause: str
    effect: str
    explanation: str = ""
    confidence: CognitiveConfidence = "medium"
    source_type: ConceptSourceType | None = "manual"
    source_id: str | None = None


class CausalNoteUpdate(BaseModel):
    title: str | None = None
    cause: str | None = None
    effect: str | None = None
    explanation: str | None = None
    confidence: CognitiveConfidence | None = None


class CausalNoteOut(_UtcAssumingModel):
    id: str
    title: str
    cause: str
    effect: str
    explanation: str
    confidence: CognitiveConfidence
    source_type: str | None
    source_id: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class CognitiveBriefRequest(BaseModel):
    user_message: str
    conversation_id: str | None = None


class CognitiveBriefOut(_UtcAssumingModel):
    id: str
    conversation_id: str | None
    task_understanding_id: str | None
    brief_text: str
    selected_concepts_json: list[str]
    selected_skills_json: list[str]
    selected_context_sources_json: list[str]
    created_at: datetime
    # ECHO Layer 2A
    candidate_tools_json: list[str] = Field(default_factory=list)
    risk_and_confirmation_summary: str | None = None
    confidence: TaskConfidence = "medium"
    next_reasoning_stage: str | None = None


class CognitiveSettingsOut(BaseModel):
    cognitive_core_enabled: bool
    cognitive_concept_extraction_enabled: bool
    cognitive_skill_matching_enabled: bool
    cognitive_show_developer_diagnostics: bool


class CognitiveSettingsUpdate(BaseModel):
    cognitive_core_enabled: bool | None = None
    cognitive_concept_extraction_enabled: bool | None = None
    cognitive_skill_matching_enabled: bool | None = None
    cognitive_show_developer_diagnostics: bool | None = None


# ============================================================================
# ECHO Layer 2B — Systems Thinking and Simulation Engine
# ============================================================================

SystemModelScope = Literal[
    "software_architecture", "project_plan", "physical_system", "organisational_workflow", "study_plan", "decision_context"
]
SystemNodeRole = Literal["component", "actor", "resource", "constraint", "interface", "external_factor"]
SimulationStatus = Literal["running", "completed", "aborted", "failed"]
SimulationRiskTolerance = Literal["low", "medium", "high"]
ScenarioReversibility = Literal["reversible", "hard_to_reverse", "irreversible"]
EvidenceQuality = Literal["low", "medium", "high"]
ConfidenceBand = Literal["narrow", "moderate", "wide"]


class SystemModelCreate(BaseModel):
    name: str
    scope: SystemModelScope = "software_architecture"
    description: str | None = None
    project_id: str | None = None


class SystemModelUpdate(BaseModel):
    name: str | None = None
    scope: SystemModelScope | None = None
    description: str | None = None


class SystemModelOut(_UtcAssumingModel):
    id: str
    name: str
    scope: SystemModelScope
    description: str | None
    project_id: str | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class SystemModelNodeCreate(BaseModel):
    concept_id: str
    node_role: SystemNodeRole = "component"
    state: str | None = None
    owner: str | None = None
    evidence: str | None = None
    confidence: CognitiveConfidence = "medium"


class SystemModelNodeOut(BaseModel):
    id: str
    system_model_id: str
    concept_id: str
    concept_name: str
    node_role: SystemNodeRole
    state: str | None
    owner: str | None
    evidence: str | None
    confidence: CognitiveConfidence
    created_at: datetime


class DependencyEdgeOut(BaseModel):
    from_concept_id: str
    to_concept_id: str
    relation_type: RelationType


class BottleneckOut(BaseModel):
    concept_id: str
    concept_name: str
    in_degree: int
    out_degree: int
    reason: str


class CriticalPathOut(BaseModel):
    node_ids: list[str] = Field(default_factory=list)
    node_names: list[str] = Field(default_factory=list)
    length: int


class SystemAnalysisOut(BaseModel):
    system_model: SystemModelOut
    nodes: list[SystemModelNodeOut] = Field(default_factory=list)
    edges: list[DependencyEdgeOut] = Field(default_factory=list)
    bottlenecks: list[BottleneckOut] = Field(default_factory=list)
    cycles: list[list[str]] = Field(default_factory=list)
    critical_path: CriticalPathOut | None = None


class SimulationCreate(BaseModel):
    objective: str
    task_id: str | None = None
    system_model_id: str | None = None
    baseline_state: str | None = None
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    max_scenarios: int = 4
    max_steps: int = 12
    time_horizon: str | None = None
    evaluation_criteria: list[str] = Field(default_factory=list)
    risk_tolerance: SimulationRiskTolerance = "medium"


class SimulationScenarioOut(_UtcAssumingModel):
    id: str
    simulation_id: str
    label: str
    strategy: str
    assumptions_json: list[str]
    steps_json: list[dict]
    predicted_outcomes_json: list[str]
    dependencies_json: list[str]
    costs_json: list[str]
    risks_json: list[str]
    failure_modes_json: list[str]
    reversibility: ScenarioReversibility
    evidence_quality: EvidenceQuality
    confidence_band: ConfidenceBand
    uncertainty_notes: str | None
    sensitivity_label: Literal["low", "moderate", "high"]
    sensitivity_note: str
    steps_completed: int
    steps_blocked: int
    stopped_reason: str | None
    rank: int | None
    created_at: datetime


class SimulationOut(_UtcAssumingModel):
    id: str
    task_id: str | None
    system_model_id: str | None
    objective: str
    baseline_state: str | None
    constraints_json: list[str]
    assumptions_json: list[str]
    max_scenarios: int
    max_steps: int
    time_horizon: str | None
    evaluation_criteria_json: list[str]
    risk_tolerance: SimulationRiskTolerance
    status: SimulationStatus
    too_uncertain_to_rank: bool
    created_at: datetime
    scenarios: list[SimulationScenarioOut] = Field(default_factory=list)


class DecisionHandoffOut(BaseModel):
    simulation_id: str
    recommended_scenario_id: str | None
    recommendation_summary: str
    ranked_scenario_ids: list[str] = Field(default_factory=list)
    too_uncertain_to_rank: bool
    caveats: list[str] = Field(default_factory=list)


# ============================================================================
# ECHO Layer 2C — Decision Engine and Planning Engine
# ============================================================================

DecisionCaseStatus = Literal["draft", "analysed", "selected", "cancelled"]
DecisionReversibility = Literal["reversible", "hard_to_reverse", "irreversible"]
DecisionConsequenceLevel = Literal["low", "medium", "high", "critical"]
CriterionSource = Literal["user_stated", "inferred", "from_simulation"]
CriterionImportance = Literal["low", "medium", "high"]
HardOrSoft = Literal["hard", "soft"]
PlanStatus = Literal["proposed", "approved", "active", "blocked", "completed", "failed", "cancelled"]
PlanStepStatus = Literal["pending", "in_progress", "blocked", "completed", "failed", "cancelled"]
MilestoneStatus = Literal["pending", "reached", "missed"]
PlanDependencyType = Literal["blocks", "informs"]
ResourceType = Literal["time", "tool", "skill", "external", "other"]
ResourceAvailability = Literal["available", "unavailable", "unknown"]
RiskLikelihood = Literal["low", "medium", "high", "unknown"]
RiskImpact = Literal["low", "medium", "high"]
PlanRiskStatus = Literal["open", "mitigated", "accepted", "occurred"]
ReplanTrigger = Literal["failure", "new_evidence", "changed_constraint", "missed_deadline", "user_correction"]


class DecisionOptionCreate(BaseModel):
    label: str
    description: str | None = None
    benefits: list[str] = Field(default_factory=list)
    drawbacks: list[str] = Field(default_factory=list)
    direct_cost: str | None = None
    opportunity_cost: str | None = None
    time_estimate: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    reversibility: DecisionReversibility = "reversible"
    evidence_quality: EvidenceQuality = "medium"
    confidence: CognitiveConfidence = "medium"
    violates_criteria: list[str] = Field(default_factory=list)


class DecisionOptionOut(_UtcAssumingModel):
    id: str
    decision_case_id: str
    label: str
    description: str | None
    benefits_json: list[str]
    drawbacks_json: list[str]
    direct_cost: str | None
    opportunity_cost: str | None
    time_estimate: str | None
    dependencies_json: list[str]
    risks_json: list[str]
    failure_modes_json: list[str]
    reversibility: DecisionReversibility
    evidence_quality: EvidenceQuality
    confidence: CognitiveConfidence
    violates_criteria_json: list[str]
    criterion_ratings_json: dict[str, float]
    eliminated: bool
    eliminated_reason: str | None
    score: float | None
    pareto_dominated: bool
    source_scenario_id: str | None
    created_at: datetime


class DecisionCriterionCreate(BaseModel):
    name: str
    description: str | None = None
    source: CriterionSource = "user_stated"
    importance: CriterionImportance = "medium"
    hard_or_soft: HardOrSoft = "soft"


class DecisionCriterionOut(_UtcAssumingModel):
    id: str
    decision_case_id: str
    name: str
    description: str | None
    source: CriterionSource
    importance: CriterionImportance
    hard_or_soft: HardOrSoft
    weight: float | None
    created_at: datetime


class DecisionCriterionWeightUpdate(BaseModel):
    weight: float | None = Field(default=None, ge=0.0, le=1.0)


class DecisionOptionRatingsUpdate(BaseModel):
    """Explicit per-criterion ratings for one option — never inferred.
    Values are 0.0-1.0, keyed by DecisionCriterion.id."""

    ratings: dict[str, float]


class DecisionCaseCreate(BaseModel):
    question: str
    objective: str
    constraints: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    uncertainty: str | None = None
    time_horizon: str | None = None
    reversibility: DecisionReversibility = "reversible"
    consequence_level: DecisionConsequenceLevel = "low"
    simulation_id: str | None = None
    task_id: str | None = None
    project_id: str | None = None
    options: list[DecisionOptionCreate] = Field(default_factory=list)
    criteria: list[DecisionCriterionCreate] = Field(default_factory=list)


class DecisionReportOut(BaseModel):
    decision_summary: str
    recommended_option_label: str | None
    no_clear_winner: bool
    why_this_option: str | None
    key_tradeoffs: list[str] = Field(default_factory=list)
    hard_constraints_checked: list[str] = Field(default_factory=list)
    major_assumptions: list[str] = Field(default_factory=list)
    major_uncertainties: list[str] = Field(default_factory=list)
    risks_and_mitigations: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    reversibility: DecisionReversibility
    evidence_quality: EvidenceQuality
    confidence_band: ConfidenceBand
    next_information_to_collect: list[str] = Field(default_factory=list)
    user_confirmation_needed: bool


class DecisionCaseOut(_UtcAssumingModel):
    id: str
    question: str
    objective: str
    constraints_json: list[str]
    stakeholders_json: list[str]
    evidence_json: list[str]
    assumptions_json: list[str]
    uncertainty: str | None
    time_horizon: str | None
    reversibility: DecisionReversibility
    consequence_level: DecisionConsequenceLevel
    status: DecisionCaseStatus
    simulation_id: str | None
    task_id: str | None
    project_id: str | None
    recommended_option_id: str | None
    no_clear_winner: bool
    report: DecisionReportOut | None = None
    created_at: datetime
    updated_at: datetime
    options: list[DecisionOptionOut] = Field(default_factory=list)
    criteria: list[DecisionCriterionOut] = Field(default_factory=list)


class DecisionSelectRequest(BaseModel):
    option_id: str


class PlanStepCreate(BaseModel):
    title: str
    description: str | None = None
    estimated_effort: str | None = None
    owner: str = "user"
    verification_criteria: list[str] = Field(default_factory=list)
    depends_on_titles: list[str] = Field(default_factory=list)  # references other steps by title within the same request


class PlanStepOut(_UtcAssumingModel):
    id: str
    plan_id: str
    order_index: int
    title: str
    description: str | None
    estimated_effort: str | None
    owner: str
    status: PlanStepStatus
    verification_criteria_json: list[str]
    parallel_group: str | None
    materialised_task_id: str | None
    created_at: datetime
    updated_at: datetime


class MilestoneOut(_UtcAssumingModel):
    id: str
    plan_id: str
    name: str
    description: str | None
    target_step_ids_json: list[str]
    verification_criteria_json: list[str]
    status: MilestoneStatus
    due_at: datetime | None
    created_at: datetime


class PlanDependencyOut(_UtcAssumingModel):
    id: str
    plan_id: str
    from_step_id: str
    to_step_id: str
    dependency_type: PlanDependencyType


class PlanResourceRequirementOut(_UtcAssumingModel):
    id: str
    plan_id: str
    step_id: str | None
    resource_name: str
    resource_type: ResourceType
    amount: str | None
    availability_status: ResourceAvailability
    created_at: datetime


class PlanRiskOut(_UtcAssumingModel):
    id: str
    plan_id: str
    step_id: str | None
    description: str
    likelihood: RiskLikelihood
    impact: RiskImpact
    mitigation: str | None
    status: PlanRiskStatus
    created_at: datetime


class PlanRevisionOut(_UtcAssumingModel):
    id: str
    plan_id: str
    revision_number: int
    reason: str
    trigger: ReplanTrigger
    changed_step_ids_json: list[str]
    previous_status: str | None
    new_status: str | None
    created_at: datetime


class PlanCreate(BaseModel):
    objective: str
    scope: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    decision_case_id: str | None = None
    system_model_id: str | None = None
    task_id: str | None = None
    project_id: str | None = None
    steps: list[PlanStepCreate] = Field(default_factory=list)  # empty -> auto-generate a minimum viable plan


class PlanUpdate(BaseModel):
    scope: str | None = None
    assumptions: list[str] | None = None
    constraints: list[str] | None = None
    success_criteria: list[str] | None = None


class PlanValidationIssue(BaseModel):
    step_id: str | None
    severity: Literal["blocking", "warning"]
    message: str


class PlanValidationOut(BaseModel):
    plan_id: str
    valid: bool
    issues: list[PlanValidationIssue] = Field(default_factory=list)
    critical_path_step_ids: list[str] = Field(default_factory=list)
    parallel_groups: dict[str, list[str]] = Field(default_factory=dict)


class ReplanRequest(BaseModel):
    reason: str
    trigger: ReplanTrigger = "user_correction"


class MaterialiseTasksOut(BaseModel):
    plan_id: str
    created_task_ids: list[str] = Field(default_factory=list)
    created_reminder_action_run_ids: list[str] = Field(default_factory=list)
    skipped_step_ids: list[str] = Field(default_factory=list)


class PlanOut(_UtcAssumingModel):
    id: str
    objective: str
    scope: str | None
    assumptions_json: list[str]
    constraints_json: list[str]
    success_criteria_json: list[str]
    estimated_effort: str | None
    owner: str
    status: PlanStatus
    evidence_json: list[str]
    approved_at: datetime | None
    decision_case_id: str | None
    system_model_id: str | None
    task_id: str | None
    project_id: str | None
    revision_number: int
    superseded_by_plan_id: str | None
    created_at: datetime
    updated_at: datetime
    steps: list[PlanStepOut] = Field(default_factory=list)
    milestones: list[MilestoneOut] = Field(default_factory=list)
    dependencies: list[PlanDependencyOut] = Field(default_factory=list)
    resource_requirements: list[PlanResourceRequirementOut] = Field(default_factory=list)
    risks: list[PlanRiskOut] = Field(default_factory=list)
    revisions: list[PlanRevisionOut] = Field(default_factory=list)


# ============================================================================
# ECHO Operational Self-Model v1
# ============================================================================

SelfModelConfidence = Literal["high", "medium", "low", "unverified"]
ShowInnerState = Literal["never", "only_when_helpful", "developer_mode_only"]


class OperationalStateSnapshotOut(_UtcAssumingModel):
    id: str
    conversation_id: str | None
    current_goal: str
    current_mode: OperationalMode
    confidence: SelfModelConfidence
    known_limits_json: list[str]
    active_risks_json: list[str]
    relevant_memory_summary: str | None
    relationship_summary: str | None
    permissions_summary: str | None
    next_best_action: str | None
    should_ask_confirmation: bool
    should_use_tools_json: list[str]
    should_not_do_json: list[str]
    intensity: int
    expires_at: datetime | None
    created_at: datetime


class InterfaceSettingsOut(BaseModel):
    show_advanced_nav: bool
    compact_sidebar: bool
    show_developer_controls: bool
    show_usage_in_topbar: bool
    show_model_selector: bool
    poetic_language_enabled: bool
    operational_self_model_enabled: bool
    show_inner_state: ShowInnerState


class InterfaceSettingsUpdate(BaseModel):
    show_advanced_nav: bool | None = None
    compact_sidebar: bool | None = None
    show_developer_controls: bool | None = None
    show_usage_in_topbar: bool | None = None
    show_model_selector: bool | None = None
    poetic_language_enabled: bool | None = None
    operational_self_model_enabled: bool | None = None
    show_inner_state: ShowInnerState | None = None
