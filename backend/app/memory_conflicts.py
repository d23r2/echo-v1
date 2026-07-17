"""Free, local, deterministic conflict detection for memory candidates — not
semantic search (that's Atlas's separate ChromaDB-backed search in atlas.py), just
plain word-overlap and tag-overlap heuristics. No model calls, nothing paid.

A "conflict" here just means "plausibly about the same thing" — good enough to
surface to a human for review, not a claim of actual contradiction.

ECHO Layer 1 (Phase 6) extends this with a richer, classified/severity-scored
MemoryConflict record — find_conflicts()/find_all_conflicts() above stay
exactly as they were (still used at candidate-creation time for the quick
"here's a possible conflict" flag); detect_and_record_conflicts() below is
the new, heavier pass that turns a plausible overlap into a typed, reviewable
conflict record.
"""

import re
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import models

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "and", "to", "of",
    "in", "on", "for", "with", "that", "this", "it", "as", "at", "by", "or", "but",
    "user", "user's", "echo", "their", "they", "them", "has", "have", "had",
}


def significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def word_overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Above this word-overlap ratio, two entries are treated as "plausibly about the
# same subject" even with zero shared tags.
_OVERLAP_THRESHOLD = 0.4


def find_conflicts(
    db: Session, *, content: str, memory_type: str, tags: list[str], include_outdated: bool = False
) -> list[models.AtlasEntry]:
    """Existing AtlasEntry rows that plausibly overlap with a new memory
    candidate: same memory_type, and either a shared tag or significant word
    overlap in content — but not near-identical content (that's a duplicate, not
    a conflict, and isn't flagged here). Outdated entries are excluded by
    default — a candidate isn't "conflicting" with a memory that's already
    been marked as no longer current; pass include_outdated=True to check
    against those too."""
    candidate_words = significant_words(content)
    candidate_tags = {t.lower() for t in tags}
    candidate_content_norm = content.strip().lower()

    conflicts = []
    query = db.query(models.AtlasEntry).filter(models.AtlasEntry.memory_type == memory_type)
    if not include_outdated:
        query = query.filter(models.AtlasEntry.outdated.is_(False))
    existing = query.all()
    for entry in existing:
        if entry.content.strip().lower() == candidate_content_norm:
            continue

        entry_tags = {t.lower() for t in entry.tags}
        shares_tags = bool(candidate_tags & entry_tags)

        entry_words = significant_words(entry.content)
        overlap = word_overlap_ratio(candidate_words, entry_words)

        if shares_tags or overlap >= _OVERLAP_THRESHOLD:
            conflicts.append(entry)

    return conflicts


def find_all_conflicts(db: Session, include_outdated: bool = False) -> dict[str, list[str]]:
    """Same heuristic as find_conflicts(), applied pairwise across all existing
    Atlas entries (grouped by memory_type) instead of one new candidate against
    the rest. Returns entry id -> list of conflicting entry ids, both directions.
    Outdated entries are excluded by default, same rationale as find_conflicts()."""
    query = db.query(models.AtlasEntry)
    if not include_outdated:
        query = query.filter(models.AtlasEntry.outdated.is_(False))
    entries = query.all()
    by_type: dict[str, list[models.AtlasEntry]] = {}
    for entry in entries:
        by_type.setdefault(entry.memory_type, []).append(entry)

    conflicts: dict[str, list[str]] = {}
    for group in by_type.values():
        for i, a in enumerate(group):
            a_words = significant_words(a.content)
            a_tags = {t.lower() for t in a.tags}
            a_content_norm = a.content.strip().lower()
            for b in group[i + 1 :]:
                if a_content_norm == b.content.strip().lower():
                    continue
                b_tags = {t.lower() for t in b.tags}
                overlap = word_overlap_ratio(a_words, significant_words(b.content))
                if bool(a_tags & b_tags) or overlap >= _OVERLAP_THRESHOLD:
                    conflicts.setdefault(a.id, []).append(b.id)
                    conflicts.setdefault(b.id, []).append(a.id)

    return conflicts


# ============================================================================
# ECHO Layer 1 (Phase 6) — typed, severity-scored conflicts. Deterministic,
# no model call — same style as the rest of this module.
# ============================================================================

_NEGATION_CUES = (
    "no longer", "not anymore", "isn't", "is not", "moved to", "instead of",
    "used to", "changed to", "was wrong", "actually", "correction",
)


def _has_negation_cue(a_content: str, b_content: str) -> bool:
    combined = f"{a_content} {b_content}".lower()
    return any(cue in combined for cue in _NEGATION_CUES)


