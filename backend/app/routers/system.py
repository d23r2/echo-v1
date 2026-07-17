"""ECHO Layer 0 — health/readiness/status/diagnostics/version/metrics.

Two bare (no /api prefix) routes for orchestration-style probes (`/health`,
`/ready`), everything else under `/api/system/*` alongside this app's
existing `/api/health` (kept unchanged — some deployment/monitoring
config may already point at it) and `/api/features` (kept unchanged — the
frontend chat UI already depends on its exact shape).
"""

import time
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.core import metrics
from app.core.feature_flags import list_feature_flags
from app.db import engine, get_db
from app.providers.registry import build_local_model_roles, build_provider_registry
from app.router import ModelRouter
from app.services.local_model_router import list_installed_models

router = APIRouter(tags=["system"])
_model_router = ModelRouter()

_REQUIRED_TABLES = ("conversations", "messages", "atlas_entries")


def _database_healthy() -> tuple[bool, str | None]:
    try:
        with engine.connect() as conn:
            existing = {row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = [t for t in _REQUIRED_TABLES if t not in existing]
        if missing:
            return False, f"missing required tables: {', '.join(missing)}"
        return True, None
    except Exception as exc:
        return False, f"database error: {type(exc).__name__}"


def _ollama_health(settings: Settings) -> str:
    if not settings.ollama_enabled:
        return "not_configured"
    _, error = list_installed_models()
    return "offline" if error else "healthy"


@router.get("/health")
def health():
    """Process-alive check only — no DB/network calls, so this never blocks
    even if a dependency is unhealthy. Matches this app's existing
    `/api/health` in spirit; kept as a separate bare route since orchestration
    tooling conventionally probes `/health`, not an API-prefixed path."""
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    healthy, reason = _database_healthy()
    if not healthy:
        return {"ready": False, "reason": reason}
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return {"ready": False, "reason": "database not reachable"}
    return {"ready": True}


@router.get("/api/system/status")
def system_status(db: Session = Depends(get_db)):
    settings = get_settings()
    db_healthy, db_reason = _database_healthy()
    ollama_status = _ollama_health(settings)

    warnings: list[str] = []
    if db_reason:
        warnings.append(db_reason)
    if ollama_status == "offline":
        warnings.append("Ollama is enabled but not reachable")

    if not db_healthy:
        overall = "red"
    elif ollama_status == "offline" and not settings.cloud_fallback_enabled:
        overall = "yellow"
    else:
        overall = "green"

    return {
        "status": overall,
        "backend": "healthy" if db_healthy else "unhealthy",
        "database": "healthy" if db_healthy else "unhealthy",
        "ollama": ollama_status,
        "frontend_expected_url": settings.frontend_url,
        "backend_url": f"http://localhost:{settings.port}",
        "wiki": "enabled" if settings.wiki_search_enabled else "disabled",
        "rss": "enabled" if (settings.rss_search_enabled and settings.rss_feed_url_list) else "disabled",
        "searxng": "enabled" if (settings.web_search_enabled and settings.searxng_base_url) else "disabled",
        "atlas": "healthy" if db_healthy else "unhealthy",
        "cognitive_core": "enabled" if settings.cognitive_core_enabled else "disabled",
        "version": settings.app_version,
        "warnings": warnings,
    }


@router.get("/api/system/diagnostics")
def system_diagnostics(db: Session = Depends(get_db)):
    """Developer-oriented but sanitized — see Settings.public_dict() for the
    secret-exclusion guarantee, and core/logging.py's redact() as a second
    layer if anything here were ever logged."""
    settings = get_settings()
    db_healthy, db_reason = _database_healthy()

    data_dir_writable = True
    write_check_error = None
    try:
        probe = Path(settings.database_backup_path)
        probe.mkdir(parents=True, exist_ok=True)
        test_file = probe / ".write_check"
        test_file.write_text("ok")
        test_file.unlink()
    except Exception as exc:
        data_dir_writable = False
        write_check_error = type(exc).__name__

    flags = list_feature_flags(settings, db)
    providers = build_provider_registry(settings, _model_router, db)

    return {
        "configuration": settings.public_dict(),
        "feature_flags": [f.__dict__ for f in flags],
        "providers": [p.__dict__ for p in providers],
        "database": {
            "healthy": db_healthy,
            "reason": db_reason,
            "path_configured": bool(settings.database_url),
            "engine": engine.dialect.name,
            "writable_backup_dir": data_dir_writable,
            "write_check_error": write_check_error,
        },
        "schema_version": _get_schema_version(),
        "version": settings.app_version,
    }


def _get_schema_version() -> int:
    try:
        with engine.connect() as conn:
            row = conn.exec_driver_sql("SELECT version FROM schema_version LIMIT 1").fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


@router.get("/api/system/features")
def system_features(db: Session = Depends(get_db)):
    settings = get_settings()
    flags = list_feature_flags(settings, db)
    return {"features": [f.__dict__ for f in flags]}


@router.get("/api/system/providers")
def system_providers(db: Session = Depends(get_db)):
    settings = get_settings()
    return {"providers": [p.__dict__ for p in build_provider_registry(settings, _model_router, db)]}


@router.get("/api/system/models")
def system_models():
    settings = get_settings()
    installed, error = list_installed_models()
    return {
        "installed_ollama_models": installed,
        "ollama_error": error,
        "local_model_roles": [r.__dict__ for r in build_local_model_roles(settings)],
    }


@router.post("/api/system/providers/{provider_id}/check")
def check_provider(provider_id: str):
    provider = _model_router.get_provider(provider_id)
    if provider is None:
        return {"provider_id": provider_id, "found": False}
    start = time.monotonic()
    available, reason = provider.available()
    elapsed_ms = (time.monotonic() - start) * 1000
    return {"provider_id": provider_id, "found": True, "available": available, "reason": reason, "checked_in_ms": round(elapsed_ms, 1)}


@router.get("/api/system/metrics")
def system_metrics():
    settings = get_settings()
    if not settings.metrics_enabled:
        return {"enabled": False}
    snap = metrics.snapshot()
    snap["enabled"] = True
    return snap


@router.get("/api/system/version")
def system_version():
    settings = get_settings()
    return {
        "application_version": settings.app_version,
        "backend_version": settings.app_version,
        "frontend_expected_version": settings.app_version,
        "schema_version": _get_schema_version(),
        "api_version": "1",
    }
