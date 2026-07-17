"""ECHO Layer 1 — Memory Consolidation Engine (Phase 5).

Deterministic duplicate/near-duplicate/correction detection over AtlasEntry,
reusing memory_conflicts.py's word-overlap primitives at a stricter threshold
(DUPLICATE_THRESHOLD > memory_conflicts.OVERLAP_THRESHOLD) — "plausibly the
same subject" (a conflict) is a much looser bar than "plausibly restating the
same specific memory" (a duplicate). No model call, no fabrication: every
action taken is logged as a MemoryConsolidationEvent, and nothing here ever
silently overwrites a memory without recording what it replaced.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app import atlas, schemas
from app.memory_conflicts import significant_words
from app.models import AtlasEntry, MemoryConsolidationEvent, MemoryRelationship, MemoryRevision

# Containment (not Jaccard) similarity threshold: "what fraction of the
# SMALLER memory's significant words also appear in the other one." Plain
# Jaccard overlap (memory_conflicts.word_overlap_ratio) gets diluted whenever
# a correction/refinement legitimately adds new words ("port 8001" ->
# "must run on port 8000; 8001 was temporary" shares few words relative to
# the UNION, but nearly all of the shorter memory's words appear in the
# longer one) — containment is the right measure for "is B a restatement,
# correction, or refinement of A," which is what consolidation cares about.
# Stricter than memory_conflicts.OVERLAP_THRESHOLD (0.4, "plausibly the same
# subject") — this is "plausibly restating the same specific memory."
DUPLICATE_THRESHOLD = 0.55


def _containment_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    return max(intersection / len(a), intersection / len(b))

_CORRECTION_PATTERNS_TEXT = (
    "no longer", "not anymore", "was temporary", "instead of", "actually,",
    "correction:", "correction ", "update:", "must be", "must run", "must use",
    "has changed to", "is now", "was wrong",
)


def _looks_like_correction(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in _CORRECTION_PATTERNS_TEXT)


def classify_action(existing_content: str, new_content: str) -> str:
    """Pure, side-effect-free classification — one of the ConsolidationAction
    values (see schemas.py). Never raises."""
    existing_norm = (existing_content or "").strip().lower()
    new_norm = (new_content or "").strip().lower()
    if existing_norm == new_norm:
        return "reject_duplicate"

    existing_words = significant_words(existing_content)
    new_words = significant_words(new_content)
    overlap = _containment_ratio(existing_words, new_words)
    if overlap < DUPLICATE_THRESHOLD:
        return "keep_both"

    if _looks_like_correction(new_content):
        return "supersede_existing"

    # "More specific": the new statement contains (most of) the old one's
    # significant words plus meaningfully more content — a refinement, not a
    # replacement, so update in place rather than supersede.
    if existing_words and existing_words.issubset(new_words) and len(new_content) > len(existing_content) * 1.15:
        return "update_existing"

    return "keep_both"


def find_duplicates(
    db: Session, *, content: str, memory_type: str, exclude_id: str | None = None
) -> list[tuple[AtlasEntry, float]]:
    """Existing active AtlasEntry rows that plausibly restate `content` —
    sorted by overlap, highest first. Only considers status="active" rows:
    an archived/superseded memory isn't a live duplicate candidate."""
    words = significant_words(content)
    content_norm = (content or "").strip().lower()
    query = db.query(AtlasEntry).filter(AtlasEntry.memory_type == memory_type, AtlasEntry.status == "active")
    if exclude_id:
        query = query.filter(AtlasEntry.id != exclude_id)

    results: list[tuple[AtlasEntry, float]] = []
    for entry in query.all():
        overlap = _containment_ratio(words, significant_words(entry.content))
        if overlap >= DUPLICATE_THRESHOLD or entry.content.strip().lower() == content_norm:
            results.append((entry, overlap))
    results.sort(key=lambda pair: pair[1], reverse=True)
    return results


def _record_revision(db: Session, entry: AtlasEntry, *, change_type: str, change_reason: str, new_content: str | None) -> None:
    revision_count = db.query(MemoryRevision).filter(MemoryRevision.memory_id == entry.id).count()
    db.add(
        MemoryRevision(
            memory_id=entry.id,
            revision_number=revision_count + 1,
            previous_content=entry.content,
            new_content=new_content,
            change_type=change_type,
            change_reason=change_reason,
            changed_by="system",
        )
    )


