"""ECHO Layer 1 — Memory Export, Import, and Portability (Phase 19).

Export excludes embeddings, internal prompts, secrets, and highly sensitive
content by default (memory_privacy.can_export). Import never writes directly
to active memory — every imported record is staged as a MemoryCandidate for
normal human review (the same queue explicit/opportunistic capture already
uses), so "never overwrite active memories silently" holds by construction.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models import AtlasEntry, MemoryCandidate, MemoryRelationship
from app.services import memory_privacy

EXPORT_SCHEMA_VERSION = 1


def export_memories(db: Session, *, include_archived: bool = False) -> dict:
    query = db.query(AtlasEntry)
    if not include_archived:
        query = query.filter(AtlasEntry.status == "active")
    rows = query.all()

    memories = []
    excluded_sensitive = 0
    for entry in rows:
        sensitivity = memory_privacy.classify_sensitivity(entry.content)
        if not memory_privacy.can_export(sensitivity):
            excluded_sensitive += 1
            continue
        memories.append(
            {
                "id": entry.id,
                "content": entry.content,
                "memory_type": entry.memory_type,
                "category": entry.category,
                "epistemic_status": entry.epistemic_status,
                "verification_status": entry.verification_status,
                "confidence": entry.confidence,
                "importance": entry.importance,
                "stability": entry.stability,
                "tags": entry.tags,
                "source": entry.source,
                "source_type": entry.source_type,
                "capture_method": entry.capture_method,
                "project_id": entry.project_id,
                "status": entry.status,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            }
        )

    exported_ids = {m["id"] for m in memories}
    relationships = [
        {
            "source_memory_id": rel.source_memory_id,
            "target_memory_id": rel.target_memory_id,
            "relationship_type": rel.relationship_type,
            "confidence": rel.confidence,
        }
        for rel in db.query(MemoryRelationship).filter(MemoryRelationship.status == "active").all()
        if rel.source_memory_id in exported_ids and rel.target_memory_id in exported_ids
    ]

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
        "memory_count": len(memories),
        "excluded_sensitive_count": excluded_sensitive,
        "memories": memories,
        "relationships": relationships,
    }


def _validate_payload(payload: dict) -> str | None:
    if not isinstance(payload, dict):
        return "Import payload must be a JSON object."
    if payload.get("schema_version") != EXPORT_SCHEMA_VERSION:
        return f"Unsupported schema_version (expected {EXPORT_SCHEMA_VERSION}, got {payload.get('schema_version')!r})."
    if not isinstance(payload.get("memories"), list):
        return "Import payload is missing a 'memories' list."
    return None


def preview_import(db: Session, payload: dict) -> dict:
    """Dry run — never writes anything. Reports what commit_import() would
    do: how many records are new, how many look like duplicates of an
    existing active memory, and how many would be rejected as secrets."""
    error = _validate_payload(payload)
    if error:
        return {"valid": False, "error": error, "total": 0, "new": 0, "duplicates": [], "secrets_rejected": 0}

    from app.services import memory_consolidation

    new_count = 0
    duplicate_ids: list[str] = []
    secrets_rejected = 0

    for record in payload["memories"]:
        content = str(record.get("content") or "")
        if not content.strip():
            continue
        if memory_privacy.classify_sensitivity(content) == "secret":
            secrets_rejected += 1
            continue
        duplicates = memory_consolidation.find_duplicates(
            db, content=content, memory_type=record.get("memory_type", "fact")
        )
        if duplicates:
            duplicate_ids.append(record.get("id", content[:40]))
        else:
            new_count += 1

    return {
        "valid": True,
        "error": None,
        "total": len(payload["memories"]),
        "new": new_count,
        "duplicates": duplicate_ids,
        "secrets_rejected": secrets_rejected,
    }


def commit_import(db: Session, payload: dict, *, skip_duplicates: bool = True) -> dict:
    """Stages every acceptable record as a pending MemoryCandidate — never
    creates an AtlasEntry directly, so an import can never silently overwrite
    or bypass review of an active memory."""
    error = _validate_payload(payload)
    if error:
        return {"valid": False, "error": error, "staged": 0, "skipped_duplicates": 0, "skipped_secrets": 0}

    from app.services import memory_consolidation

    staged = 0
    skipped_duplicates = 0
    skipped_secrets = 0

    for record in payload["memories"]:
        content = str(record.get("content") or "").strip()
        if not content:
            continue
        sensitivity = memory_privacy.classify_sensitivity(content)
        if sensitivity == "secret":
            skipped_secrets += 1
            continue

        memory_type = record.get("memory_type", "fact")
        if skip_duplicates and memory_consolidation.find_duplicates(db, content=content, memory_type=memory_type):
            skipped_duplicates += 1
            continue

        db.add(
            MemoryCandidate(
                content=content,
                epistemic_status=record.get("epistemic_status", "Hypothesis"),
                memory_type=memory_type,
                tags=record.get("tags") or [],
                confidence=float(record.get("confidence", 0.5)),
                source=record.get("source") or "imported",
                category=record.get("category"),
                sensitivity_level=sensitivity,
                recommendation="ask_user",
                capture_reason="Staged from an imported memory export — review before accepting.",
            )
        )
        staged += 1

    db.commit()
    return {
        "valid": True,
        "error": None,
        "staged": staged,
        "skipped_duplicates": skipped_duplicates,
        "skipped_secrets": skipped_secrets,
    }
