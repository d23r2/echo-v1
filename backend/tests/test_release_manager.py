"""ECHO Action + Reliability Core v1 — Release / Build Manager."""

import pytest

from app.services import release_manager


def test_create_release(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    assert release.status == "draft"
    assert release.version_name == "v1.2.0"


def test_add_backend_test_check(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    check = release_manager.add_check(db_session, release.id, check_name="Backend tests", platform="backend", command="python -m pytest backend/tests", status="pass")
    assert check.status == "pass"


def test_add_web_build_check(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    release_manager.add_check(db_session, release.id, check_name="Backend tests", platform="backend", status="pass")
    check = release_manager.add_check(db_session, release.id, check_name="Frontend build", platform="web", status="pass")
    assert check.platform == "web"


def test_status_green_only_if_required_checks_pass(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    release_manager.add_check(db_session, release.id, check_name="Backend tests", platform="backend", status="pass")
    release_manager.add_check(db_session, release.id, check_name="Frontend build", platform="web", status="pass")
    release_manager.add_check(db_session, release.id, check_name="Manual checklist", platform="manual", status="pass")
    refreshed = release_manager.get_release(db_session, release.id)
    assert refreshed.status == "green"


def test_status_yellow_if_checks_missing(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    release_manager.add_check(db_session, release.id, check_name="Backend tests", platform="backend", status="pass")
    refreshed = release_manager.get_release(db_session, release.id)
    assert refreshed.status == "yellow"


def test_status_red_if_required_check_fails(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    release_manager.add_check(db_session, release.id, check_name="Backend tests", platform="backend", status="fail")
    release_manager.add_check(db_session, release.id, check_name="Frontend build", platform="web", status="pass")
    release_manager.add_check(db_session, release.id, check_name="Manual checklist", platform="manual", status="pass")
    refreshed = release_manager.get_release(db_session, release.id)
    assert refreshed.status == "red"


def test_status_never_green_without_recorded_evidence(db_session):
    """A release with zero recorded checks must never claim green — this is
    the direct 'don't say Green without test results' rule."""
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    assert release.status != "green"


def test_artifact_path_stored_cleanly(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    artifact = release_manager.add_artifact(db_session, release.id, platform="android", artifact_type="apk", path="frontend/android/app/build/outputs/apk/debug/app-debug.apk")
    assert artifact.path.endswith(".apk")


def test_seed_standard_checklist(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    checks = release_manager.seed_standard_checklist(db_session, release.id)
    assert len(checks) == len(release_manager.STANDARD_CHECKLIST)
    # Idempotent — running again doesn't duplicate.
    checks_again = release_manager.seed_standard_checklist(db_session, release.id)
    assert checks_again == []


def test_mark_status_override(db_session):
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    release_manager.add_check(db_session, release.id, check_name="Backend tests", platform="backend", status="pass")
    release_manager.add_check(db_session, release.id, check_name="Frontend build", platform="web", status="pass")
    release_manager.add_check(db_session, release.id, check_name="Manual checklist", platform="manual", status="pass")
    released = release_manager.mark_status(db_session, release.id, "released")
    assert released.status == "released"
    # Further checks shouldn't silently revert a released version's status.
    release_manager.add_check(db_session, release.id, check_name="Extra check", platform="backend", status="fail")
    refreshed = release_manager.get_release(db_session, release.id)
    assert refreshed.status == "released"


def test_create_release_requires_version_name(db_session):
    with pytest.raises(ValueError):
        release_manager.create_release(db_session, version_name="  ")


def test_marking_a_seeded_check_updates_in_place_not_duplicates(db_session):
    """Regression test for a bug caught during live browser verification:
    seeding the standard checklist then marking one of those checks 'pass'
    via add_check() must UPDATE that row, not append a second row with the
    same check_name — otherwise the original 'not_run' seed row lingers
    forever in required_checks and compute_status() never reaches green
    even after every check has genuinely been marked pass."""
    release = release_manager.create_release(db_session, version_name="v1.2.0")
    release_manager.seed_standard_checklist(db_session, release.id)

    # Every check on a required platform (backend/web/manual) — matches
    # compute_status()'s "every recorded required check must pass" rule.
    for check_name, platform in [
        ("Backend test suite", "backend"),
        ("Backend lint", "backend"),
        ("Frontend build", "web"),
        ("Frontend typecheck", "web"),
        ("Manual checklist", "manual"),
    ]:
        release_manager.add_check(db_session, release.id, check_name=check_name, platform=platform, status="pass")

    refreshed = release_manager.get_release(db_session, release.id)
    backend_checks = [c for c in refreshed.checks if c.check_name == "Backend test suite"]
    assert len(backend_checks) == 1
    assert backend_checks[0].status == "pass"
    assert refreshed.status == "green"
