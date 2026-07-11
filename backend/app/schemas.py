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


class MemoryUpdate(BaseModel):
    saved: bool
    explicit: bool
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


class AttachmentOut(BaseModel):
    filename: str
    mime_type: str
    size_bytes: int
    understood: bool

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    reasoning: str | None
    provider: str | None
    atlas_citations: list[dict]
    attachments: list[AttachmentOut] = Field(default_factory=list)
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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AtlasSearchResult(AtlasEntryOut):
    distance: float | None = None


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
