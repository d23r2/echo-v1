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
    plain strings, never raw chain-of-thought."""

    __tablename__ = "task_understandings"
    __table_args__ = (Index("ix_task_understandings_conversation_id", "conversation_id"),)

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
