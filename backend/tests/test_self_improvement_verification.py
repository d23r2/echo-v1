"""Tests for real local self-improvement verification (Goal 10).

Covers the pure verification module (app/self_improvement_verify.py) with real
subprocess calls to trivial, cross-platform commands (no dependency on git/pytest
actually being installed), plus the founder-approval-gated /verify route with a
monkeypatched verification function so route tests stay fast and deterministic.
"""

import shutil
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import self_improvement_verify as verify_mod
from app.db import SessionLocal, init_db
from app.main import app
from app.models import SelfImprovementRequest
from app.self_improvement_verify import (
    _module_available,
    _resolve_backend_dir,
    _run,
    run_verification,
    summarize,
)

client = TestClient(app)


# ---- summarize() — pure function, no subprocess involved ----


def test_summarize_all_passed():
    checks = [
        {"command": "a", "status": "passed"},
        {"command": "b", "status": "passed"},
    ]
    status, notes = summarize(checks)
    assert status == "passed"
    assert "2/2 runnable checks passed" in notes


def test_summarize_one_failed():
    checks = [
        {"command": "git status --short", "status": "passed"},
        {"command": "pytest -q", "status": "failed"},
    ]
    status, notes = summarize(checks)
    assert status == "failed"
    assert "failed: pytest -q" in notes


def test_summarize_unavailable_does_not_count_as_failure():
    checks = [
        {"command": "git status --short", "status": "passed"},
        {"command": "ruff check .", "status": "unavailable"},
        {"command": "mypy app", "status": "unavailable"},
    ]
    status, notes = summarize(checks)
    assert status == "passed"
    assert "unavailable: ruff check ., mypy app" in notes


def test_summarize_nothing_ran():
    checks = [
        {"command": "git status --short", "status": "unavailable"},
    ]
    status, notes = summarize(checks)
    assert status == "failed"
    assert "No checks could run" in notes


# ---- _run() / _module_available() — real subprocess, trivial commands only ----


def test_run_reports_passed_on_zero_exit(tmp_path):
    result = _run([sys.executable, "-c", "import sys; sys.exit(0)"], cwd=tmp_path)
    assert result.status == "passed"
    assert result.exit_code == 0


def test_run_reports_failed_on_nonzero_exit(tmp_path):
    result = _run([sys.executable, "-c", "import sys; sys.exit(1)"], cwd=tmp_path)
    assert result.status == "failed"
    assert result.exit_code == 1


def test_run_reports_unavailable_for_missing_binary(tmp_path):
    result = _run(["definitely-not-a-real-binary-xyz"], cwd=tmp_path)
    assert result.status == "unavailable"
    assert result.exit_code is None
    assert "not installed" in result.stderr_summary or "not on PATH" in result.stderr_summary


def test_run_does_not_crash_on_missing_binary(tmp_path):
    # The whole point of this feature: a missing tool must never raise.
    result = _run(["definitely-not-a-real-binary-xyz"], cwd=tmp_path)
    assert result is not None


def test_module_available_true_for_installed_pytest():
    assert _module_available("pytest") is True


def test_module_available_false_for_nonexistent_module():
    assert _module_available("definitely_not_a_real_python_module_xyz") is False


# ---- run_verification() wiring ----


def test_run_verification_all_tools_unavailable_does_not_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(verify_mod.shutil, "which", lambda name: None)
    monkeypatch.setattr(verify_mod, "_module_available", lambda name: False)

    checks = run_verification(repo_root=tmp_path, backend_dir=tmp_path)

    assert len(checks) == 5  # git status, git diff, pytest, ruff, mypy
    assert all(c["status"] == "unavailable" for c in checks)
    status, notes = summarize(checks)
    assert status == "failed"


def test_run_verification_real_git_in_temp_repo(tmp_path, monkeypatch):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    monkeypatch.setattr(verify_mod, "_module_available", lambda name: False)

    checks = run_verification(repo_root=tmp_path, backend_dir=tmp_path)
    by_command = {c["command"]: c for c in checks}

    assert by_command["git status --short"]["status"] == "passed"
    assert by_command["git diff --stat"]["status"] == "passed"
    assert by_command["pytest -q"]["status"] == "unavailable"
    assert by_command["ruff check ."]["status"] == "unavailable"
    assert by_command["mypy app"]["status"] == "unavailable"

    status, notes = summarize(checks)
    assert status == "passed"
    assert "2/2 runnable checks passed" in notes


