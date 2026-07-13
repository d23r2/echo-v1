import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String, default="New conversation")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(String)  # "user" | "echo"
    content: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    atlas_citations: Mapped[list] = mapped_column(JSON, default=list)
    # Set when auto mode's actual reply came from a lower-priority provider because a
    # higher-priority one 429'd on this same turn — surfaced in the UI near "via X".
    fallback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which dependency pattern (if any) triggered this turn's independence nudge —
    # see app/dependency_patterns.py. Audit/debug only, not shown prominently in chat.
    independence_nudge_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # Previous-conversation snippets (raw history, not Atlas) injected into this
    # turn's prompt, if any — see app/conversation_search.py. Persisted so the
    # "used previous conversation context" indicator survives reloading an old
    # conversation, same rationale as atlas_citations above.
    conversation_snippets: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(ForeignKey("messages.id"))
    filename: Mapped[str] = mapped_column(String)
    mime_type: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String)
    understood: Mapped[bool] = mapped_column(Boolean, default=False)
    # Honest, specific record of what actually happened to this file's content —
    # see app/attachments.py's ANALYSIS_STATUSES. `understood` above is coarser
    # ("is this a file type we intend to support at all"); this is what the UI
    # should show the user, since "understood" alone reads as a promise the model
    # actually looked at the content, which isn't true for audio/video/stored images.
    analysis_status: Mapped[str] = mapped_column(String, default="stored")
    # True only for images produced by POST /api/chat/generate-image, never for
    # user-uploaded files.
    generated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    message: Mapped["Message"] = relationship(back_populates="attachments")

    @property
    def base64_preview(self) -> str | None:
        # Only generated images carry an inline preview — computed on read from the
        # on-disk file rather than stored in the DB, so this stays cheap for the
        # normal (non-generated) attachment case and never bloats the database.
        if not self.generated:
            return None
        try:
            data = Path(self.storage_path).read_bytes()
        except OSError:
            return None
        return base64.b64encode(data).decode("ascii")


class AtlasEntry(Base):
    __tablename__ = "atlas_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    content: Mapped[str] = mapped_column(Text)
    epistemic_status: Mapped[str] = mapped_column(String)  # Verified | Inferred | Hypothesis | Narrative
    # fact | preference | mood | goal | fear | capability | project | relationship | event
    memory_type: Mapped[str] = mapped_column(String, default="fact")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outdated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SelfImprovementRequest(Base):
    __tablename__ = "self_improvement_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    proposed_by: Mapped[str] = mapped_column(String, default="founder")
    status: Mapped[str] = mapped_column(String, default="draft")  # draft | proposed | approved | rejected | applied | failed
    patch_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String, default="pending")  # pending | passed | failed
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_checks: Mapped[list] = mapped_column(JSON, default=list)  # list of check-result dicts
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Amendment(Base):
    __tablename__ = "amendments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    text: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_by: Mapped[str] = mapped_column(String)  # role id, e.g. "founder"
    status: Mapped[str] = mapped_column(String, default="proposed")  # proposed | ratified | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    votes: Mapped[list["Vote"]] = relationship(back_populates="amendment", cascade="all, delete-orphan")


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("amendment_id", "role", name="uq_vote_amendment_role"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    amendment_id: Mapped[str] = mapped_column(ForeignKey("amendments.id"))
    role: Mapped[str] = mapped_column(String)  # guardian_a | guardian_b | guardian_c | verifier
    decision: Mapped[str] = mapped_column(String)  # approve | reject
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    amendment: Mapped["Amendment"] = relationship(back_populates="votes")


class ProviderUsageDaily(Base):
    """One row per (provider, date_key) — date_key is a YYYY-MM-DD string computed in
    whatever timezone that provider resets its own quota in (see app/usage.py), not
    necessarily UTC today. Deliberately no fixed rate-limit numbers here: this only
    ever records real request counts and real 429 timestamps."""

    __tablename__ = "provider_usage_daily"
    __table_args__ = (UniqueConstraint("provider", "date_key", name="uq_provider_usage_date"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String)
    date_key: Mapped[str] = mapped_column(String)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    last_429_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MemoryExtractionLog(Base):
    """One row per chat turn's memory-extraction attempt (see
    app/routers/chat.py's _extract_memory / _log_memory_diagnostic) — not the
    memory content itself, just what happened while deciding whether to save one.
    Lets /api/atlas/diagnostics answer "why isn't Atlas remembering more?" without
    persisting full raw conversation text."""

    __tablename__ = "memory_extraction_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    explicit_request: Mapped[bool] = mapped_column(Boolean, default=False)
    memory_block_present: Mapped[bool] = mapped_column(Boolean, default=False)
    was_none: Mapped[bool] = mapped_column(Boolean, default=False)
    json_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    parse_succeeded: Mapped[bool] = mapped_column(Boolean, default=False)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryCandidate(Base):
    """An auto-extracted (implicit, opportunistic) memory awaiting human review
    before it becomes a real AtlasEntry — see app/memory_conflicts.py. Explicit
    "remember that..." requests bypass this table entirely and save directly, same
    as before: the user already deliberately asked, there's nothing to review."""

    __tablename__ = "memory_candidates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    content: Mapped[str] = mapped_column(Text)
    epistemic_status: Mapped[str] = mapped_column(String)
    memory_type: Mapped[str] = mapped_column(String, default="fact")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    source: Mapped[str | None] = mapped_column(String, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | accepted | rejected
    conflict_with: Mapped[list] = mapped_column(JSON, default=list)  # AtlasEntry ids
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
