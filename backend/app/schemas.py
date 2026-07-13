from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EpistemicStatus = Literal["Verified", "Inferred", "Hypothesis", "Narrative"]
MemoryType = Literal[
    "fact", "preference", "mood", "goal", "fear", "capability", "project", "relationship", "event"
]
Role = Literal["founder", "guardian_a", "guardian_b", "guardian_c", "verifier"]
VoteDecision = Literal["approve", "reject"]


# ---- Chat ----
class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str
    provider: str = "auto"


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


class AtlasEntryUpdate(BaseModel):
    content: str | None = None
    epistemic_status: EpistemicStatus | None = None
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    source: str | None = None
    valid_until: datetime | None = None
    outdated: bool | None = None


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

    model_config = {"from_attributes": True}


class MemoryCandidateEdit(BaseModel):
    content: str | None = None
    epistemic_status: EpistemicStatus | None = None
    memory_type: MemoryType | None = None
    tags: list[str] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)


class MemoryCandidateDecision(BaseModel):
    note: str | None = None


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


class LibraryItemOut(BaseModel):
    id: str
    title: str
    file_path: str
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
