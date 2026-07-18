"""ECHO Layer 3A Part 2D — Self-Modification Sandbox.

Git-worktree plus Docker isolation for supervised self-modification. The
worktree isolates source state; the Docker runner is the security boundary
for executing repository code. It receives only the disposable worktree,
uses no host environment/secrets, has networking disabled, drops Linux
capabilities, and runs with bounded CPU/memory/process/time/output limits.

Every operation runs inside a dedicated `git worktree` created under
<repo_root>/.self_mod_sandboxes/ and NEVER checks out or mutates the
primary working tree's current branch, index, or uncommitted changes.
`git worktree add <path> <ref>` only materializes *committed* history at
<ref> into <path> — a dirty primary working tree (e.g. real in-progress
work sitting on master, as this repo very often has) is simply not visible
inside the sandbox at all. This is intentional and load-bearing, not
incidental.

Honest scope limits — see the architecture doc's threat model for the full
discussion:
  - Docker must be installed and the pinned local sandbox image must already
    exist. Runtime never downloads or builds it automatically.
  - A private Docker daemon or hostile image is outside this module's trust
    boundary. Sandbox execution fails closed if Docker/image checks fail.
  - "Deployment" always means committing to a *new* branch inside a *new*
    worktree, off a specific base ref — never the checked-out branch of the
    primary working tree, and never a push anywhere.

Every repo_root parameter defaults to the real repository but can be
overridden — tests use a throwaway `git init` fixture repo (same pattern as
test_self_improvement_verification.py) so the test suite never creates or
removes worktrees/branches in the actual ECHO repository.
"""

import hashlib
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import get_settings
from app.self_improvement_verify import REPO_ROOT, CheckResult, _now_iso, _truncate

_TIMEOUT_SECONDS = 600
_SANDBOX_DIRNAME = ".self_mod_sandboxes"
_IMAGE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,199}$")
_CHECKS = {
    "backend-pytest": "python -B -m pytest -p no:cacheprovider -q",
    "backend-ruff": "python -m ruff check app tests",
    "frontend-typecheck": "npm run typecheck",
    "frontend-build": "npm run build",
}


class SandboxError(Exception):
    """Raised for any sandbox setup/apply/teardown failure. Messages here
    are already safe to surface to a human reviewer (no secrets, no raw
    tracebacks) — see _truncate()'s use throughout."""


@dataclass(frozen=True)
class SandboxResult:
    passed: bool
    workspace_path: str
    base_commit: str
    checks: list[dict]
    summary: str
    baseline_passed: bool = False
    network_disabled: bool = True
    runner: str = "docker"


@dataclass(frozen=True)
class DeployResult:
    branch_name: str
    worktree_path: str


def _sandbox_root(repo_root: Path) -> Path:
    return repo_root / _SANDBOX_DIRNAME


