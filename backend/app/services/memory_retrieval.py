"""ECHO Layer 1 — Hybrid Memory Retrieval (Phase 8).

Combines Atlas's existing semantic search (local sentence-transformers +
Chroma — already satisfies "prefer local embeddings," see Phase 9) with
metadata filtering, recency/importance/confidence scoring, a sensitivity
gate (memory_privacy.py), and a conflict-penalty lookup — then degrades
cleanly to a pure lexical/metadata pass if Chroma is unavailable, per rule
15 ("existing chat behaviour must remain functional if Atlas or vector
search is unavailable").

This is deliberately a thin scoring layer over atlas.py, not a second
retrieval engine — atlas.search()/list_entries() do all the actual
SQL/Chroma work.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import atlas
from app.core import metrics
from app.models import AtlasEntry, MemoryConflict, MemoryFeedback
from app.services import memory_privacy

logger = logging.getLogger(__name__)


@dataclass
class MemoryRetrievalRequest:
    query: str
    conversation_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    allowed_categories: list[str] | None = None
    excluded_categories: list[str] | None = None
    max_results: int = 5
    include_archived: bool = False
    minimum_confidence: float = 0.0
    purpose: str = "general"  # passed through to memory_privacy.can_retrieve


@dataclass
class MemoryRetrievalResult:
    memory_id: str
    content: str
    category: str
    relevance_score: float
    confidence: float
    verification_status: str
    provenance_summary: str
    freshness_status: str  # "fresh" | "stale" | "needs_review" | "unknown"
    conflict_warning: str | None
    retrieval_reason: str
    epistemic_status: str = ""
    tags: list[str] = field(default_factory=list)


_PROVENANCE_LABELS = {
    "explicit_user_request": "You told ECHO",
    "approved_candidate": "You confirmed this",
    "manual_entry": "Manually added",
    "project_import": "From project",
    "document_extraction": "From an uploaded document",
    "conversation_summary": "From a conversation summary",
    "system_generated": "Inferred by ECHO",
    "migration": "Imported from an earlier Atlas memory",
}


def _provenance_summary(entry: AtlasEntry) -> str:
    return _PROVENANCE_LABELS.get(entry.capture_method, "Unknown source")


def _freshness_status(entry: AtlasEntry) -> str:
    if entry.review_state == "pending_review":
        return "needs_review"
    if entry.outdated:
        return "stale"
    if entry.verification_status in ("verified", "partially_verified"):
        return "fresh"
    return "unknown"


def _open_conflict_ids(db: Session) -> set[str]:
    rows = db.query(MemoryConflict).filter(MemoryConflict.status.in_(["open", "user_review_required"])).all()
    ids: set[str] = set()
    for row in rows:
        ids.update(row.memory_ids_json or [])
    return ids


def _passes_filters(entry: AtlasEntry, request: MemoryRetrievalRequest) -> bool:
    if not request.include_archived and entry.status != "active":
        return False
    if entry.confidence < request.minimum_confidence:
        return False
    if request.allowed_categories and entry.category not in request.allowed_categories:
        return False
    if request.excluded_categories and entry.category in request.excluded_categories:
        return False
    if request.project_id and entry.project_id and entry.project_id != request.project_id:
        return False
    sensitivity = memory_privacy.classify_sensitivity(entry.content)
    if not memory_privacy.can_retrieve(sensitivity, purpose=request.purpose):
        return False
    return True


# ECHO Layer 1 (Phase 21) — adaptive feedback nudges ranking gently and is
# capped so a handful of ratings can never dominate scoring or "erase truth"
# from a single negative rating (explicit rule). This never changes a
# memory's content, confidence, or epistemic_status — only where it ranks.
_POSITIVE_FEEDBACK_TYPES = {"useful"}
_NEGATIVE_FEEDBACK_TYPES = {"irrelevant", "incorrect", "overused", "too_sensitive", "wrong_scope"}
_MAX_FEEDBACK_SAMPLES_PER_MEMORY = 3


def record_feedback(
    db: Session, *, memory_id: str, feedback_type: str,
    conversation_id: str | None = None, scope: str | None = None, reason: str | None = None,
) -> MemoryFeedback:
    row = MemoryFeedback(
        memory_id=memory_id, feedback_type=feedback_type,
        conversation_id=conversation_id, scope=scope, reason=reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _feedback_bias(db: Session) -> dict[str, float]:
    counts: dict[str, dict[str, int]] = {}
    for row in db.query(MemoryFeedback).all():
        bucket = counts.setdefault(row.memory_id, {"positive": 0, "negative": 0})
        if row.feedback_type in _POSITIVE_FEEDBACK_TYPES:
            bucket["positive"] += 1
        elif row.feedback_type in _NEGATIVE_FEEDBACK_TYPES:
            bucket["negative"] += 1
    return {
        memory_id: min(c["positive"], _MAX_FEEDBACK_SAMPLES_PER_MEMORY) * 0.02
        - min(c["negative"], _MAX_FEEDBACK_SAMPLES_PER_MEMORY) * 0.03
        for memory_id, c in counts.items()
    }


def _score(
    entry: AtlasEntry, request: MemoryRetrievalRequest, *,
    distance: float | None, conflict_ids: set[str], feedback_bias: float = 0.0,
) -> float:
    score = 0.0
    if distance is not None:
        # Chroma cosine/L2 distance — lower is more similar. Clamp defensively;
        # exact semantics vary by embedding backend and aren't guaranteed to
        # stay in [0, 2], so this must never produce a negative score.
        score += max(0.0, 1.0 - min(distance, 1.0)) * 0.5
    else:
        score += 0.15  # lexical fallback gets a flat, modest base score

    score += {"critical": 0.25, "high": 0.18, "medium": 0.1, "low": 0.03}.get(entry.importance, 0.1)
    score += entry.confidence * 0.15
    if entry.verification_status == "verified":
        score += 0.1
    elif entry.verification_status == "disputed":
        score -= 0.15
    if request.project_id and entry.project_id == request.project_id:
        score += 0.15
    if entry.id in conflict_ids:
        score -= 0.2  # contradiction penalty — still returned, never silently hidden
    if entry.outdated:
        score -= 0.2
    score += feedback_bias
    return max(0.0, score)


def _to_result(entry: AtlasEntry, score: float, *, reason: str, conflict_ids: set[str]) -> MemoryRetrievalResult:
    return MemoryRetrievalResult(
        memory_id=entry.id,
        content=entry.content,
        category=entry.category,
        relevance_score=round(score, 4),
        confidence=entry.confidence,
        verification_status=entry.verification_status,
        provenance_summary=_provenance_summary(entry),
        freshness_status=_freshness_status(entry),
        conflict_warning="This memory has an unresolved conflict with another memory." if entry.id in conflict_ids else None,
        retrieval_reason=reason,
        epistemic_status=entry.epistemic_status,
        tags=list(entry.tags or []),
    )


def _touch_access(db: Session, entries: list[AtlasEntry]) -> None:
    """Best-effort — a failure here must never break retrieval itself."""
    try:
        for entry in entries:
            entry.last_accessed_at = datetime.now(UTC)
            entry.access_count = (entry.access_count or 0) + 1
        db.commit()
    except Exception:
        db.rollback()


def retrieve(db: Session, request: MemoryRetrievalRequest) -> list[MemoryRetrievalResult]:
    conflict_ids = _open_conflict_ids(db)
    feedback_bias = _feedback_bias(db)
    scored: list[tuple[AtlasEntry, float, str]] = []

    try:
        semantic_hits = atlas.search(db, request.query, top_k=max(request.max_results * 3, 10))
        semantic_ok = True
        metrics.increment("memory_retrieval_total", mode="semantic")
    except Exception:
        logger.warning("Semantic memory retrieval unavailable, falling back to lexical/metadata search", exc_info=True)
        semantic_hits = []
        semantic_ok = False
        metrics.increment("memory_retrieval_total", mode="fallback")

    seen_ids: set[str] = set()
    for entry, distance in semantic_hits:
        if not _passes_filters(entry, request):
            continue
        score = _score(entry, request, distance=distance, conflict_ids=conflict_ids, feedback_bias=feedback_bias.get(entry.id, 0.0))
        scored.append((entry, score, "semantic match"))
        seen_ids.add(entry.id)

    # Lexical/metadata fallback — always runs (not just when Chroma is down)
    # for project/task-scoped requests, since a project-scoped memory that
    # didn't rank in the top semantic hits should still surface if it's an
    # exact scope match. Rule 10: "Hybrid retrieval should function without
    # embeddings using metadata / lexical search / project scope / recent
    # active memories."
    if not semantic_ok or request.project_id or request.task_id:
        query_words = {w.lower() for w in request.query.split() if len(w) > 2}
        candidates = db.query(AtlasEntry).filter(AtlasEntry.status == "active")
        if request.project_id:
            candidates = candidates.filter(AtlasEntry.project_id == request.project_id)
        if request.task_id:
            candidates = candidates.filter(AtlasEntry.task_id == request.task_id)
        for entry in candidates.order_by(AtlasEntry.created_at.desc()).limit(50).all():
            if entry.id in seen_ids or not _passes_filters(entry, request):
                continue
            content_words = {w.lower() for w in entry.content.split()}
            lexical_match = bool(query_words & content_words) or bool(request.project_id and entry.project_id == request.project_id)
            if not lexical_match:
                continue
            score = _score(entry, request, distance=None, conflict_ids=conflict_ids, feedback_bias=feedback_bias.get(entry.id, 0.0))
            scored.append((entry, score, "lexical/metadata match" if not semantic_ok else "project-scoped match"))
            seen_ids.add(entry.id)

    scored.sort(key=lambda triple: triple[1], reverse=True)
    top = scored[: request.max_results]

    _touch_access(db, [entry for entry, _score, _reason in top])
    return [_to_result(entry, score, reason=reason, conflict_ids=conflict_ids) for entry, score, reason in top]


def build_memory_brief(db: Session, message: str, *, top_k: int = 5) -> tuple[str, list[MemoryRetrievalResult]]:
    """ECHO Layer 1 (Phase 10) — the compact, prompt-ready text block plus
    the underlying results (for the caller to build AtlasCitation/response
    metadata from). Never raises: a retrieval failure degrades to an honest
    "no memories available" block rather than blocking the chat turn (rule
    15). Never includes a raw memory ID, an internal score, or hidden
    reasoning in the text block itself — only content, epistemic status,
    confidence, and a short freshness/conflict note when relevant."""
    try:
        results = retrieve(db, MemoryRetrievalRequest(query=message, max_results=top_k))
    except Exception:
        logger.warning("MemoryBrief retrieval failed; continuing without memory context", exc_info=True)
        return "No relevant memories are available right now.", []

    if not results:
        return "No relevant memories found for this message.", []

    lines = []
    for r in results:
        notes = [f"[{r.epistemic_status}, confidence {r.confidence:.2f}]"]
        if r.freshness_status == "needs_review":
            notes.append("(due for re-verification)")
        if r.conflict_warning:
            notes.append("(has an unresolved conflicting memory — do not present this as the single settled fact)")
        lines.append(f"- {' '.join(notes)} {r.content}")

    block = (
        "Relevant memories (cite epistemic status/confidence if you use these; "
        "treat any marked as needing re-verification or conflicting with appropriate caution):\n"
        + "\n".join(lines)
    )
    return block, results
