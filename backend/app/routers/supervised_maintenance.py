from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import schemas
from app.db import get_db
from app.models import ApprovedRepository, MaintenanceAuditEvent
from app.services import maintenance_analysis, maintenance_code_access, maintenance_policy
from app.services.maintenance_code_access import CodeAccessPermissionError, CodeAccessRejectedError
from app.services.maintenance_policy import (
    MaintenanceNotFoundError,
    MaintenancePermissionError,
    MaintenancePolicyError,
)

router = APIRouter(prefix="/api/governance/supervised-maintenance", tags=["supervised-maintenance"])

_POLICY_ERROR_STATUS = {
    MaintenanceNotFoundError: 404,
    MaintenancePermissionError: 403,
    MaintenancePolicyError: 400,
}
_ANALYSIS_ERROR_STATUS = {
    maintenance_analysis.MaintenanceAnalysisNotFoundError: 404,
    maintenance_analysis.MaintenanceAnalysisPermissionError: 403,
    maintenance_analysis.MaintenanceAnalysisStateError: 409,
    maintenance_analysis.MaintenanceAnalysisError: 400,
}
_ACCESS_ERROR_STATUS = {
    CodeAccessPermissionError: 403,
    CodeAccessRejectedError: 400,
}


def _run(fn, error_status: dict, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except tuple(error_status) as exc:
        status_code = error_status.get(type(exc), 400)
        raise HTTPException(status_code=status_code, detail=str(exc)) from None


@router.get("/status", response_model=schemas.MaintenanceHealthOut)
def status(db: Session = Depends(get_db)):
    return maintenance_analysis.get_health(db)


@router.get("/policy")
def policy():
    from app.services import self_modification_governance as governance

    return {
        "protected_paths": sorted(governance.PROTECTED_PATHS),
        "protected_path_prefixes": list(governance.PROTECTED_PATH_PREFIXES),
        "protected_symbols": [name for name, _pattern in governance.PROTECTED_SYMBOL_PATTERNS],
        "allowed_path_prefixes": list(governance.ALLOWED_PATH_PREFIXES),
        "secret_filename_patterns": [p.pattern for p in maintenance_code_access._SECRET_FILENAME_PATTERNS],
        "capability_modes": ["disabled", "analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit"],
    }


# ---- Repositories (registration is owner-only, enforced inside the service) ----


@router.get("/repositories", response_model=list[schemas.ApprovedRepositoryOut])
def list_repositories(db: Session = Depends(get_db)):
    return maintenance_policy.list_repositories(db)


@router.post("/repositories", response_model=schemas.ApprovedRepositoryOut)
def register_repository(payload: schemas.ApprovedRepositoryCreate, db: Session = Depends(get_db)):
    return _run(
        maintenance_policy.register_repository, _POLICY_ERROR_STATUS, db,
        display_name=payload.display_name, requested_by=payload.requested_by,
        approved_branches=payload.approved_branches or None,
    )


def _get_repository_or_404(db: Session, repository_id: str) -> ApprovedRepository:
    repo = db.get(ApprovedRepository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.get("/repositories/{repository_id}", response_model=schemas.ApprovedRepositoryOut)
def get_repository(repository_id: str, db: Session = Depends(get_db)):
    return _get_repository_or_404(db, repository_id)


@router.post("/repositories/{repository_id}/mode", response_model=schemas.ApprovedRepositoryOut)
def set_capability_mode(repository_id: str, payload: schemas.ApprovedRepositoryModeUpdate, db: Session = Depends(get_db)):
    return _run(
        maintenance_policy.set_capability_mode, _POLICY_ERROR_STATUS, db, repository_id,
        payload.capability_mode, requested_by=payload.requested_by,
    )


@router.post("/repositories/{repository_id}/verify", response_model=schemas.ApprovedRepositoryOut)
def verify_repository(repository_id: str, db: Session = Depends(get_db)):
    repo, _drifted = _run(maintenance_policy.verify_repository, _POLICY_ERROR_STATUS, db, repository_id)
    return repo


# ---- Read-only code access (CodeAccessService) ----


@router.get("/repositories/{repository_id}/files", response_model=list[schemas.MaintenanceFileEntryOut])
def list_files(repository_id: str, subpath: str = "", db: Session = Depends(get_db)):
    repo = _get_repository_or_404(db, repository_id)
    entries = _run(maintenance_code_access.list_repository_files, _ACCESS_ERROR_STATUS, repo, subpath)
    return [schemas.MaintenanceFileEntryOut(path=e.path, size_bytes=e.size_bytes, is_directory=e.is_directory) for e in entries]


@router.get("/repositories/{repository_id}/file", response_model=schemas.MaintenanceFileContentOut)
def read_file(repository_id: str, path: str, db: Session = Depends(get_db)):
    repo = _get_repository_or_404(db, repository_id)
    content = _run(maintenance_code_access.read_repository_file, _ACCESS_ERROR_STATUS, repo, path)
    return schemas.MaintenanceFileContentOut(path=content.path, content=content.content, sha256=content.sha256)


@router.get("/repositories/{repository_id}/search", response_model=list[schemas.MaintenanceSearchHitOut])
def search_code(repository_id: str, q: str, subpath: str = "", db: Session = Depends(get_db)):
    repo = _get_repository_or_404(db, repository_id)
    hits = _run(maintenance_code_access.search_repository_text, _ACCESS_ERROR_STATUS, repo, q, subpath=subpath)
    return [schemas.MaintenanceSearchHitOut(path=h.path, line=h.line, text=h.text) for h in hits]


@router.get("/repositories/{repository_id}/git-status")
def git_status(repository_id: str, db: Session = Depends(get_db)):
    repo = _get_repository_or_404(db, repository_id)
    return {"output": _run(maintenance_code_access.inspect_git_status, _ACCESS_ERROR_STATUS, repo)}


@router.get("/repositories/{repository_id}/git-diff")
def git_diff(repository_id: str, staged: bool = False, db: Session = Depends(get_db)):
    repo = _get_repository_or_404(db, repository_id)
    return {"output": _run(maintenance_code_access.inspect_git_diff, _ACCESS_ERROR_STATUS, repo, staged=staged)}


# ---- Analyses (MaintenanceAnalysisService) ----


@router.get("/analyses", response_model=list[schemas.MaintenanceAnalysisOut])
def list_analyses(repository_id: str | None = None, db: Session = Depends(get_db)):
    return maintenance_analysis.list_analyses(db, repository_id)


@router.post("/analyses", response_model=schemas.MaintenanceAnalysisOut)
def create_analysis(payload: schemas.MaintenanceAnalysisCreate, db: Session = Depends(get_db)):
    return _run(
        maintenance_analysis.create_analysis, _ANALYSIS_ERROR_STATUS, db,
        repository_id=payload.repository_id, objective=payload.objective,
        requested_by=payload.requested_by, problem_statement=payload.problem_statement,
    )


@router.get("/analyses/{analysis_id}", response_model=schemas.MaintenanceAnalysisOut)
def get_analysis(analysis_id: str, db: Session = Depends(get_db)):
    return _run(maintenance_analysis.get_analysis, _ANALYSIS_ERROR_STATUS, db, analysis_id)


@router.post("/analyses/{analysis_id}/propose", response_model=schemas.SelfModProposalOut)
def propose_from_analysis(analysis_id: str, payload: schemas.MaintenanceProposalFromAnalysisCreate, db: Session = Depends(get_db)):
    from app.services import maintenance_proposal

    error_status = {
        maintenance_proposal.MaintenanceProposalPermissionError: 403,
        maintenance_proposal.MaintenanceProposalStateError: 409,
        maintenance_proposal.MaintenanceProposalError: 400,
    }
    return _run(
        maintenance_proposal.create_proposal_from_analysis, error_status, db,
        analysis_id=analysis_id, title=payload.title, description=payload.description,
        rationale=payload.rationale, patch_text=payload.patch_text, proposed_by=payload.proposed_by,
    )


@router.get("/analyses/{analysis_id}/findings", response_model=list[schemas.MaintenanceFindingOut])
def list_findings(analysis_id: str, db: Session = Depends(get_db)):
    return _run(maintenance_analysis.list_findings, _ANALYSIS_ERROR_STATUS, db, analysis_id)


@router.post("/analyses/{analysis_id}/findings", response_model=schemas.MaintenanceFindingOut)
def add_finding(analysis_id: str, payload: schemas.MaintenanceFindingCreate, db: Session = Depends(get_db)):
    return _run(
        maintenance_analysis.add_finding, _ANALYSIS_ERROR_STATUS, db, analysis_id,
        epistemic_status=payload.epistemic_status, description=payload.description,
        affected_files=payload.affected_files, evidence_reference=payload.evidence_reference,
    )


@router.post("/analyses/{analysis_id}/complete", response_model=schemas.MaintenanceAnalysisOut)
def complete_analysis(analysis_id: str, db: Session = Depends(get_db)):
    return _run(maintenance_analysis.complete_analysis, _ANALYSIS_ERROR_STATUS, db, analysis_id)


@router.post("/analyses/{analysis_id}/cancel", response_model=schemas.MaintenanceAnalysisOut)
def cancel_analysis(analysis_id: str, reason: str = "", db: Session = Depends(get_db)):
    return _run(maintenance_analysis.cancel_analysis, _ANALYSIS_ERROR_STATUS, db, analysis_id, reason=reason)


# ---- Audit ----


@router.get("/audit", response_model=list[schemas.MaintenanceAuditEventOut])
def get_audit_trail(repository_id: str | None = None, analysis_id: str | None = None, db: Session = Depends(get_db)):
    query = db.query(MaintenanceAuditEvent)
    if repository_id:
        query = query.filter(MaintenanceAuditEvent.repository_id == repository_id)
    if analysis_id:
        query = query.filter(MaintenanceAuditEvent.analysis_id == analysis_id)
    return query.order_by(MaintenanceAuditEvent.created_at.asc()).all()