def _git(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess:
    if shutil.which("git") is None:
        raise SandboxError("git is not installed / not on PATH")
    try:
        return subprocess.run(
            ["git", *argv], cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        raise SandboxError(f"git {' '.join(argv)} timed out after {_TIMEOUT_SECONDS}s") from exc


def current_head(repo_root: Path = REPO_ROOT) -> str:
    proc = _git(["rev-parse", "HEAD"], cwd=repo_root)
    if proc.returncode != 0:
        raise SandboxError(f"Could not resolve HEAD: {_truncate(proc.stderr)}")
    return proc.stdout.strip()


def _remove_worktree(path: Path, *, repo_root: Path) -> None:
    if not path.exists():
        _git(["worktree", "prune"], cwd=repo_root)
        return
    proc = _git(["worktree", "remove", "--force", str(path)], cwd=repo_root)
    if proc.returncode != 0:
        # Metadata may be stale (e.g. dir removed out-of-band) — prune
        # rather than leaving the repo's worktree list dirty.
        _git(["worktree", "prune"], cwd=repo_root)
        if path.exists():
            raise SandboxError("Sandbox worktree cleanup failed; execution is unsafe to continue.")


def _create_worktree(
    name: str, base_ref: str, *, repo_root: Path, new_branch: str | None = None
) -> Path:
    sandbox_root = _sandbox_root(repo_root)
    sandbox_root.mkdir(parents=True, exist_ok=True)
    path = sandbox_root / name
    if path.exists():
        _remove_worktree(path, repo_root=repo_root)
    argv = ["worktree", "add"]
    if new_branch:
        argv += ["-b", new_branch, str(path), base_ref]
    else:
        argv += ["--detach", str(path), base_ref]
    proc = _git(argv, cwd=repo_root)
    if proc.returncode != 0:
        raise SandboxError(f"git worktree add failed: {_truncate(proc.stderr)}")
    return path


def _apply_patch(workspace: Path, patch_text: str, patch_hash: str) -> None:
    """Recomputes the patch hash before applying — refuses a patch whose
    content doesn't match what was reviewed/approved (tampering or a stale
    reference). Uses `git apply --check` first so a bad patch never
    partially applies."""
    recomputed = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()
    if recomputed != patch_hash:
        raise SandboxError(
            "Patch content does not match its recorded hash — refusing to apply a tampered or stale patch."
        )
    patch_file = workspace / ".self_mod_patch.diff"
    patch_file.write_text(patch_text, encoding="utf-8")
    try:
        check = subprocess.run(
            ["git", "apply", "--check", str(patch_file)],
            cwd=workspace, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
        )
        if check.returncode != 0:
            raise SandboxError(f"Patch does not apply cleanly: {_truncate(check.stderr)}")
        apply_proc = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=workspace, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
        )
        if apply_proc.returncode != 0:
            raise SandboxError(f"git apply failed after passing --check: {_truncate(apply_proc.stderr)}")
    finally:
        patch_file.unlink(missing_ok=True)


def _docker_image_available(image: str) -> bool:
    if not _IMAGE_RE.fullmatch(image) or shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def get_sandbox_capabilities(image: str | None = None) -> dict:
    selected = image or get_settings().self_modification_sandbox_image
    available = _docker_image_available(selected)
    return {
        "runner": "docker",
        "image": selected,
        "available": available,
        "network_isolation_enforced": available,
        "host_environment_forwarded": False,
        "workspace_only_mount": True,
    }


def _check_result(command: str, proc: subprocess.CompletedProcess | None, error: str | None = None) -> CheckResult:
    if proc is None:
        return CheckResult(command, "failed", None, "", error or "Sandbox command failed.", _now_iso())
    return CheckResult(
        command=command,
        status="passed" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode,
        stdout_summary=_truncate(proc.stdout),
        stderr_summary=_truncate(proc.stderr),
        timestamp=_now_iso(),
    )


def _run_docker_check(workspace: Path, check_name: str, image: str) -> CheckResult:
    if check_name not in _CHECKS:
        raise SandboxError(f"Sandbox check '{check_name}' is not allowlisted.")
    # No shell is involved and no caller-provided argv reaches the container.
    # Docker gets a single read/write mount: the disposable worktree.
    docker = shutil.which("docker")
    if docker is None:
        return _check_result(_CHECKS[check_name], None, "Docker is unavailable.")
    argv = [
        docker, "run", "--rm",
        "--network", "none",
        "--read-only",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--pids-limit", "256",
        "--memory", "2g",
        "--cpus", "2",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=512m",
        "--mount", f"type=bind,src={workspace.resolve()},dst=/workspace",
        "--workdir", "/workspace",
        "--env", "HOME=/tmp/home",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        image,
        check_name,
    ]
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            env={},
        )
    except subprocess.TimeoutExpired:
        return _check_result(_CHECKS[check_name], None, f"Command timed out after {_TIMEOUT_SECONDS}s")
    except OSError:
        return _check_result(_CHECKS[check_name], None, "Docker could not start the sandbox command.")
    return _check_result(_CHECKS[check_name], proc)


