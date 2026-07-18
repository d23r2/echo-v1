"""ECHO Layer 3A Part 2D — self_modification_sandbox.py.

Real git/subprocess tests, same pattern as
test_self_improvement_verification.py's tmp_path git fixture: every test
here passes repo_root=tmp_path explicitly so nothing ever touches the real
ECHO repository's git state. Never call these functions without repo_root.
"""

import shutil
import subprocess

import pytest

import selfmod_runner
from app.services import self_modification_sandbox as sandbox


def _init_repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.local"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "mod.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    return tmp_path


def _make_patch(tmp_path) -> str:
    """Edits mod.py, captures the real `git diff`, then reverts the working
    tree — giving a genuinely git-apply-able patch without hand-crafting one."""
    mod = tmp_path / "backend" / "mod.py"
    mod.write_text("def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n", encoding="utf-8", newline="\n")
    diff = subprocess.run(["git", "diff"], cwd=tmp_path, capture_output=True, text=True, check=True).stdout
    subprocess.run(["git", "checkout", "--", "backend/mod.py"], cwd=tmp_path, check=True)
    return diff


@pytest.fixture()
def git_fixture_repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not installed in this test environment")
    return _init_repo(tmp_path)


def test_current_head_resolves_a_commit_sha(git_fixture_repo):
    head = sandbox.current_head(git_fixture_repo)
    assert len(head) == 40
    assert all(c in "0123456789abcdef" for c in head)


def test_run_patch_in_sandbox_applies_and_verifies(git_fixture_repo):
    patch_text = _make_patch(git_fixture_repo)
    patch_hash = sandbox.hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    head = sandbox.current_head(git_fixture_repo)

    result = sandbox.run_patch_in_sandbox(
        patch_text, patch_hash, head, repo_root=git_fixture_repo, runner="host-test"
    )

    assert result.base_commit == head
    by_command = {c["command"]: c for c in result.checks}
    assert "python -m ruff check app tests" in by_command
    assert "python -B -m pytest -p no:cacheprovider -q" in by_command

    # The primary working tree's file must be untouched — the patch only
    # ever applied inside the (now torn-down) sandbox worktree.
    original = (git_fixture_repo / "backend" / "mod.py").read_text()
    assert "def sub" not in original


def test_run_patch_in_sandbox_cleans_up_worktree_after_run(git_fixture_repo):
    patch_text = _make_patch(git_fixture_repo)
    patch_hash = sandbox.hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    head = sandbox.current_head(git_fixture_repo)

    sandbox.run_patch_in_sandbox(
        patch_text, patch_hash, head, repo_root=git_fixture_repo, runner="host-test"
    )

    listing = subprocess.run(
        ["git", "worktree", "list"], cwd=git_fixture_repo, capture_output=True, text=True, check=True
    ).stdout
    assert "verify-" not in listing


def test_run_patch_in_sandbox_rejects_tampered_hash(git_fixture_repo):
    patch_text = _make_patch(git_fixture_repo)
    wrong_hash = "0" * 64
    head = sandbox.current_head(git_fixture_repo)

    with pytest.raises(sandbox.SandboxError, match="does not match"):
        sandbox.run_patch_in_sandbox(
            patch_text, wrong_hash, head, repo_root=git_fixture_repo, runner="host-test"
        )


def test_run_patch_in_sandbox_rejects_patch_that_does_not_apply(git_fixture_repo):
    bogus_patch = (
        "diff --git a/backend/mod.py b/backend/mod.py\n"
        "index 0000000..1111111 100644\n"
        "--- a/backend/mod.py\n"
        "+++ b/backend/mod.py\n"
        "@@ -100,1 +100,1 @@\n"
        "-this line does not exist\n"
        "+neither does this\n"
    )
    patch_hash = sandbox.hashlib.sha256(bogus_patch.encode("utf-8")).hexdigest()
    head = sandbox.current_head(git_fixture_repo)

    with pytest.raises(sandbox.SandboxError, match="does not apply cleanly"):
        sandbox.run_patch_in_sandbox(
            bogus_patch, patch_hash, head, repo_root=git_fixture_repo, runner="host-test"
        )


