"""ECHO Action + Reliability Core v1 — Release / Build Manager.

v1 stores manual/recorded results and shows the commands to run — it does
not execute shell/build commands itself (Phase 8's own explicit rule).
Status is always computed from recorded ReleaseCheck rows, never hand-set
to "green" independent of what was actually recorded — see compute_status().
"""

from sqlalchemy.orm import Session

from app.models import ReleaseArtifact, ReleaseCheck, ReleaseRecord

# Mirrors DEVELOPMENT.md's real commands — shown to the user, never run here.
STANDARD_CHECKLIST: list[dict] = [
    {"check_name": "Backend test suite", "platform": "backend", "command": "python -m pytest backend/tests"},
    {"check_name": "Backend lint", "platform": "backend", "command": "cd backend && ruff check ."},
    {"check_name": "Frontend build", "platform": "web", "command": "cd frontend && npm run build"},
    {"check_name": "Frontend typecheck", "platform": "web", "command": "cd frontend && npm run typecheck"},
    {"check_name": "Android sync", "platform": "android", "command": "npx cap sync android"},
    {"check_name": "Android debug APK", "platform": "android", "command": "cd frontend/android && .\\gradlew assembleDebug"},
    {"check_name": "Windows Tauri build", "platform": "windows", "command": "npm run tauri build"},
    {"check_name": "Manual checklist", "platform": "manual", "command": None},
]

# A release only reaches "green" if every check on a REQUIRED platform has
# actually been recorded as "pass" — "manual" is required too (an unchecked
# manual pass is still an unverified claim), but "android"/"windows" are not
# required by default since not every environment can build them (matches
# this repo's own established Android/Tauri-optional posture).
_REQUIRED_PLATFORMS = {"backend", "web", "manual"}


def create_release(db: Session, *, version_name: str, summary: str = "", git_commit: str | None = None, git_tag: str | None = None) -> ReleaseRecord:
    if not version_name.strip():
        raise ValueError("A version name is required.")
    release = ReleaseRecord(version_name=version_name.strip(), summary=summary, git_commit=git_commit, git_tag=git_tag)
    db.add(release)
    db.commit()
    db.refresh(release)
    return release


def list_releases(db: Session) -> list[ReleaseRecord]:
    return db.query(ReleaseRecord).order_by(ReleaseRecord.created_at.desc()).all()


def get_release(db: Session, release_id: str) -> ReleaseRecord | None:
    return db.get(ReleaseRecord, release_id)


def update_release(db: Session, release_id: str, updates: dict) -> ReleaseRecord:
    release = db.get(ReleaseRecord, release_id)
    if release is None:
        raise ValueError("That release doesn't exist.")
    for field, value in updates.items():
        if value is not None:
            setattr(release, field, value)
    db.commit()
    db.refresh(release)
    return release


def add_check(db: Session, release_id: str, **fields) -> ReleaseCheck:
    """Upserts by (release_id, check_name) — recording a result for a check
    that already exists (e.g. re-running "Backend tests", or marking a
    seeded "not_run" row as pass/fail from the UI) updates that row in
    place rather than appending a duplicate. Without this, a stale
    "not_run" seed row would sit alongside a new "pass" row forever and
    compute_status() would never see the check as actually resolved."""
    release = db.get(ReleaseRecord, release_id)
    if release is None:
        raise ValueError("That release doesn't exist.")
    existing = (
        db.query(ReleaseCheck)
        .filter(ReleaseCheck.release_id == release_id, ReleaseCheck.check_name == fields.get("check_name"))
        .first()
    )
    if existing is not None:
        for field, value in fields.items():
            setattr(existing, field, value)
        check = existing
    else:
        check = ReleaseCheck(release_id=release_id, **fields)
        db.add(check)
    db.commit()
    db.refresh(check)
    _recompute_status(db, release)
    return check


def seed_standard_checklist(db: Session, release_id: str) -> list[ReleaseCheck]:
    release = db.get(ReleaseRecord, release_id)
    if release is None:
        raise ValueError("That release doesn't exist.")
    existing_names = {c.check_name for c in release.checks}
    added = []
    for entry in STANDARD_CHECKLIST:
        if entry["check_name"] in existing_names:
            continue
        check = ReleaseCheck(release_id=release_id, **entry)
        db.add(check)
        added.append(check)
    db.commit()
    for check in added:
        db.refresh(check)
    return added


def add_artifact(db: Session, release_id: str, *, platform: str, artifact_type: str, path: str) -> ReleaseArtifact:
    release = db.get(ReleaseRecord, release_id)
    if release is None:
        raise ValueError("That release doesn't exist.")
    artifact = ReleaseArtifact(release_id=release_id, platform=platform, artifact_type=artifact_type, path=path)
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def compute_status(release: ReleaseRecord) -> str:
    """Green only if every REQUIRED-platform check that was recorded at all
    is a pass and every required platform has at least one recorded check.
    Yellow if checks are missing or any warning exists. Red if any recorded
    check failed. This mirrors the honest-Green rule the rest of this repo
    already follows — never claim green without recorded evidence."""
    checks = release.checks
    if not checks:
        return "draft"
    if any(c.status == "fail" for c in checks):
        return "red"
    recorded_platforms = {c.platform for c in checks if c.status != "not_run"}
    missing_required = _REQUIRED_PLATFORMS - recorded_platforms
    if missing_required:
        return "yellow"
    required_checks = [c for c in checks if c.platform in _REQUIRED_PLATFORMS]
    if any(c.status in ("not_run", "warning") for c in required_checks):
        return "yellow"
    if all(c.status == "pass" for c in required_checks):
        return "green"
    return "yellow"


def _recompute_status(db: Session, release: ReleaseRecord) -> None:
    if release.status in ("released",):
        return  # a released version's status is a historical record, not recomputed
    release.status = compute_status(release)
    db.commit()


def mark_status(db: Session, release_id: str, status: str) -> ReleaseRecord:
    """Manual override (e.g. marking "released") — everything else flows
    through _recompute_status() automatically as checks are added."""
    release = db.get(ReleaseRecord, release_id)
    if release is None:
        raise ValueError("That release doesn't exist.")
    release.status = status
    db.commit()
    db.refresh(release)
    return release
