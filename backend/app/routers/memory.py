"""ECHO Layer 1 — consolidated /api/memory/* surface (Phase 18).

Additive alongside the pre-existing /api/atlas/* (still used unchanged by
AtlasView.tsx) and /api/memory-candidates/* (still used unchanged by
MemoryCandidates.tsx) — this router doesn't replace either. Candidate
accept/reject/edit stays exactly where it already is
(/api/memory-candidates/*) rather than being duplicated here; this router
covers the new Layer 1 capabilities that didn't have a home yet: typed
hybrid search, conflict review, lifecycle actions, index status/rebuild,
maintenance, and stats.

Route ordering matters: literal-path routes (/conflicts, /search, /stats,
...) are registered before the /{memory_id} catch-all, since FastAPI/
Starlette matches in registration order and a dynamic path segment would
otherwise swallow "conflicts"/"search"/etc. as if they were a memory id.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import atlas as atlas_store
from app import memory_conflicts, schemas
from app.core import metrics as core_metrics
from app.db import get_db
from app.models import AtlasEntry, MemoryCandidate, MemoryConflict, MemoryConsolidationEvent
from app.services import memory_export, memory_index, memory_lifecycle, memory_retrieval

router = APIRouter(prefix="/api/memory", tags=["memory"])


# ---- List (before the dynamic /{memory_id} route) ----


@router.get("", response_model=list[schemas.AtlasEntryOut])
def list_memories(
    category: str | None = Query(None),
    status: str | None = Query(None),
    project_id: str | None = Query(None),
    needs_review: bool = Query(False),
    limit: int = Query(200, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AtlasEntry)
    if category:
        query = query.filter(AtlasEntry.category == category)
    if status:
        query = query.filter(AtlasEntry.status == status)
    if project_id:
        query = query.filter(AtlasEntry.project_id == project_id)
    if needs_review:
        query = query.filter(AtlasEntry.review_state == "pending_review")
    return query.order_by(AtlasEntry.created_at.desc()).limit(limit).all()


# ---- Search ----


@router.post("/search", response_model=list[schemas.MemorySearchResultOut])
def search_memories(payload: schemas.MemorySearchRequest, db: Session = Depends(get_db)):
    request = memory_retrieval.MemoryRetrievalRequest(
        query=payload.query,
        project_id=payload.project_id,
        task_id=payload.task_id,
        allowed_categories=payload.allowed_categories,
        excluded_categories=payload.excluded_categories,
        max_results=payload.max_results,
        include_archived=payload.include_archived,
        minimum_confidence=payload.minimum_confidence,
        purpose=payload.purpose,
    )
    results = memory_retrieval.retrieve(db, request)
    return [schemas.MemorySearchResultOut(**vars(r)) for r in results]


@router.post("/context-preview")
def context_preview(payload: schemas.MemorySearchRequest, db: Session = Depends(get_db)):
    """What the MemoryBrief prompt section would actually contain for this
    message — for developer diagnostics / Memory Center's "why did ECHO say
    that" view, never for normal chat."""
    block, results = memory_retrieval.build_memory_brief(db, payload.query, top_k=payload.max_results)
    return {
        "brief_text": block,
        "results": [schemas.MemorySearchResultOut(**vars(r)) for r in results],
    }


# ---- Conflicts ----


@router.get("/conflicts", response_model=list[schemas.MemoryConflictOut])
def list_conflicts(status: str | None = Query(None), db: Session = Depends(get_db)):
    query = db.query(MemoryConflict)
    if status:
        query = query.filter(MemoryConflict.status == status)
    else:
        query = query.filter(MemoryConflict.status.in_(["open", "user_review_required"]))
    return query.order_by(MemoryConflict.created_at.desc()).all()