def test_deploy_to_local_branch_never_touches_primary_branch(git_fixture_repo):
    patch_text = _make_patch(git_fixture_repo)
    patch_hash = sandbox.hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    head = sandbox.current_head(git_fixture_repo)

    result = sandbox.deploy_to_local_branch(
        "proposal-xyz", 1, patch_text, patch_hash, head, repo_root=git_fixture_repo
    )

    assert result.branch_name == "echo/self-modification/proposal-xyz/1"
    # Primary working tree is still on its original branch/commit.
    assert sandbox.current_head(git_fixture_repo) == head
    status = subprocess.run(
        ["git", "status", "--short"], cwd=git_fixture_repo, capture_output=True, text=True, check=True
    ).stdout
    # The only allowed noise is the untracked sandbox scratch directory itself
    # (the real repo's .gitignore excludes it; this throwaway fixture repo has
    # no .gitignore at all) — no *tracked* file may show as modified.
    tracked_changes = [line for line in status.splitlines() if ".self_mod_sandboxes" not in line]
    assert tracked_changes == []

    branches = subprocess.run(
        ["git", "branch"], cwd=git_fixture_repo, capture_output=True, text=True, check=True
    ).stdout
    assert "echo/self-modification/proposal-xyz/1" in branches

    sandbox.rollback_local_branch(result.worktree_path, result.branch_name, repo_root=git_fixture_repo)
    branches_after = subprocess.run(
        ["git", "branch"], cwd=git_fixture_repo, capture_output=True, text=True, check=True
    ).stdout
    assert "echo/self-modification/proposal-xyz/1" not in branches_after
    assert sandbox.current_head(git_fixture_repo) == head


def test_deploy_refuses_to_redeploy_existing_branch(git_fixture_repo):
    patch_text = _make_patch(git_fixture_repo)
    patch_hash = sandbox.hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    head = sandbox.current_head(git_fixture_repo)

    sandbox.deploy_to_local_branch("proposal-dup", 1, patch_text, patch_hash, head, repo_root=git_fixture_repo)
    with pytest.raises(sandbox.SandboxError, match="already exists"):
        sandbox.deploy_to_local_branch("proposal-dup", 1, patch_text, patch_hash, head, repo_root=git_fixture_repo)


def test_rollback_is_safe_to_call_when_nothing_to_remove(git_fixture_repo):
    # Should not raise even if the worktree path is already gone / branch
    # never existed — rollback is meant to be idempotent-safe.
    sandbox.rollback_local_branch(None, None, repo_root=git_fixture_repo)
    sandbox.rollback_local_branch(str(git_fixture_repo / "nonexistent"), "no-such-branch", repo_root=git_fixture_repo)


def test_docker_runner_uses_fixed_network_and_resource_boundary(tmp_path, monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

    monkeypatch.setattr(sandbox.shutil, "which", lambda _name: "C:/docker.exe")
    monkeypatch.setattr(sandbox.subprocess, "run", fake_run)

    result = sandbox._run_docker_check(tmp_path, "backend-ruff", "echo-selfmod-sandbox:local")

    assert result.status == "passed"
    argv = captured["argv"]
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv
    assert "--cap-drop" in argv and argv[argv.index("--cap-drop") + 1] == "ALL"
    assert "--pids-limit" in argv and "--memory" in argv and "--cpus" in argv
    assert sum(item == "--mount" for item in argv) == 1
    assert captured["kwargs"]["env"] == {}


def test_docker_runner_rejects_non_allowlisted_command(tmp_path):
    with pytest.raises(sandbox.SandboxError, match="not allowlisted"):
        sandbox._run_docker_check(tmp_path, "sh -c whoami", "echo-selfmod-sandbox:local")


def test_runner_environment_contains_no_host_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-leak")
    environment = selfmod_runner._safe_environment()
    assert "OPENAI_API_KEY" not in environment
    assert not any("TOKEN" in key or "SECRET" in key or "PASSWORD" in key for key in environment)


def test_exact_diff_check_rejects_unexpected_tracked_change(git_fixture_repo):
    patch_text = _make_patch(git_fixture_repo)
    patch_hash = sandbox.hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    head = sandbox.current_head(git_fixture_repo)
    workspace = sandbox._create_worktree("unexpected-change", head, repo_root=git_fixture_repo)
    try:
        sandbox._apply_patch(workspace, patch_text, patch_hash)
        target = workspace / "backend" / "mod.py"
        target.write_text(target.read_text(encoding="utf-8") + "\n# unapproved\n", encoding="utf-8")
        with pytest.raises(sandbox.SandboxError, match="does not exactly match"):
            sandbox._assert_exact_working_diff(workspace, patch_text, patch_hash)
    finally:
        sandbox._remove_worktree(workspace, repo_root=git_fixture_repo)
