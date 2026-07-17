import base64
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String, default="New conversation")
    # Lightweight tester identity (Human Persona Layer v1) — not real auth, just a
    # string label so multiple testers on the same install each get their own
    # RelationshipProfile/PersonaSettings instead of sharing one. "default" is the
    # primary user (Aravind); the frontend sends this via an X-Tester-Id header,
    # defaulting to "default" when absent so existing usage needs no changes.
    tester_id: Mapped[str] = mapped_column(String, default="default")
    # Session-only operational mode override (e.g. "strict_coach" after the user
    # says "switch to strict coach mode") — deliberately NOT on PersonaSettings,
    # since a mode switch mid-conversation is not meant to change the tester's
    # permanent default mode unless they explicitly ask for that (see
    # chat_actions.py's persona-action parser).
    active_operational_mode: Mapped[str | None] = mapped_column(String, nullable=True)
    # Session-only style tweaks (e.g. {"length": "short"} after "keep replies
    # short today") — scoped to this conversation only, never written back to
    # PersonaSettings, so it can never leak into a new conversation or another
    # tester's defaults.
    session_style_override: Mapped[dict] = mapped_column(JSON, default=dict)
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
    # "complete" | "partial" | "missing" | "malformed" — see providers/base.py's
    # split_reasoning_and_answer() and envelope_stream.py's EnvelopeStreamParser for
    # how this is computed. Persisted so the frontend can show an honest "reasoning
    # unavailable" note even when reopening an old conversation, without ever
    # inventing a reasoning value that wasn't actually returned.
    envelope_status: Mapped[str] = mapped_column(String, default="missing")
    envelope_degradation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # No-billing web/wiki/RSS search results actually used for this turn's prompt —
    # see app/web_search.py's SourceResult (source_type/provider/title/url/domain/
    # feed_title/snippet/retrieved_at/published_at/reliability_note per entry).
    # Persisted so reopening an old conversation still shows the "via ..." source
    # names it was answered with, same rationale as atlas_citations above.
    sources_used: Mapped[list] = mapped_column(JSON, default=list)
    # The classified SearchIntent.task_type for this turn (see
    # app/search_intent.py) — e.g. "sports_update", "encyclopedia_lookup",
    # "general_chat". Recorded even when no search was needed, so it's
    # possible to audit what the classifier decided.
    current_info_intent: Mapped[str | None] = mapped_column(String, nullable=True)
    # Set when the message needed current/background info but no source could
    # be retrieved (search disabled, provider unreachable, no results) — the
    # honest reason surfaced instead of a fabricated answer. See
    # app/web_search.py's GatherResult.search_failure_reason.
    search_failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    """ECHO Layer 1 — this is the unified memory record ("MemoryRecord" in the
    milestone spec). Rather than build a second, parallel memory table, this
    existing model was extended in place with the Layer 1 fields below: it
    was already the source-of-truth memory store with real semantic search
    (see atlas.py), and rule 3 ("do not create a second independent memory
    system") makes extension the correct call, not a new table. `memory_type`
    (legacy: fact|preference|mood|goal|fear|capability|project|relationship|
    event) is left completely unchanged for backward compatibility with
    every existing row/filter/test; `category` below carries the new Layer 1
    taxonomy going forward. See ECHO_LAYER_1_MEMORY_FOUNDATION.md."""

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

    # --- ECHO Layer 1: Memory Foundation v1 (all additive, all default-safe) ---
    # profile|preference|project|task|episodic|semantic|skill|relationship|environment|temporary
    category: Mapped[str] = mapped_column(String, default="semantic")
    # verified|partially_verified|unverified|disputed|outdated|not_applicable
    verification_status: Mapped[str] = mapped_column(String, default="unverified")
    importance: Mapped[str] = mapped_column(String, default="medium")  # critical|high|medium|low
    stability: Mapped[str] = mapped_column(String, default="semi_stable")  # durable|semi_stable|volatile|temporary
    # permanent_until_deleted|periodic_review|expire_after_period|conversation_only|project_lifetime|manual_only
    retention_policy: Mapped[str] = mapped_column(String, default="periodic_review")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    # explicit_user_request|approved_candidate|manual_entry|project_import|document_extraction|
    # conversation_summary|system_generated|migration
    capture_method: Mapped[str] = mapped_column(String, default="migration")
    # No ForeignKey constraint, matching this repo's existing cross-reference style
    # (see CognitiveConcept/CognitiveRelationship) — Projects/Tasks are soft-archived
    # not hard-deleted, so a stale reference here is safe and SQLite FK enforcement
    # (ECHO Layer 0) would otherwise reject legitimate cross-entity references.
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # user_statement|uploaded_file|conversation|trusted_source|web_source|project_state|
    # test_output|tool_result|inference|manual_verification|migration
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_memory_id: Mapped[str | None] = mapped_column(String, nullable=True)
    supersedes_memory_id: Mapped[str | None] = mapped_column(String, nullable=True)
    contradiction_group_id: Mapped[str | None] = mapped_column(String, nullable=True)
    duplicate_group_id: Mapped[str | None] = mapped_column(String, nullable=True)
    review_state: Mapped[str] = mapped_column(String, default="none")  # none|pending_review|reviewed
    # active|archived|superseded|deleted — distinct from the legacy `outdated` bool,
    # which stays as the "don't treat as current" retrieval-exclusion flag it always
    # was. `status` adds the richer lifecycle Layer 1 needs (see memory_lifecycle.py).
    status: Mapped[str] = mapped_column(String, default="active")


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


class ProviderCooldown(Base):
    """At most one active row per provider — set when a call fails with a
    quota/credit/billing/rate-limit error (see app/provider_errors.py's
    COOLDOWN_CATEGORIES), cleared once `cooldown_until` passes. Lets the router
    skip a provider it already knows is exhausted instead of re-trying it (and
    paying the latency cost) on every single turn. See app/router.py."""

    __tablename__ = "provider_cooldowns"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    provider: Mapped[str] = mapped_column(String, unique=True)
    category: Mapped[str] = mapped_column(String)  # ErrorCategory value, see provider_errors.py
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class LibraryItem(Base):
    """A pointer to a file Echo produced or received — generated images,
    exported conversations, self-improvement/health reports, uploaded
    attachments, etc. — so Phase 5's Library view can list/search/filter them
    without re-deriving "what files exist" by scanning disk or Attachment
    rows scattered across conversations. Registered via app/library.py's
    register_item(), not created directly by user request."""

    __tablename__ = "library_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    file_path: Mapped[str] = mapped_column(String)
    # image | document | exported_conversation | report | code | other
    file_type: Mapped[str] = mapped_column(String, default="other")
    # Where this item came from — e.g. "image_generation", "self_improvement",
    # "health_report", "conversation_export", "attachment_upload".
    source: Mapped[str] = mapped_column(String)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ScheduleItem(Base):
    """A user-created reminder/to-do, surfaced in Phase 5's Schedule view.
    Reminders are in-app only in this build — reminder_type is always
    "in_app" for now; there is no background OS notification delivery, so a
    due item only surfaces the next time the user has Echo open. See
    PROJECT_HEALTH_REPORT.md's known-gaps section."""

    __tablename__ = "schedule_items"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recurrence_rule: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending | completed | cancelled
    source_conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reminder_type: Mapped[str] = mapped_column(String, default="in_app")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


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

    # --- ECHO Layer 1: Memory Foundation v1 candidate-pipeline fields ---
    category: Mapped[str | None] = mapped_column(String, nullable=True)  # Layer 1 taxonomy, see AtlasEntry.category
    # public|ordinary_personal|private|highly_sensitive|secret — see memory_privacy.py
    sensitivity_level: Mapped[str] = mapped_column(String, default="ordinary_personal")
    # auto_accept|ask_user|merge|update_existing|ignore|reject_sensitive|temporary_only
    recommendation: Mapped[str | None] = mapped_column(String, nullable=True)
    capture_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    duplicate_memory_id: Mapped[str | None] = mapped_column(String, nullable=True)
    importance: Mapped[str] = mapped_column(String, default="medium")
    stability: Mapped[str] = mapped_column(String, default="semi_stable")