@router.post("/conflicts/{conflict_id}/resolve", response_model=schemas.MemoryConflictOut)
def resolve_conflict(conflict_id: str, payload: schemas.ConflictResolveRequest, db: Session = Depends(get_db)):
    conflict = db.get(MemoryConflict, conflict_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return memory_conflicts.resolve_conflict(db, conflict, resolution=payload.resolution)


# ---- Maintenance / index ----


@router.post("/maintenance/run", response_model=schemas.MemoryMaintenanceResultOut)
def run_maintenance(db: Session = Depends(get_db)):
    return memory_lifecycle.run_maintenance(db)


@router.get("/index/status", response_model=schemas.MemoryIndexStatusOut)
def index_status(db: Session = Depends(get_db)):
    return memory_index.status(db)


@router.post("/index/rebuild")
def index_rebuild(db: Session = Depends(get_db)):
    return memory_index.rebuild_index(db)


@router.post("/index/repair")
def index_repair(db: Session = Depends(get_db)):
    return memory_index.repair_index(db)


# ---- Export / import ----


@router.get("/export")
def export_memories(include_archived: bool = Query(False), db: Session = Depends(get_db)):
    return memory_export.export_memories(db, include_archived=include_archived)


@router.post("/import/preview")
def import_preview(payload: dict, db: Session = Depends(get_db)):
    return memory_export.preview_import(db, payload)


@router.post("/import/commit")
def import_commit(payload: dict, skip_duplicates: bool = Query(True), db: Session = Depends(get_db)):
    return memory_export.commit_import(db, payload, skip_duplicates=skip_duplicates)


# ---- Metrics ----


@router.get("/metrics", response_model=schemas.MemoryMetricsOut)
def memory_metrics(db: Session = Depends(get_db)):
    """Phase 20 — quality indicators computed live from the DB (never
    persisted separately, never includes raw memory content) plus the
    in-process retrieval counters from core.metrics (Layer 0)."""
    active_rows = db.query(AtlasEntry).filter(AtlasEntry.status == "active").all()
    total = len(active_rows)

    def pct(count: int) -> float:
        return round(100.0 * count / total, 1) if total else 0.0

    provenance_covered = sum(1 for r in active_rows if r.source_type is not None)
    verified = sum(1 for r in active_rows if r.verification_status in ("verified", "partially_verified"))
    stale = sum(1 for r in active_rows if r.review_state == "pending_review" or r.outdated)

    open_conflicts = db.query(MemoryConflict).filter(MemoryConflict.status.in_(["open", "user_review_required"])).count()
    resolved_conflicts = db.query(MemoryConflict).filter(MemoryConflict.status == "resolved").count()
    total_conflicts = open_conflicts + resolved_conflicts
    unresolved_pct = round(100.0 * open_conflicts / total_conflicts, 1) if total_conflicts else 0.0

    snapshot = core_metrics.snapshot()
    retrieval_counters = {k: v for k, v in snapshot["counters"].items() if k.startswith("memory_retrieval_total")}

    return schemas.MemoryMetricsOut(
        retrieval_counters=retrieval_counters,
        provenance_coverage_pct=pct(provenance_covered),
        verification_coverage_pct=pct(verified),
        stale_memory_pct=pct(stale),
        unresolved_conflict_pct=unresolved_pct,
        duplicate_consolidation_events=db.query(MemoryConsolidationEvent).count(),
        total_active=total,
    )


# ---- Feedback ----


@router.post("/{memory_id}/feedback", response_model=schemas.MemoryFeedbackOut)
def submit_feedback(memory_id: str, payload: schemas.MemoryFeedbackRequest, db: Session = Depends(get_db)):
    _get_entry_or_404(db, memory_id)
    return memory_retrieval.record_feedback(
        db, memory_id=memory_id, feedback_type=payload.feedback_type,
        conversation_id=payload.conversation_id, scope=payload.scope, reason=payload.reason,
    )


# ---- Stats ----


@router.get("/stats", response_model=schemas.MemoryStatsOut)
def memory_stats(db: Session = Depends(get_db)):
    active_rows = db.query(AtlasEntry).all()
    by_category: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in active_rows:
        by_category[row.category] = by_category.get(row.category, 0) + 1
        by_status[row.status] = by_status.get(row.status, 0) + 1

    return schemas.MemoryStatsOut(
        total_active=sum(1 for r in active_rows if r.status == "active"),
        by_category=by_category,
        by_status=by_status,
        pending_candidates=db.query(MemoryCandidate).filter(MemoryCandidate.status == "pending").count(),
        accepted_candidates=db.query(MemoryCandidate).filter(MemoryCandidate.status == "accepted").count(),
        rejected_candidates=db.query(MemoryCandidate).filter(MemoryCandidate.status == "rejected").count(),
        open_conflicts=db.query(MemoryConflict).filter(MemoryConflict.status.in_(["open", "user_review_required"])).count(),
        resolved_conflicts=db.query(MemoryConflict).filter(MemoryConflict.status == "resolved").count(),
        consolidation_events=db.query(MemoryConsolidationEvent).count(),
    )


# ---- Single-memory routes (registered last — see module docstring) ----


def _get_entry_or_404(db: Session, memory_id: str) -> AtlasEntry:
    entry = db.get(AtlasEntry, memory_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return entry


@router.get("/{memory_id}", response_model=schemas.AtlasEntryOut)
def get_memory(memory_id: str, db: Session = Depends(get_db)):
    return _get_entry_or_404(db, memory_id)


@router.patch("/{memory_id}", response_model=schemas.AtlasEntryOut)
def update_memory(memory_id: str, payload: schemas.AtlasEntryUpdate, db: Session = Depends(get_db)):
    entry = _get_entry_or_404(db, memory_id)
    return atlas_store.update_entry(db, entry, payload)


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: str, db: Session = Depends(get_db)):
    """Real, permanent deletion — not archival. See POST .../archive for the
    reversible alternative. Explicit endpoint per rule 8 ("deletion endpoints
    must be explicit")."""
    entry = _get_entry_or_404(db, memory_id)
    atlas_store.delete_entry(db, entry)


@router.post("/{memory_id}/archive", response_model=schemas.AtlasEntryOut)
def archive_memory(memory_id: str, db: Session = Depends(get_db)):
    return memory_lifecycle.archive(db, _get_entry_or_404(db, memory_id))


@router.post("/{memory_id}/restore", response_model=schemas.AtlasEntryOut)
def restore_memory(memory_id: str, db: Session = Depends(get_db)):
    return memory_lifecycle.restore(db, _get_entry_or_404(db, memory_id))


@router.post("/{memory_id}/confirm", response_model=schemas.AtlasEntryOut)
def confirm_memory(memory_id: str, db: Session = Depends(get_db)):
    return memory_lifecycle.mark_verified(db, _get_entry_or_404(db, memory_id))


@router.post("/{memory_id}/mark-outdated", response_model=schemas.AtlasEntryOut)
def mark_memory_outdated(memory_id: str, db: Session = Depends(get_db)):
    return memory_lifecycle.mark_outdated(db, _get_entry_or_404(db, memory_id))