def _run_host_test_check(workspace: Path, check_name: str) -> CheckResult:
    """Test-fixture-only runner; production governance never selects it."""
    from app.self_improvement_verify import _run

    backend = workspace / "backend" if (workspace / "backend").is_dir() else workspace
    if check_name == "backend-pytest":
        return _run([sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q"], cwd=backend, display=_CHECKS[check_name])
    if check_name == "backend-ruff":
        return _run([sys.executable, "-m", "ruff", "check", "."], cwd=backend, display=_CHECKS[check_name])
    raise SandboxError("The host-test runner supports backend fixture checks only.")


def _required_checks(changed_paths: list[str] | None) -> list[str]:
    paths = changed_paths or []
    checks = ["backend-pytest", "backend-ruff"]
    if any(path.replace("\\", "/").casefold().startswith("frontend/") for path in paths):
        checks.extend(["frontend-typecheck", "frontend-build"])
    return checks


def _working_diff(workspace: Path) -> str:
    # Intent-to-add makes newly-created files visible to git diff without
    # staging their content or changing the primary repository index.
    add_intent = _git(["add", "-N", "."], cwd=workspace)
    if add_intent.returncode != 0:
        raise SandboxError(f"Could not prepare patch-integrity comparison: {_truncate(add_intent.stderr)}")
    diff = _git(["diff", "--binary", "--no-ext-diff"], cwd=workspace)
    if diff.returncode != 0:
        raise SandboxError(f"Could not verify resulting sandbox diff: {_truncate(diff.stderr)}")
    return diff.stdout


def _assert_exact_working_diff(workspace: Path, patch_text: str, patch_hash: str) -> None:
    actual = _working_diff(workspace).replace("\r\n", "\n")
    expected = patch_text.replace("\r\n", "\n")
    if hashlib.sha256(actual.encode("utf-8")).hexdigest() != hashlib.sha256(expected.encode("utf-8")).hexdigest():
        raise SandboxError(
            "The sandbox working-tree diff does not exactly match the approved patch; unexpected changes were detected."
        )


def run_patch_in_sandbox(
    patch_text: str,
    patch_hash: str,
    base_commit: str | None,
    *,
    repo_root: Path = REPO_ROOT,
    changed_paths: list[str] | None = None,
    runner: str = "docker",
    runner_image: str | None = None,
) -> SandboxResult:
    """Creates an isolated worktree off base_commit (or current HEAD if
    None), hash-verifies and applies the exact patch, then runs the same
    restricted, no-autofix, allowlisted commands self_improvement_verify.py
    already uses — scoped to the sandbox's own backend/ directory. The
    workspace is torn down immediately after; full per-check output is
    captured in the returned result before teardown, so nothing is lost —
    this app has no async job queue to keep a sandbox alive for browsing."""
    image = runner_image or get_settings().self_modification_sandbox_image
    if runner == "docker" and not _docker_image_available(image):
        raise SandboxError(
            "The local Docker sandbox image is unavailable. Build it explicitly before enabling sandbox execution."
        )
    if runner not in {"docker", "host-test"}:
        raise SandboxError("Unsupported sandbox runner.")

    base_ref = base_commit or current_head(repo_root)
    name = f"verify-{patch_hash[:12]}"
    workspace = _create_worktree(name, base_ref, repo_root=repo_root)
    try:
        check_names = _required_checks(changed_paths)
        run_check = (
            (lambda check: _run_docker_check(workspace, check, image))
            if runner == "docker"
            else (lambda check: _run_host_test_check(workspace, check))
        )
        baseline = [asdict(run_check(check)) | {"phase": "baseline"} for check in check_names]
        baseline_passed = bool(baseline) and all(check["status"] == "passed" for check in baseline)

        _apply_patch(workspace, patch_text, patch_hash)
        _assert_exact_working_diff(workspace, patch_text, patch_hash)
        post = [asdict(run_check(check)) | {"phase": "patched"} for check in check_names]
        _assert_exact_working_diff(workspace, patch_text, patch_hash)

        checks_dicts = baseline + post
        post_passed = bool(post) and all(check["status"] == "passed" for check in post)
        passed = baseline_passed and post_passed
        summary = (
            f"Baseline {sum(c['status'] == 'passed' for c in baseline)}/{len(baseline)}; "
            f"patched {sum(c['status'] == 'passed' for c in post)}/{len(post)} allowlisted checks passed."
        )
        return SandboxResult(
            passed=passed, workspace_path=str(workspace), base_commit=base_ref,
            checks=checks_dicts, summary=summary, baseline_passed=baseline_passed,
            network_disabled=(runner == "docker"), runner=runner,
        )
    finally:
        _remove_worktree(workspace, repo_root=repo_root)


def deploy_to_local_branch(
    proposal_id: str,
    revision_number: int,
    patch_text: str,
    patch_hash: str,
    base_commit: str | None,
    *,
    repo_root: Path = REPO_ROOT,
) -> DeployResult:
    """Commits the exact, hash-verified patch to a brand-new
    `echo/self-modification/<proposal-id>/<revision-number>` branch inside
    its own worktree, off base_commit. Never checks out or modifies the
    primary working tree's branch. The worktree+branch are the deployment
    artifact and are deliberately left in place — rollback_local_branch()
    is what tears them down."""
    base_ref = base_commit or current_head(repo_root)
    branch_name = f"echo/self-modification/{proposal_id}/{revision_number}"

    existing = _git(["branch", "--list", branch_name], cwd=repo_root)
    if existing.stdout.strip():
        raise SandboxError(
            f"Branch '{branch_name}' already exists — this revision may already be deployed."
        )

    name = f"deploy-{patch_hash[:12]}"
    workspace = _create_worktree(name, base_ref, repo_root=repo_root, new_branch=branch_name)
    try:
        _apply_patch(workspace, patch_text, patch_hash)
        add_proc = subprocess.run(
            ["git", "add", "-A"], cwd=workspace, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
        )
        if add_proc.returncode != 0:
            raise SandboxError(f"git add failed: {_truncate(add_proc.stderr)}")
        commit_message = (
            f"self-modification: apply revision {revision_number} of proposal {proposal_id}\n\n"
            "Applied by ECHO's supervised self-modification workflow after sandbox "
            "verification and explicit human approval. See SelfModificationAuditEvent "
            "rows for the full trail. This branch was never merged automatically."
        )
        commit_proc = subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=workspace, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
        )
        if commit_proc.returncode != 0:
            raise SandboxError(f"git commit failed: {_truncate(commit_proc.stderr)}")
    except SandboxError:
        _remove_worktree(workspace, repo_root=repo_root)
        _git(["branch", "-D", branch_name], cwd=repo_root)
        raise
    return DeployResult(branch_name=branch_name, worktree_path=str(workspace))


def rollback_local_branch(
    worktree_path: str | None,
    branch_name: str | None,
    *,
    repo_root: Path = REPO_ROOT,
) -> None:
    """Discards the deployment worktree and deletes its branch. Safe and
    complete by construction: nothing was ever merged into an existing
    branch, so there is nothing else to undo."""
    if worktree_path:
        _remove_worktree(Path(worktree_path), repo_root=repo_root)
    if branch_name:
        proc = _git(["branch", "-D", branch_name], cwd=repo_root)
        if proc.returncode != 0 and "not found" not in proc.stderr.lower():
            raise SandboxError(f"Could not delete branch '{branch_name}': {_truncate(proc.stderr)}")