class Project(Base):
    """ECHO Personal OS v1 — a durable body of ongoing work (a study track, a
    job search, a coding project, a piece of research). Deliberately no hard
    delete from the API: `DELETE /api/projects/{id}` sets status to
    "archived" (see app/routers/projects.py), matching the same
    never-lose-data posture as everything else in this app."""

    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_status", "status"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active | paused | completed | archived
    priority: Mapped[str] = mapped_column(String, default="medium")  # low | medium | high
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # Bumped on any create/update touching this project or one of its tasks —
    # what "Recently touched projects" (Mission Control) and Continue Where We
    # Left Off actually sort by, distinct from updated_at which SQLAlchemy's
    # onupdate would also bump on trivial edits.
    last_touched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- ECHO Layer 1: lightweight project memory profile (Phase 12) ---
    # A full separate ProjectMemoryProfile table was judged unnecessary — Project
    # is already the first-class identity; these are just the memory-relevant
    # fields it was missing, kept short/compact by construction (see
    # memory_retrieval.py's project-scoped MemoryBrief section).
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints_json: Mapped[list] = mapped_column(JSON, default=list)
    decisions_json: Mapped[list] = mapped_column(JSON, default=list)
    blockers_json: Mapped[list] = mapped_column(JSON, default=list)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project")


