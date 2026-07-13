"""Free, local, deterministic conflict detection for memory candidates — not
semantic search (that's Atlas's separate ChromaDB-backed search in atlas.py), just
plain word-overlap and tag-overlap heuristics. No model calls, nothing paid.

A "conflict" here just means "plausibly about the same thing" — good enough to
surface to a human for review, not a claim of actual contradiction.
"""

import re

from sqlalchemy.orm import Session

from app import models

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "and", "to", "of",
    "in", "on", "for", "with", "that", "this", "it", "as", "at", "by", "or", "but",
    "user", "user's", "echo", "their", "they", "them", "has", "have", "had",
}


def _significant_words(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _word_overlap_ratio(a: set[str], b: set[str]) -> float:
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
    candidate_words = _significant_words(content)
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

        entry_words = _significant_words(entry.content)
        overlap = _word_overlap_ratio(candidate_words, entry_words)

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
            a_words = _significant_words(a.content)
            a_tags = {t.lower() for t in a.tags}
            a_content_norm = a.content.strip().lower()
            for b in group[i + 1 :]:
                if a_content_norm == b.content.strip().lower():
                    continue
                b_tags = {t.lower() for t in b.tags}
                overlap = _word_overlap_ratio(a_words, _significant_words(b.content))
                if bool(a_tags & b_tags) or overlap >= _OVERLAP_THRESHOLD:
                    conflicts.setdefault(a.id, []).append(b.id)
                    conflicts.setdefault(b.id, []).append(a.id)

    return conflicts