def test_run_verification_git_installed_but_no_git_repo_is_unavailable_not_failed(tmp_path):
    # Regression test for a real bug found via live Docker testing: the
    # production image doesn't ship a .git directory (see backend/Dockerfile —
    # only app/ is copied in), so running git there previously came back
    # "failed" (a confusing, misleading verdict) instead of the honest
    # "unavailable" every other missing-tool case already gets.
    if shutil.which("git") is None:
        pytest.skip("git not installed in this test environment")

    checks = run_verification(repo_root=tmp_path, backend_dir=tmp_path)
    by_command = {c["command"]: c for c in checks}

    assert by_command["git status --short"]["status"] == "unavailable"
    assert "not a git repository" in by_command["git status --short"]["stderr_summary"]


def test_resolve_backend_dir_uses_backend_subdir_when_present(tmp_path):
    (tmp_path / "backend").mkdir()
    assert _resolve_backend_dir(tmp_path) == tmp_path / "backend"


def test_resolve_backend_dir_falls_back_to_repo_root_when_no_backend_subdir(tmp_path):
    # Matches the production Docker layout: WORKDIR /app has app/ and data/
    # directly, no wrapping backend/ subdirectory.
    assert _resolve_backend_dir(tmp_path) == tmp_path


# ---- /api/self-improvement/{id}/verify route ----


def _make_request_in_app_db(*, status: str = "proposed") -> str:
    init_db()
    db = SessionLocal()
    try:
        req = SelfImprovementRequest(
            title="Test improvement",
            description="Do a thing",
            proposed_by="founder",
            status=status,
        )
        db.add(req)
        db.commit()
        db.refresh(req)
        return req.id
    finally:
        db.close()


def test_verify_rejects_unapproved_request():
    request_id = _make_request_in_app_db(status="proposed")
    resp = client.post(f"/api/self-improvement/{request_id}/verify")
    assert resp.status_code == 400
    assert "approved" in resp.json()["detail"].lower()


def test_verify_runs_and_stores_real_results(monkeypatch):
    request_id = _make_request_in_app_db(status="approved")

    fake_checks = [
        {
            "command": "git status --short",
            "status": "passed",
            "exit_code": 0,
            "stdout_summary": "",
            "stderr_summary": "",
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
        {
            "command": "pytest -q",
            "status": "failed",
            "exit_code": 1,
            "stdout_summary": "1 failed, 3 passed",
            "stderr_summary": "",
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
        {
            "command": "ruff check .",
            "status": "unavailable",
            "exit_code": None,
            "stdout_summary": "",
            "stderr_summary": "ruff is not installed — skipped (optional tool)",
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
    ]
    monkeypatch.setattr(
        "app.routers.self_improvement.run_verification", lambda: fake_checks
    )

    resp = client.post(f"/api/self-improvement/{request_id}/verify")
    assert resp.status_code == 200
    body = resp.json()

    assert body["verification_status"] == "failed"
    assert "pytest -q" in body["verification_notes"]
    assert len(body["verification_checks"]) == 3
    assert body["verified_at"] is not None
    # Must never claim code was applied — this is read-only verification.
    assert "no code was modified" in body["patch_summary"].lower()


def test_verify_passing_case_reports_passed(monkeypatch):
    request_id = _make_request_in_app_db(status="approved")

    fake_checks = [
        {
            "command": "git status --short",
            "status": "passed",
            "exit_code": 0,
            "stdout_summary": "",
            "stderr_summary": "",
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
        {
            "command": "pytest -q",
            "status": "passed",
            "exit_code": 0,
            "stdout_summary": "124 passed",
            "stderr_summary": "",
            "timestamp": "2026-01-01T00:00:00+00:00",
        },
    ]
    monkeypatch.setattr(
        "app.routers.self_improvement.run_verification", lambda: fake_checks
    )

    resp = client.post(f"/api/self-improvement/{request_id}/verify")
    assert resp.status_code == 200
    body = resp.json()
    assert body["verification_status"] == "passed"


def test_verify_missing_request_returns_404():
    resp = client.post("/api/self-improvement/does-not-exist/verify")
    assert resp.status_code == 404