class Task(Base):
    """A single actionable item, optionally under a Project. source_type/
    source_id record where a task came from (e.g. "chat"/conversation_id) for
    traceability — never used to auto-execute anything, just provenance."""

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_due_at", "due_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="todo")  # todo | in_progress | blocked | done | cancelled
    priority: Mapped[str] = mapped_column(String, default="medium")  # low | medium | high
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "chat" | "manual"
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. a conversation_id
    tags: Mapped[list] = mapped_column(JSON, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project | None"] = relationship(back_populates="tasks")


class PersonaSettings(Base):
    """ECHO Human Persona Layer v1 — one row per tester_id. Consolidates the
    style-only settings from Phases 5/9/10/11/13/14 (humour, social
    preferences, opinion style, proactivity, default operational mode, base
    response-length preference) that had no existing home. This is entirely
    style — it can never weaken truthfulness/privacy/safety (see
    human_persona.py's CHARACTER_CODE, which is not stored here and is not
    user-editable)."""

    __tablename__ = "persona_settings"
    __table_args__ = (UniqueConstraint("tester_id", name="uq_persona_settings_tester_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tester_id: Mapped[str] = mapped_column(String, default="default")

    # Social preferences (Phase 13)
    preferred_name: Mapped[str | None] = mapped_column(String, nullable=True)
    allowed_nicknames: Mapped[list] = mapped_column(JSON, default=list)
    disliked_names: Mapped[list] = mapped_column(JSON, default=list)
    formality_level: Mapped[int] = mapped_column(Integer, default=2)  # 0-5
    emoji_level: Mapped[int] = mapped_column(Integer, default=1)  # 0-5
    asks_followup_questions: Mapped[str] = mapped_column(String, default="medium")  # low | medium | high
    bullet_points_preferred: Mapped[bool] = mapped_column(Boolean, default=True)
    examples_first: Mapped[bool] = mapped_column(Boolean, default=True)
    challenge_style: Mapped[str] = mapped_column(String, default="direct")  # gentle | direct | strict
    comfort_style: Mapped[str] = mapped_column(String, default="practical")  # practical | warm | minimal

    # Humour style (Phase 5)
    humour_level: Mapped[int] = mapped_column(Integer, default=2)  # 0-5
    sarcasm_level: Mapped[int] = mapped_column(Integer, default=1)  # 0-5
    dry_wit_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    humour_safety_mode: Mapped[str] = mapped_column(String, default="serious_context_low_humour")

    # Response shape (Phases 9, 10, 11)
    detail_level: Mapped[str] = mapped_column(String, default="normal")  # minimal|short|normal|detailed|exhaustive
    proactivity_level: Mapped[int] = mapped_column(Integer, default=2)  # 0-4
    default_operational_mode: Mapped[str] = mapped_column(String, default="normal")

    # Opinion style (Phase 14)
    recommendation_strength: Mapped[int] = mapped_column(Integer, default=3)  # 0-5
    disagreement_style: Mapped[str] = mapped_column(String, default="direct")  # soft | direct | firm

    # ECHO Local Intelligence Engine v1 — per-tester answer quality mode
    # (fast|balanced|deep), the one Local Intelligence setting the spec
    # calls out as user-adjustable at runtime rather than .env-only, same
    # as every other field on this table. Defaults match
    # config.py's LOCAL_ANSWER_QUALITY_MODE.
    local_answer_quality_mode: Mapped[str] = mapped_column(String, default="balanced")

    # ECHO Action + Reliability Core v1 — Voice-first Mode foundation. STT/TTS
    # themselves run entirely in the browser (Web Speech API) — these two
    # fields are just the persisted preference, same "settings, not a new
    # subsystem" shape as everything else on this table.
    # Defaults to push_to_talk, NOT off — voice input already worked
    # unconditionally (gated only by browser support) before this setting
    # existed; defaulting this to "off" would silently regress that for
    # every existing and new install the moment this column exists.
    voice_mode: Mapped[str] = mapped_column(String, default="push_to_talk")  # off|push_to_talk|hands_free_placeholder
    tts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class RelationshipProfile(Base):
    """How ECHO works with this specific tester — durable, user-editable, one
    row per tester_id. Deliberately NOT auto-written from chat: silently
    inferring relationship facts risks fabrication and sensitive-trait
    inference (Phase 2 rules 1-2), so this is a settings-form-style resource
    populated by explicit edits, with genuinely-accepted Atlas/preference
    memory candidates available as read-only suggestions (surfaced via the
    existing memory_candidates review queue, never auto-merged in)."""

    __tablename__ = "relationship_profiles"
    __table_args__ = (UniqueConstraint("tester_id", name="uq_relationship_profiles_tester_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tester_id: Mapped[str] = mapped_column(String, default="default")
    relationship_summary: Mapped[str] = mapped_column(Text, default="")
    working_style_summary: Mapped[str] = mapped_column(Text, default="")
    trust_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    support_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    communication_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ConversationMoodState(Base):
    """The most recently detected conversational mood for one conversation —
    a single upserted row, overwritten every turn, never accumulated as
    history and never merged into PersonaSettings/RelationshipProfile. This
    is what makes mood explicitly temporary: it lives and dies with the
    conversation row it's attached to (Phase 3 rule 4)."""

    __tablename__ = "conversation_mood_states"
    __table_args__ = (UniqueConstraint("conversation_id", name="uq_mood_state_conversation_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    tester_id: Mapped[str] = mapped_column(String, default="default")
    detected_mode: Mapped[str] = mapped_column(String, default="neutral")
    confidence: Mapped[str] = mapped_column(String, default="low")  # low | medium | high
    reason_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationThreadState(Base):
    """What a conversation was actively about, for Continue Where We Left Off
    / new-chat welcome suggestions — one upserted row per conversation.
    next_step stays null unless there's a real, retrievable next action to
    show (see human_persona.py) — never guessed, per Phase 12 rule 3."""

    __tablename__ = "conversation_thread_states"
    __table_args__ = (UniqueConstraint("conversation_id", name="uq_thread_state_conversation_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tester_id: Mapped[str] = mapped_column(String, default="default")
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    topic: Mapped[str] = mapped_column(String, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    linked_project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    linked_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active|paused|completed|stale
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PersonalRitual(Base):
    """An optional, user-toggleable short prompt ECHO can surface for a
    recurring moment (starting a coding session, a weekly review, ...). Never
    triggered automatically without an existing notification system — see
    Phase 15 rule 2; v1 only surfaces these via Mission Control and explicit
    chat requests, never an intrusive popup."""

    __tablename__ = "personal_rituals"
    __table_args__ = (UniqueConstraint("tester_id", "ritual_type", name="uq_ritual_tester_type"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tester_id: Mapped[str] = mapped_column(String, default="default")
    ritual_type: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_time: Mapped[str | None] = mapped_column(String, nullable=True)
    prompt_text: Mapped[str] = mapped_column(Text, default="")
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ============================================================================
# ECHO Action + Reliability Core v1
# ============================================================================


class ActionDefinition(Base):
    """One row per registered action (see app/services/action_system.py's
    _ACTIONS registry, which upserts these at startup). Deliberately not the
    source of truth for *behavior* — risk_level/requires_confirmation here
    mirror the registry's hardcoded definition and exist so the frontend can
    list/toggle actions without importing Python, and so `enabled` (the one
    field actually mutable by the user) persists across restarts."""

    __tablename__ = "action_definitions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String)  # memory|task|project|schedule|library|web|file|report|release|system|voice|camera
    risk_level: Mapped[str] = mapped_column(String, default="low")  # low|medium|high|destructive
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_permission_key: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ActionRun(Base):
    """A single invocation of an action, pending confirmation through to a
    final terminal state. input_json/result_json are already-safe-to-display
    structured data by construction — action_system.py never writes a raw
    exception or secret into either field (see _clean_error())."""

    __tablename__ = "action_runs"
    __table_args__ = (Index("ix_action_runs_status", "status"), Index("ix_action_runs_action_name", "action_name"))

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    action_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|running|completed|failed|cancelled
    risk_level: Mapped[str] = mapped_column(String, default="low")
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PermissionSetting(Base):
    """One row per permission_key (see permission_center.py's DEFAULT_
    PERMISSIONS for the full list + safe defaults). Single-install, not
    per-tester — this app has no multi-user auth (deliberately, this
    milestone) so permissions are a single shared local-device policy."""

    __tablename__ = "permission_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    permission_key: Mapped[str] = mapped_column(String, unique=True)
    level: Mapped[str] = mapped_column(String, default="ask_first")  # allowed|ask_first|disabled
    description: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String, default="low")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class EvaluationRun(Base):
    """One execution of the fixture case set (backend/tests/fixtures/
    evaluation_lab_cases.json re-read at runtime by evaluation_lab.py, not
    duplicated into the DB as its own table — the cases themselves are
    static and version-controlled, only *results* are a runtime concern)."""

    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String, default="running")  # running|completed|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result_summary: Mapped[str] = mapped_column(String, default="unknown")  # green|yellow|red|unknown
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[int] = mapped_column(Integer, default=0)

    results: Mapped[list["EvaluationResult"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (Index("ix_evaluation_results_run_id", "run_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"))
    case_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="fail")  # pass|fail|warning
    reason: Mapped[str] = mapped_column(Text, default="")
    observed_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped["EvaluationRun"] = relationship(back_populates="results")


class KnowledgeItem(Base):
    """User-visible, user-editable knowledge — distinct from Atlas (internal/
    adaptive memory, never directly edited) and from PersonalRitual/
    RelationshipProfile (persona settings, not knowledge). Soft-archived via
    archived_at, matching Project/Task's never-lose-data convention."""

    __tablename__ = "knowledge_items"
    __table_args__ = (Index("ix_knowledge_items_item_type", "item_type"), Index("ix_knowledge_items_project_id", "project_id"))

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(Text, default="")
    item_type: Mapped[str] = mapped_column(String, default="note")  # note|decision|source|summary|idea|bug|release_note|study_note|prompt|reference|personal_rule
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)  # e.g. "conversation" | "manual" | "release"
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|unverified
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationSummary(Base):
    """A compact, decision-oriented summary of one conversation — what
    "Continue Where We Left Off" and Knowledge Vault export both read from.
    *_json fields are plain lists of short strings, never raw prompt/debug
    text (see conversation_summary.py's _parse_summary_json degrade path)."""

    __tablename__ = "conversation_summaries"
    __table_args__ = (Index("ix_conversation_summaries_conversation_id", "conversation_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    title: Mapped[str] = mapped_column(String, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    decisions_json: Mapped[list] = mapped_column(JSON, default=list)
    tasks_json: Mapped[list] = mapped_column(JSON, default=list)
    open_questions_json: Mapped[list] = mapped_column(JSON, default=list)
    next_steps_json: Mapped[list] = mapped_column(JSON, default=list)
    memories_to_review_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # --- ECHO Layer 1 (Phase 11): distinguishes a full end-of-conversation
    # summary (the only kind this app generates today) from the other summary
    # granularities Layer 1's spec anticipates for later layers. ---
    summary_type: Mapped[str] = mapped_column(String, default="final")  # rolling|final|topic|project_update|decision_log
    candidate_memory_ids_json: Mapped[list] = mapped_column(JSON, default=list)


class ReleaseRecord(Base):
    __tablename__ = "release_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    version_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft|testing|green|yellow|red|released
    summary: Mapped[str] = mapped_column(Text, default="")
    git_commit: Mapped[str | None] = mapped_column(String, nullable=True)
    git_tag: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    checks: Mapped[list["ReleaseCheck"]] = relationship(back_populates="release", cascade="all, delete-orphan")
    artifacts: Mapped[list["ReleaseArtifact"]] = relationship(back_populates="release", cascade="all, delete-orphan")


class ReleaseCheck(Base):
    __tablename__ = "release_checks"
    __table_args__ = (Index("ix_release_checks_release_id", "release_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    release_id: Mapped[str] = mapped_column(ForeignKey("release_records.id"))
    check_name: Mapped[str] = mapped_column(String)
    platform: Mapped[str] = mapped_column(String)  # backend|web|android|windows|docs|manual
    command: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="not_run")  # pass|fail|warning|not_run
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    release: Mapped["ReleaseRecord"] = relationship(back_populates="checks")


class ReleaseArtifact(Base):
    __tablename__ = "release_artifacts"
    __table_args__ = (Index("ix_release_artifacts_release_id", "release_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    release_id: Mapped[str] = mapped_column(ForeignKey("release_records.id"))
    platform: Mapped[str] = mapped_column(String)
    artifact_type: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    release: Mapped["ReleaseRecord"] = relationship(back_populates="artifacts")


class ToolDefinition(Base):
    """Internal tool registry (app/services/tool_registry.py's _TOOLS,
    upserted at startup) — not a public marketplace, no third-party tool
    loading. Each tool wraps one existing service function; this table is
    the enable/disable + permission/risk metadata layer over that registry,
    same relationship ActionDefinition has to action_system.py."""

    __tablename__ = "tool_definitions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tool_name: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    risk_level: Mapped[str] = mapped_column(String, default="low")
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    permission_key: Mapped[str | None] = mapped_column(String, nullable=True)
    input_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class ToolRun(Base):
    __tablename__ = "tool_runs"
    __table_args__ = (Index("ix_tool_runs_tool_name", "tool_name"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tool_name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|completed|failed|blocked
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ============================================================================
# ECHO Cognitive Core v1 — World Model + Task Understanding Engine.
# Complements Atlas (internal adaptive memory of facts about the user) with a
# structured understanding layer: durable concepts and how they relate, task
# understanding for complex requests, reusable skill patterns, and simple
# cause-effect notes. Everything here is deterministic (no model call) — see
# app/services/cognitive_core.py's module docstring for why.
# ============================================================================


class CognitiveConcept(Base):
    """A durable, named thing ECHO's world model knows about (a system, a
    tool, a person preference, a goal, a risk, ...) — not a raw fact like
    Atlas stores, but a node other concepts can relate to. Soft-archived,
    never hard-deleted, matching this app's established convention."""

    __tablename__ = "cognitive_concepts"
    __table_args__ = (
        Index("ix_cognitive_concepts_name", "name"),
        Index("ix_cognitive_concepts_concept_type", "concept_type"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # project|system|tool|file|process|person_preference|domain|technical|goal|constraint|risk|source|other
    concept_type: Mapped[str] = mapped_column(String, default="other")
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|inferred
    # atlas_memory|conversation|knowledge_vault|library|project|task|manual|system|inferred
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CognitiveRelationship(Base):
    """A directed edge between two concepts — e.g. "Android APK" --depends_on--> "Capacitor sync".
    No foreign-key constraint on from/to (SQLite + this repo's existing
    style doesn't enforce FKs at the DB level elsewhere either) but both are
    expected to be CognitiveConcept ids."""

    __tablename__ = "cognitive_relationships"
    __table_args__ = (
        Index("ix_cognitive_relationships_from", "from_concept_id"),
        Index("ix_cognitive_relationships_to", "to_concept_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    from_concept_id: Mapped[str] = mapped_column(String)
    to_concept_id: Mapped[str] = mapped_column(String)
    # uses|depends_on|causes|blocks|enables|part_of|conflicts_with|similar_to|requires|produces|verifies|belongs_to
    relation_type: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|inferred
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class TaskUnderstanding(Base):
    """A structured read of one complex user request — goal, what's known/
    unknown, constraints, success criteria, risks. Only created for
    medium/hard-difficulty requests (see cognitive_core.py's gating rule) —
    not one row per chat message. The *_json fields are short lists of
    plain strings, never raw chain-of-thought.

    ECHO Layer 2A extended this in place (the milestone's own "unified task
    model") rather than creating a parallel table — same consolidation
    pattern Layer 1 used for AtlasEntry. `task_type` (the v1 taxonomy) is
    untouched for backward compatibility; `task_category` carries the
    broader Layer 2A taxonomy alongside it."""

    __tablename__ = "task_understandings"
    __table_args__ = (
        Index("ix_task_understandings_conversation_id", "conversation_id"),
        Index("ix_task_understandings_project_id", "project_id"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    user_message: Mapped[str] = mapped_column(Text)
    goal_summary: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String, default="general")
    task_type: Mapped[str] = mapped_column(String, default="other")
    known_facts_json: Mapped[list] = mapped_column(JSON, default=list)
    unknowns_json: Mapped[list] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list] = mapped_column(JSON, default=list)
    success_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    risks_json: Mapped[list] = mapped_column(JSON, default=list)
    relevant_concepts_json: Mapped[list] = mapped_column(JSON, default=list)
    recommended_next_step: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|incomplete
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # --- ECHO Layer 2A: Cognitive Core v2 (all additive, all default-safe) ---
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    parent_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    normalized_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    # question|explanation|research|coding|debugging|planning|decision|document|
    # action|reminder|learning|emotional_support|creative|mixed — the Layer 2A
    # taxonomy, independent of the legacy `task_type` above.
    task_category: Mapped[str] = mapped_column(String, default="mixed")
    urgency: Mapped[str] = mapped_column(String, default="normal")  # low|normal|high|urgent
    complexity: Mapped[str] = mapped_column(String, default="moderate")  # trivial|simple|moderate|complex
    primary_goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    secondary_goals_json: Mapped[list] = mapped_column(JSON, default=list)
    user_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from the legacy `constraints_json` (kept as-is, treated as
    # "explicit" for backward compatibility): inferred constraints are new
    # and always separately labelled, never merged into the explicit list.
    inferred_constraints_json: Mapped[list] = mapped_column(JSON, default=list)
    preferences_json: Mapped[list] = mapped_column(JSON, default=list)
    forbidden_actions_json: Mapped[list] = mapped_column(JSON, default=list)
    uncertainties_json: Mapped[list] = mapped_column(JSON, default=list)
    # `unknowns_json` (legacy) stays as the general missing-knowledge list;
    # `missing_information_json` is the Layer 2A classified version (each
    # item tagged blocking/important/optional/safely_inferable — see
    # task_understanding_v2.py).
    missing_information_json: Mapped[list] = mapped_column(JSON, default=list)
    failure_conditions_json: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_tests_json: Mapped[list] = mapped_column(JSON, default=list)
    required_capabilities_json: Mapped[list] = mapped_column(JSON, default=list)
    candidate_skills_json: Mapped[list] = mapped_column(JSON, default=list)
    candidate_tools_json: Mapped[list] = mapped_column(JSON, default=list)
    required_sources_json: Mapped[list] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String, default="low")  # low|medium|high|critical
    consequence_level: Mapped[str] = mapped_column(String, default="low")  # low|medium|high|critical
    reversibility: Mapped[str] = mapped_column(String, default="reversible")  # reversible|hard_to_reverse|irreversible
    confirmation_requirement: Mapped[bool] = mapped_column(Boolean, default=False)
    # draft|analyzing|ready|needs_clarification|stale|superseded
    status: Mapped[str] = mapped_column(String, default="ready")
    intent_hierarchy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    scope: Mapped[str] = mapped_column(String, default="current_turn")  # current_turn|conversation|project|recurring_workflow|long_term_goal
    clarification_questions_json: Mapped[list] = mapped_column(JSON, default=list)
    # A short hash of the normalized request + key context, used to detect
    # whether the task has "materially changed" (Phase 7 rule) without
    # storing anything sensitive.
    content_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class SkillPattern(Base):
    """A reusable, named workflow ECHO knows how to run — a checklist, not a
    script: nothing here is auto-executed (see app/services/action_system.py
    for actual side-effecting actions, which are a separate, permission-
    gated system). Soft-archived, never hard-deleted."""

    __tablename__ = "skill_patterns"
    __table_args__ = (Index("ix_skill_patterns_category", "category"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    # coding|release|research|study|planning|troubleshooting|writing|personal|system|other
    category: Mapped[str] = mapped_column(String, default="other")
    trigger_patterns_json: Mapped[list] = mapped_column(JSON, default=list)
    steps_json: Mapped[list] = mapped_column(JSON, default=list)
    required_tools_json: Mapped[list] = mapped_column(JSON, default=list)
    success_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    common_failures_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CausalNote(Base):
    """A single, simple cause -> effect fact ECHO can draw on for risk/
    troubleshooting reasoning — e.g. "If Ollama is offline -> local chat
    fails." Not a general knowledge base; deliberately narrow and
    ECHO-operations-focused for v1."""

    __tablename__ = "causal_notes"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    cause: Mapped[str] = mapped_column(Text)
    effect: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|inferred
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CognitiveBrief(Base):
    """The compact, internal-only summary handed to the prompt builder for
    one turn — never shown in normal chat UI (see cognitive_core.py). Stored
    so the Cognitive Core page can show a history of recent briefs without
    needing to re-derive them."""

    __tablename__ = "cognitive_briefs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    task_understanding_id: Mapped[str | None] = mapped_column(String, nullable=True)
    brief_text: Mapped[str] = mapped_column(Text)
    selected_concepts_json: Mapped[list] = mapped_column(JSON, default=list)
    selected_skills_json: Mapped[list] = mapped_column(JSON, default=list)
    selected_context_sources_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # --- ECHO Layer 2A: CognitiveBrief v2 fields (Phase 6) ---
    candidate_tools_json: Mapped[list] = mapped_column(JSON, default=list)
    risk_and_confirmation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|incomplete
    next_reasoning_stage: Mapped[str | None] = mapped_column(String, nullable=True)


class CognitiveSettings(Base):
    """A single mutable row (id="singleton") backing GET/PATCH
    /api/cognitive/settings — config.py's cognitive_* fields are the
    install's *initial* defaults (env-configured, requires a restart to
    change); this table is the actually-mutable runtime source of truth,
    same "DB is mutable, config.py is just the starting default" split
    Permission Center already established for its own settings."""

    __tablename__ = "cognitive_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: "singleton")
    cognitive_core_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cognitive_concept_extraction_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cognitive_skill_matching_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cognitive_show_developer_diagnostics: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ============================================================================
# ECHO Layer 2B — Systems Thinking and Simulation Engine.
#
# SystemModel is deliberately NOT a second graph database — per the
# milestone's own rule ("integrate with the existing knowledge graph
# instead of creating an unrelated graph database"), it's a named, scoped
# *view* over the CognitiveConcept/CognitiveRelationship graph Cognitive
# Core v1 already built: SystemModelNode tags which existing concepts
# belong to a given system (plus system-specific attributes — role/state/
# owner/evidence that a bare CognitiveConcept doesn't carry), and the edges
# between those nodes are just the existing CognitiveRelationship rows,
# with the relation_type vocabulary extended (it's a free-text column, not
# a DB enum, so this is additive) to cover consumes/communicates_with/
# mitigates/feedback_to alongside the pre-existing set.
# ============================================================================


class SystemModel(Base):
    """A named, scoped system view — 'this project's backend architecture,'
    'this study plan,' etc. Soft-archived, matching this app's convention."""

    __tablename__ = "system_models"
    __table_args__ = (Index("ix_system_models_project_id", "project_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    # software_architecture|project_plan|physical_system|organisational_workflow|
    # study_plan|decision_context
    scope: Mapped[str] = mapped_column(String, default="software_architecture")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SystemModelNode(Base):
    """Tags one CognitiveConcept as a member of one SystemModel, with the
    system-specific attributes a bare world-model concept doesn't carry.
    A concept can belong to more than one system model."""

    __tablename__ = "system_model_nodes"
    __table_args__ = (
        Index("ix_system_model_nodes_system_model_id", "system_model_id"),
        UniqueConstraint("system_model_id", "concept_id", name="uq_system_model_node"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    system_model_id: Mapped[str] = mapped_column(String)
    concept_id: Mapped[str] = mapped_column(String)
    # component|actor|resource|constraint|interface|external_factor
    node_role: Mapped[str] = mapped_column(String, default="component")
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    owner: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|inferred
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Simulation(Base):
    """One bounded, non-executing simulation run — forecasts and estimates,
    never facts (rule: never claim calibrated certainty). References a
    SystemModel for dependency-aware scenario generation when one exists;
    works without one for a pure decision-context simulation."""

    __tablename__ = "simulations"
    __table_args__ = (Index("ix_simulations_task_id", "task_id"), Index("ix_simulations_system_model_id", "system_model_id"))

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)  # TaskUnderstanding.id
    system_model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    objective: Mapped[str] = mapped_column(Text)
    baseline_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    constraints_json: Mapped[list] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list] = mapped_column(JSON, default=list)
    max_scenarios: Mapped[int] = mapped_column(Integer, default=4)
    max_steps: Mapped[int] = mapped_column(Integer, default=12)
    time_horizon: Mapped[str | None] = mapped_column(String, nullable=True)
    evaluation_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    risk_tolerance: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high
    status: Mapped[str] = mapped_column(String, default="completed")  # running|completed|aborted|failed
    too_uncertain_to_rank: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    scenarios: Mapped[list["SimulationScenario"]] = relationship(back_populates="simulation", cascade="all, delete-orphan")


class SimulationScenario(Base):
    """One candidate strategy within a simulation — including the
    deterministic baseline/no-action scenario. Never executed — see
    action_system.py for the separate, permission-gated real-execution path."""

    __tablename__ = "simulation_scenarios"
    __table_args__ = (Index("ix_simulation_scenarios_simulation_id", "simulation_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    simulation_id: Mapped[str] = mapped_column(ForeignKey("simulations.id"))
    label: Mapped[str] = mapped_column(String)  # "baseline" | "address_bottleneck" | ...
    strategy: Mapped[str] = mapped_column(Text)
    assumptions_json: Mapped[list] = mapped_column(JSON, default=list)
    steps_json: Mapped[list] = mapped_column(JSON, default=list)
    predicted_outcomes_json: Mapped[list] = mapped_column(JSON, default=list)
    dependencies_json: Mapped[list] = mapped_column(JSON, default=list)
    costs_json: Mapped[list] = mapped_column(JSON, default=list)
    risks_json: Mapped[list] = mapped_column(JSON, default=list)
    failure_modes_json: Mapped[list] = mapped_column(JSON, default=list)
    reversibility: Mapped[str] = mapped_column(String, default="reversible")  # reversible|hard_to_reverse|irreversible
    evidence_quality: Mapped[str] = mapped_column(String, default="low")  # low|medium|high
    confidence_band: Mapped[str] = mapped_column(String, default="wide")  # narrow|moderate|wide
    uncertainty_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How much this scenario's forecast rests on unverified assumptions
    # rather than graph-derived evidence — separate from evidence_quality/
    # confidence_band, which describe the forecast itself, not what it's
    # sensitive to changing.
    sensitivity_label: Mapped[str] = mapped_column(String, default="low")  # low|moderate|high
    sensitivity_note: Mapped[str] = mapped_column(Text, default="")
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    steps_blocked: Mapped[int] = mapped_column(Integer, default=0)
    stopped_reason: Mapped[str | None] = mapped_column(String, nullable=True)  # None if completed cleanly
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set by compare_scenarios(); null until ranked
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    simulation: Mapped["Simulation"] = relationship(back_populates="scenarios")


# ============================================================================
# ECHO Layer 2C — Decision Engine and Planning Engine.
#
# The Decision Engine recommends; it never makes an irreversible choice for
# the user (rule from the milestone spec). DecisionOption rows can be
# user-typed from scratch, OR seeded from a Layer 2B SimulationScenario via
# source_scenario_id — the two systems interoperate without either
# duplicating the other's storage. The Planning Engine deliberately does NOT
# duplicate Task/Project: a PlanStep only becomes a real Task row after
# explicit plan approval and an explicit "materialise" call (see
# services/plan_engine.py's materialise_plan(), which reuses
# action_system.run_action() rather than writing to the tasks table
# directly).
# ============================================================================


class DecisionCase(Base):
    """One structured decision under analysis. Recommendation rationale is
    stored as a concise evidence summary (report_json) — never a raw
    chain-of-thought dump."""

    __tablename__ = "decision_cases"
    __table_args__ = (Index("ix_decision_cases_status", "status"), Index("ix_decision_cases_project_id", "project_id"))

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    question: Mapped[str] = mapped_column(Text)
    objective: Mapped[str] = mapped_column(Text)
    constraints_json: Mapped[list] = mapped_column(JSON, default=list)
    stakeholders_json: Mapped[list] = mapped_column(JSON, default=list)
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    assumptions_json: Mapped[list] = mapped_column(JSON, default=list)
    uncertainty: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_horizon: Mapped[str | None] = mapped_column(String, nullable=True)
    reversibility: Mapped[str] = mapped_column(String, default="reversible")  # reversible|hard_to_reverse|irreversible
    consequence_level: Mapped[str] = mapped_column(String, default="low")  # low|medium|high|critical
    status: Mapped[str] = mapped_column(String, default="draft")  # draft|analysed|selected|cancelled
    # Optional interop with Layer 2B — a decision can be seeded from a
    # completed simulation's scenarios, but works fully standalone too.
    simulation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    recommended_option_id: Mapped[str | None] = mapped_column(String, nullable=True)
    no_clear_winner: Mapped[bool] = mapped_column(Boolean, default=False)
    # The DecisionReport (Phase 3) — decision_summary, why_this_option,
    # key_tradeoffs, hard_constraints_checked, major_assumptions,
    # major_uncertainties, risks_and_mitigations, alternatives,
    # reversibility, evidence_quality, confidence_band,
    # next_information_to_collect, user_confirmation_needed.
    report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    options: Mapped[list["DecisionOption"]] = relationship(back_populates="decision_case", cascade="all, delete-orphan")
    criteria: Mapped[list["DecisionCriterion"]] = relationship(back_populates="decision_case", cascade="all, delete-orphan")


class DecisionOption(Base):
    """One candidate choice within a DecisionCase."""

    __tablename__ = "decision_options"
    __table_args__ = (Index("ix_decision_options_decision_case_id", "decision_case_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    decision_case_id: Mapped[str] = mapped_column(ForeignKey("decision_cases.id"))
    label: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits_json: Mapped[list] = mapped_column(JSON, default=list)
    drawbacks_json: Mapped[list] = mapped_column(JSON, default=list)
    direct_cost: Mapped[str | None] = mapped_column(Text, nullable=True)
    opportunity_cost: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_estimate: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies_json: Mapped[list] = mapped_column(JSON, default=list)
    risks_json: Mapped[list] = mapped_column(JSON, default=list)
    failure_modes_json: Mapped[list] = mapped_column(JSON, default=list)
    reversibility: Mapped[str] = mapped_column(String, default="reversible")  # reversible|hard_to_reverse|irreversible
    evidence_quality: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|inferred
    # Explicit signal (set by whoever creates the option — a caller, not a
    # keyword guess) naming which hard DecisionCriterion.name values this
    # option is known to violate. Hard-constraint elimination is then a
    # simple, honest rule ("eliminate if a hard criterion is in this list"),
    # never a fragile text-matching inference.
    violates_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    # Explicit per-criterion rating (0.0-1.0), keyed by DecisionCriterion.id —
    # set by the caller/user, never inferred from free text. Weighted scoring
    # is then a plain weighted average of these, so "score" is never a
    # fabricated number beyond what was explicitly rated.
    criterion_ratings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Set by hard-constraint elimination (Phase 2) — eliminated options are
    # kept (never deleted) so the report can honestly say why they were cut.
    eliminated: Mapped[bool] = mapped_column(Boolean, default=False)
    eliminated_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set by weighted scoring when the user has approved criterion weights;
    # null whenever weighted scoring wasn't used (e.g. hard-elimination-only
    # or trade-off-matrix-only analysis) — never a fabricated number.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pareto_dominated: Mapped[bool] = mapped_column(Boolean, default=False)
    source_scenario_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    decision_case: Mapped["DecisionCase"] = relationship(back_populates="options")


class DecisionCriterion(Base):
    """One evaluation criterion for a DecisionCase — weight is only ever set
    by explicit user approval (Phase 2's non-negotiable rule: preferences
    must be user-controlled, never a silently-inferred optimisation
    target)."""

    __tablename__ = "decision_criteria"
    __table_args__ = (Index("ix_decision_criteria_decision_case_id", "decision_case_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    decision_case_id: Mapped[str] = mapped_column(ForeignKey("decision_cases.id"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String, default="user_stated")  # user_stated|inferred|from_simulation
    importance: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high
    hard_or_soft: Mapped[str] = mapped_column(String, default="soft")  # hard|soft
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)  # only set via explicit user approval
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    decision_case: Mapped["DecisionCase"] = relationship(back_populates="criteria")


class Plan(Base):
    """A concrete, approvable plan of steps toward an objective — never
    auto-derived into real Tasks; see materialise_plan()."""

    __tablename__ = "plans"
    __table_args__ = (Index("ix_plans_status", "status"), Index("ix_plans_project_id", "project_id"))

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    objective: Mapped[str] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions_json: Mapped[list] = mapped_column(JSON, default=list)
    constraints_json: Mapped[list] = mapped_column(JSON, default=list)
    success_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    estimated_effort: Mapped[str | None] = mapped_column(String, nullable=True)  # a range/description, never a fake precise number
    owner: Mapped[str] = mapped_column(String, default="user")
    # proposed|approved|active|blocked|completed|failed|cancelled — exactly
    # the 7 states the milestone spec requires plans to distinguish.
    status: Mapped[str] = mapped_column(String, default="proposed")
    evidence_json: Mapped[list] = mapped_column(JSON, default=list)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_case_id: Mapped[str | None] = mapped_column(String, nullable=True)
    system_model_id: Mapped[str | None] = mapped_column(String, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, nullable=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    superseded_by_plan_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    steps: Mapped[list["PlanStep"]] = relationship(back_populates="plan", cascade="all, delete-orphan", order_by="PlanStep.order_index")
    milestones: Mapped[list["Milestone"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    dependencies: Mapped[list["PlanDependency"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    resource_requirements: Mapped[list["PlanResourceRequirement"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    risks: Mapped[list["PlanRisk"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    revisions: Mapped[list["PlanRevision"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanStep(Base):
    """One ordered step in a Plan. materialised_task_id stays null until the
    plan is approved and materialise_plan() is explicitly called."""

    __tablename__ = "plan_steps"
    __table_args__ = (Index("ix_plan_steps_plan_id", "plan_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimated_effort: Mapped[str | None] = mapped_column(String, nullable=True)
    owner: Mapped[str] = mapped_column(String, default="user")
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|in_progress|blocked|completed|failed|cancelled
    verification_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    # Set by _detect_parallel_groups() — steps sharing a non-null group id
    # have no dependency ordering between them and can run in parallel.
    parallel_group: Mapped[str | None] = mapped_column(String, nullable=True)
    materialised_task_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    plan: Mapped["Plan"] = relationship(back_populates="steps")


class Milestone(Base):
    """A checkpoint within a Plan — reached only once its target steps are
    all completed and its verification criteria are met."""

    __tablename__ = "plan_milestones"
    __table_args__ = (Index("ix_plan_milestones_plan_id", "plan_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_step_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    verification_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|reached|missed
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    plan: Mapped["Plan"] = relationship(back_populates="milestones")


class PlanDependency(Base):
    """A directed 'from_step must complete before to_step can start' edge —
    the basis for prerequisite/critical-path/parallel-step detection."""

    __tablename__ = "plan_dependencies"
    __table_args__ = (Index("ix_plan_dependencies_plan_id", "plan_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    from_step_id: Mapped[str] = mapped_column(String)
    to_step_id: Mapped[str] = mapped_column(String)
    dependency_type: Mapped[str] = mapped_column(String, default="blocks")  # blocks|informs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    plan: Mapped["Plan"] = relationship(back_populates="dependencies")


class PlanResourceRequirement(Base):
    """A named resource need for a plan or one of its steps. amount is a
    descriptive string, never a fabricated precise quantity — this app has
    no real budget/personnel data to draw a number from."""

    __tablename__ = "plan_resource_requirements"
    __table_args__ = (Index("ix_plan_resource_requirements_plan_id", "plan_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    step_id: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_name: Mapped[str] = mapped_column(String)
    resource_type: Mapped[str] = mapped_column(String, default="other")  # time|tool|skill|external|other
    amount: Mapped[str | None] = mapped_column(String, nullable=True)
    availability_status: Mapped[str] = mapped_column(String, default="unknown")  # available|unavailable|unknown
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    plan: Mapped["Plan"] = relationship(back_populates="resource_requirements")


class PlanRisk(Base):
    """A risk identified for a plan or one of its steps."""

    __tablename__ = "plan_risks"
    __table_args__ = (Index("ix_plan_risks_plan_id", "plan_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    step_id: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str] = mapped_column(Text)
    likelihood: Mapped[str] = mapped_column(String, default="unknown")  # low|medium|high|unknown
    impact: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high
    mitigation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="open")  # open|mitigated|accepted|occurred
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    plan: Mapped["Plan"] = relationship(back_populates="risks")


class PlanRevision(Base):
    """An immutable history record of a replanning event — completed history
    is never rewritten (Phase 6's non-negotiable rule)."""

    __tablename__ = "plan_revisions"
    __table_args__ = (Index("ix_plan_revisions_plan_id", "plan_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(ForeignKey("plans.id"))
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    reason: Mapped[str] = mapped_column(Text)
    trigger: Mapped[str] = mapped_column(String, default="user_correction")  # failure|new_evidence|changed_constraint|missed_deadline|user_correction
    changed_step_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    previous_status: Mapped[str | None] = mapped_column(String, nullable=True)
    new_status: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    plan: Mapped["Plan"] = relationship(back_populates="revisions")


# ============================================================================
# ECHO Operational Self-Model v1 — an honest, explicitly non-conscious record
# of ECHO's own operating state for one turn (goal/mode/confidence/risks/
# limits/next action), distinct from Atlas (facts about the user) and
# Cognitive Core (facts about the task/world). Deterministic construction
# only — see app/services/operational_self_model.py's module docstring.
# Consolidates what would otherwise be two near-duplicate concepts ("Operational
# Self-Model" and "Inner State" from the two source specs for this milestone)
# into one table, reusing the existing PersonaSettings.default_operational_mode
# / ConversationMoodState machinery for mode/mood rather than re-detecting it.
# ============================================================================


class OperationalStateSnapshot(Base):
    """One row per meaningful (non-trivial) chat turn — never one per message,
    see operational_self_model.py's same complexity gate Cognitive Core uses.
    All *_json fields are short lists of plain strings, never raw chain-of-
    thought or a dump of the full prompt. intensity/expires_at let a snapshot
    read as a genuinely temporary operational state, not a permanent trait."""

    __tablename__ = "operational_state_snapshots"
    __table_args__ = (Index("ix_operational_state_snapshots_conversation_id", "conversation_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    current_goal: Mapped[str] = mapped_column(Text)
    current_mode: Mapped[str] = mapped_column(String, default="normal")
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|unverified
    known_limits_json: Mapped[list] = mapped_column(JSON, default=list)
    active_risks_json: Mapped[list] = mapped_column(JSON, default=list)
    relevant_memory_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    relationship_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    permissions_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_best_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    should_ask_confirmation: Mapped[bool] = mapped_column(Boolean, default=False)
    should_use_tools_json: Mapped[list] = mapped_column(JSON, default=list)
    should_not_do_json: Mapped[list] = mapped_column(JSON, default=list)
    # Not emotion — an honest "how strongly does this operational state apply
    # right now" scalar (e.g. a troubleshooting mode triggered by one mild
    # keyword vs. three explicit failure reports), 0 (barely) - 5 (strongly).
    intensity: Mapped[int] = mapped_column(Integer, default=3)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class InterfaceSettings(Base):
    """A single mutable row (id="singleton") backing GET/PATCH
    /api/interface-settings — same "DB is the mutable runtime source of
    truth" pattern as CognitiveSettings above. Covers sidebar/top-bar
    simplification (ECHO Interface Simplification v1) and the operational
    self-model's own visibility controls, single-install/local-device, no
    per-tester scoping (matching PermissionSetting's precedent)."""

    __tablename__ = "interface_settings"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: "singleton")
    show_advanced_nav: Mapped[bool] = mapped_column(Boolean, default=False)
    compact_sidebar: Mapped[bool] = mapped_column(Boolean, default=False)
    show_developer_controls: Mapped[bool] = mapped_column(Boolean, default=False)
    show_usage_in_topbar: Mapped[bool] = mapped_column(Boolean, default=True)
    show_model_selector: Mapped[bool] = mapped_column(Boolean, default=True)
    # Off by default — Part 4/8's "poetic/creative language only when
    # requested" rule. When off, the persona style directive actively steers
    # away from mystical/fantasy narration; when on, that steering relaxes.
    poetic_language_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    operational_self_model_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # never | only_when_helpful | developer_mode_only
    show_inner_state: Mapped[str] = mapped_column(String, default="only_when_helpful")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ============================================================================
# ECHO Layer 0 — Infrastructure Foundation v1
# ============================================================================


class SchemaVersion(Base):
    """A single row tracking which schema version this database is on —
    not a migration engine (this app deliberately doesn't introduce Alembic
    in v1, see ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md's rationale), just
    a detectable marker so `/api/system/diagnostics` and
    `scripts/check_database.ps1` can report something concrete instead of
    "unknown." Bumped by hand in db.py's init_db() only when a schema change
    genuinely warrants it — this table existing at all, plus its `version`
    value, is the signal; nothing here runs a migration automatically."""

    __tablename__ = "schema_version"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: "singleton")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


# ============================================================================
# ECHO Layer 1 — Memory Foundation v1
#
# AtlasEntry (above) and MemoryCandidate (above) were extended in place to
# serve as the unified memory record and candidate pipeline — see their
# docstrings. The six tables below are new only because nothing existing
# covers what they represent: evidence records, memory-instance relationships
# (deliberately separate from CognitiveConcept/CognitiveRelationship, which
# model named *world concepts*, not individual memory statements — a
# CognitiveConcept like "Ollama" is one node; many different AtlasEntry rows
# can each independently relate to it), conflicts, consolidation history,
# edit history, and usefulness feedback. No FK constraints on memory-id
# columns, matching this repo's established cross-reference style (see
# CognitiveRelationship) and avoiding SQLite FK-enforcement (Layer 0)
# rejecting a reference to a memory that was since hard-deleted.
# ============================================================================


class MemoryEvidence(Base):
    """Phase 3 — supporting/contradicting evidence for one AtlasEntry. Most
    memories don't need this (epistemic_status + source on AtlasEntry itself
    covers the common case); this exists for the less common case of
    multiple, possibly-conflicting pieces of evidence for one memory."""

    __tablename__ = "memory_evidence"
    __table_args__ = (Index("ix_memory_evidence_memory_id", "memory_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    memory_id: Mapped[str] = mapped_column(String)
    # user_statement|uploaded_file|conversation|trusted_source|web_source|project_state|
    # test_output|tool_result|inference|manual_verification
    evidence_type: Mapped[str] = mapped_column(String)
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String, nullable=True)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)  # kept short by convention, never a full page
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    supports_or_contradicts: Mapped[str] = mapped_column(String, default="supports")  # supports|contradicts
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryRelationship(Base):
    """Phase 2 — a directed edge between two AtlasEntry memories (not
    CognitiveConcept world-model nodes — see module docstring above for the
    documented decision on why these are a separate graph layer)."""

    __tablename__ = "memory_relationships"
    __table_args__ = (
        Index("ix_memory_relationships_source", "source_memory_id"),
        Index("ix_memory_relationships_target", "target_memory_id"),
        UniqueConstraint("source_memory_id", "target_memory_id", "relationship_type", name="uq_memory_relationship_edge"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_memory_id: Mapped[str] = mapped_column(String)
    target_memory_id: Mapped[str] = mapped_column(String)
    # related_to|part_of|belongs_to_project|supports|contradicts|supersedes|derived_from|
    # depends_on|caused_by|preference_for|skill_for|person_related_to|task_related_to|
    # evidence_for|example_of|version_of|duplicates|temporal_predecessor|temporal_successor
    relationship_type: Mapped[str] = mapped_column(String)
    confidence: Mapped[str] = mapped_column(String, default="medium")  # high|medium|low|inferred
    source_type: Mapped[str | None] = mapped_column(String, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active|deactivated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class MemoryConflict(Base):
    """Phase 6 — a detected conflict between two or more memories, richer
    than the plain word-overlap "plausibly conflicting" flag already used at
    candidate-creation time (see memory_conflicts.py) — this is for conflicts
    that have been classified by type/severity and may need user review."""

    __tablename__ = "memory_conflicts_v2"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    memory_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    # direct_contradiction|temporal_update|scope_conflict|source_disagreement|
    # user_preference_change|project_version_conflict|identity_ambiguity|
    # confidence_conflict|environment_drift
    conflict_type: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String, default="medium")  # low|medium|high|critical
    status: Mapped[str] = mapped_column(String, default="open")  # open|auto_resolved|user_review_required|resolved|ignored
    # choose_newer|choose_verified|retain_both_with_scope|mark_outdated|merge|user_decision|unresolved
    recommended_resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryConsolidationEvent(Base):
    """Phase 5 — a record of what the consolidation engine did (or
    recommended) when it found duplicate/near-duplicate/superseding
    memories, so consolidation is auditable and, where practical, reversible."""

    __tablename__ = "memory_consolidation_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    source_memory_ids_json: Mapped[list] = mapped_column(JSON, default=list)
    result_memory_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # keep_both|merge|update_existing|supersede_existing|reject_duplicate|ask_user|create_summary_memory
    action: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    reversible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MemoryRevision(Base):
    """Phase 15 — an append-only edit-history trail for one AtlasEntry. Never
    stores secrets (memory_privacy.redact_for_log is applied before a
    revision derived from system-generated content is written)."""

    __tablename__ = "memory_revisions"
    __table_args__ = (Index("ix_memory_revisions_memory_id", "memory_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    memory_id: Mapped[str] = mapped_column(String)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    previous_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # created|edited|confirmed|merged|superseded|archived|restored|deleted|reclassified|
    # confidence_changed|provenance_added
    change_type: Mapped[str] = mapped_column(String)
    change_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    changed_by: Mapped[str] = mapped_column(String, default="system")  # "user" | "system"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MemoryFeedback(Base):
    """Phase 21 — lets the user correct retrieval/capture behaviour after the
    fact. Used only to nudge retrieval ranking and flag review candidates —
    never to silently rewrite truth from a single negative rating (see
    memory_retrieval.py's use of this table)."""

    __tablename__ = "memory_feedback"
    __table_args__ = (Index("ix_memory_feedback_memory_id", "memory_id"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    memory_id: Mapped[str] = mapped_column(String)
    conversation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # useful|irrelevant|incorrect|outdated|too_sensitive|overused|underused|wrong_scope
    feedback_type: Mapped[str] = mapped_column(String)
    scope: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
