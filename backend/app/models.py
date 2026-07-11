import uuid
from datetime import datetime, timezone

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    message: Mapped["Message"] = relationship(back_populates="attachments")


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