def _link(db: Session, *, source_id: str, target_id: str, relationship_type: str, confidence: str = "medium") -> None:
    existing = (
        db.query(MemoryRelationship)
        .filter(
            MemoryRelationship.source_memory_id == source_id,
            MemoryRelationship.target_memory_id == target_id,
            MemoryRelationship.relationship_type == relationship_type,
        )
        .first()
    )
    if existing is not None:
        return
    db.add(
        MemoryRelationship(
            source_memory_id=source_id,
            target_memory_id=target_id,
            relationship_type=relationship_type,
            confidence=confidence,
            source_type="memory_consolidation",
        )
    )


def apply_consolidation(
    db: Session,
    *,
    existing: AtlasEntry,
    new_content: str,
    new_confidence: float,
    new_tags: list[str],
    source: str | None,
    capture_method: str,
    epistemic_status: str,
    action: str,
    reason: str,
) -> MemoryConsolidationEvent:
    """Executes `action` (from classify_action) and records the audit event.
    Never called with action == "merge"/"ask_user"/"create_summary_memory" in
    this v1 — those are documented as not-yet-implemented (see
    ECHO_LAYER_1_MEMORY_FOUNDATION.md's known limitations); callers only ever
    pass what classify_action actually returns."""
    result_memory_id: str | None = existing.id
    reversible = True

    if action == "reject_duplicate":
        pass  # existing stands unchanged — nothing to do

    elif action == "update_existing":
        _record_revision(db, existing, change_type="edited", change_reason=reason, new_content=new_content)
        atlas.update_entry(
            db, existing,
            schemas.AtlasEntryUpdate(content=new_content, confidence=max(existing.confidence, new_confidence)),
        )
        existing.last_verified_at = datetime.now(UTC)
        db.commit()

    elif action == "supersede_existing":
        new_entry = atlas.create_entry(
            db,
            schemas.AtlasEntryCreate(
                content=new_content, epistemic_status=epistemic_status, memory_type=existing.memory_type,
                tags=new_tags, confidence=new_confidence, source=source, capture_method=capture_method,
            ),
        )
        new_entry.supersedes_memory_id = existing.id
        existing.status = "superseded"
        existing.outdated = True
        db.commit()
        _link(db, source_id=new_entry.id, target_id=existing.id, relationship_type="supersedes", confidence="high")
        result_memory_id = new_entry.id

    else:  # "keep_both" (and any future action not yet special-cased, fails safe to keep_both's behavior)
        new_entry = atlas.create_entry(
            db,
            schemas.AtlasEntryCreate(
                content=new_content, epistemic_status=epistemic_status, memory_type=existing.memory_type,
                tags=new_tags, confidence=new_confidence, source=source, capture_method=capture_method,
            ),
        )
        _link(db, source_id=new_entry.id, target_id=existing.id, relationship_type="related_to", confidence="medium")
        result_memory_id = new_entry.id
        reversible = True

    event = MemoryConsolidationEvent(
        source_memory_ids_json=[existing.id],
        result_memory_id=result_memory_id,
        action=action,
        reason=reason,
        confidence=0.7,
        reversible=reversible,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _reason_for(action: str, overlap: float) -> str:
    return {
        "reject_duplicate": "Identical to an existing memory (after normalization).",
        "update_existing": f"More specific restatement of an existing memory (word overlap {overlap:.2f}).",
        "supersede_existing": f"Reads as a correction of an existing memory (word overlap {overlap:.2f}).",
        "keep_both": f"Related to an existing memory but distinct enough to keep separately (word overlap {overlap:.2f}).",
    }.get(action, f"Consolidation action {action} (word overlap {overlap:.2f}).")


def consolidate_new_memory(
    db: Session,
    *,
    content: str,
    memory_type: str,
    tags: list[str],
    confidence: float,
    source: str | None,
    capture_method: str = "system_generated",
    epistemic_status: str = "Inferred",
) -> MemoryConsolidationEvent | None:
    """The main entry point: checks `content` against existing active memories
    of the same memory_type, and if a duplicate/near-duplicate/correction is
    found, applies the appropriate consolidation action and returns the
    event. Returns None when nothing duplicate-like was found — the caller
    should then proceed with a plain atlas.create_entry() (or, for the
    candidate pipeline, queue a normal MemoryCandidate)."""
    duplicates = find_duplicates(db, content=content, memory_type=memory_type)
    if not duplicates:
        return None
    existing, overlap = duplicates[0]
    action = classify_action(existing.content, content)
    if action == "keep_both":
        # Below the bar for even recording a "related" link — this happens
        # when overlap is right at the threshold edge with no other signal.
        return None
    return apply_consolidation(
        db, existing=existing, new_content=content, new_confidence=confidence, new_tags=tags,
        source=source, capture_method=capture_method, epistemic_status=epistemic_status,
        action=action, reason=_reason_for(action, overlap),
    )