def classify_conflict_type(a: models.AtlasEntry, b: models.AtlasEntry) -> str:
    """Pure classification, no side effects. Falls back to
    'direct_contradiction' when nothing more specific is detected — a
    reasonable default given the pair was already flagged as plausibly
    conflicting by find_conflicts()."""
    category = getattr(a, "category", None) or getattr(b, "category", None)
    if category == "environment":
        return "environment_drift"
    if category == "project":
        return "project_version_conflict"
    if category == "preference":
        if _has_negation_cue(a.content, b.content):
            return "user_preference_change"
        return "scope_conflict"
    if _has_negation_cue(a.content, b.content):
        gap = abs((a.created_at - b.created_at).total_seconds())
        return "temporal_update" if gap > 3600 else "direct_contradiction"
    if abs(a.confidence - b.confidence) >= 0.3:
        return "confidence_conflict"
    return "direct_contradiction"


def classify_severity(a: models.AtlasEntry, b: models.AtlasEntry) -> str:
    """Never returns 'critical' automatically — that tier is reserved for a
    human/Guardian-Council-style judgment call this deterministic classifier
    isn't positioned to make."""
    if a.confidence >= 0.7 and b.confidence >= 0.7:
        return "high"
    if a.confidence < 0.4 or b.confidence < 0.4:
        return "low"
    return "medium"


def recommend_resolution(conflict_type: str, a: models.AtlasEntry, b: models.AtlasEntry) -> str:
    """A suggestion only — never applied automatically for high-impact
    conflicts (see resolve_conflict()'s own caller in routers/memory.py,
    which always requires an explicit resolution action)."""
    if conflict_type in ("temporal_update", "user_preference_change"):
        newer = a if a.created_at >= b.created_at else b
        return "choose_newer" if newer.confidence >= 0.6 else "user_decision"
    if conflict_type == "scope_conflict":
        return "retain_both_with_scope"
    if conflict_type == "confidence_conflict":
        higher = a if a.confidence >= b.confidence else b
        return "choose_verified" if higher.epistemic_status == "Verified" else "user_decision"
    return "user_decision"


def detect_and_record_conflicts(db: Session, entry: models.AtlasEntry) -> list[models.MemoryConflict]:
    """Runs find_conflicts() against `entry`, classifies each plausible
    conflict, and records a MemoryConflict row for any pair that doesn't
    already have one open. Returns the newly created rows only (does not
    re-return already-open conflicts for the same pair)."""
    candidates = find_conflicts(db, content=entry.content, memory_type=entry.memory_type, tags=entry.tags)
    created: list[models.MemoryConflict] = []
    for other in candidates:
        if other.id == entry.id:
            continue
        pair = sorted([entry.id, other.id])
        existing_open = (
            db.query(models.MemoryConflict)
            .filter(models.MemoryConflict.status.in_(["open", "user_review_required"]))
            .all()
        )
        already_recorded = any(
            len(row.memory_ids_json) >= 2 and sorted(row.memory_ids_json[:2]) == pair for row in existing_open
        )
        if already_recorded:
            continue

        conflict_type = classify_conflict_type(entry, other)
        severity = classify_severity(entry, other)
        recommendation = recommend_resolution(conflict_type, entry, other)
        row = models.MemoryConflict(
            memory_ids_json=pair,
            conflict_type=conflict_type,
            description=f"Plausible {conflict_type.replace('_', ' ')} between two {entry.memory_type} memories.",
            severity=severity,
            status="user_review_required" if severity in ("high", "critical") else "open",
            recommended_resolution=recommendation,
        )
        db.add(row)
        created.append(row)
    if created:
        db.commit()
        for row in created:
            db.refresh(row)
    return created


def resolve_conflict(
    db: Session, conflict: models.MemoryConflict, *, resolution: str, resolved_by: str = "user"
) -> models.MemoryConflict:
    """Applies a resolution the caller has explicitly chosen (never inferred
    automatically here — recommend_resolution() only ever suggests). Actually
    mutates the underlying memories for the resolutions that call for it;
    'retain_both_with_scope' and 'user_decision'/'unresolved' just record the
    decision without changing any AtlasEntry."""
    ids = conflict.memory_ids_json or []
    entries = db.query(models.AtlasEntry).filter(models.AtlasEntry.id.in_(ids)).all() if ids else []

    if resolution in ("choose_newer", "choose_verified") and len(entries) == 2:
        a, b = entries
        if resolution == "choose_newer":
            keep, drop = (a, b) if a.created_at >= b.created_at else (b, a)
        else:
            keep, drop = (a, b) if a.epistemic_status == "Verified" else (b, a)
        drop.status = "superseded"
        drop.outdated = True
        drop.supersedes_memory_id = None
        keep.supersedes_memory_id = drop.id
    elif resolution == "mark_outdated" and entries:
        for e in entries:
            if e.confidence == min(x.confidence for x in entries):
                e.status = "superseded"
                e.outdated = True

    conflict.resolution = resolution
    conflict.resolved_by = resolved_by
    conflict.resolved_at = datetime.now(UTC)
    conflict.status = "resolved"
    db.commit()
    db.refresh(conflict)
    return conflict
