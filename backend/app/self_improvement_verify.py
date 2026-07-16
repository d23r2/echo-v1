"""Local, read-only verification checks for founder-approved self-improvement
requests. Runs git/pytest/ruff/mypy against the current working tree and reports
what happened — it never edits files, applies patches, or restarts the app."""

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


def _resolve_repo_root() -> Path:
    """Local dev: this file lives at <repo>/backend/app/…, so the repo root is
    two levels up and contains a backend/ subdirectory. Docker: the image only
    ships app/ at WORKDIR /app (see backend/Dockerfile) — there's no wrapping
    backend/ directory or wider repo at all, so treat that as its own root."""
    app_parent = Path(__file__).resolve().parent.parent
    candidate = app_parent.parent
    if (candidate / "backend").is_dir():
        return candidate
    return app_parent


def _resolve_backend_dir(repo_root: Path) -> Path:
    candidate = repo_root / "backend"
    return candidate if candidate.is_dir() else repo_root


REPO_ROOT = _resolve_repo_root()
BACKEND_DIR = _resolve_backend_dir(REPO_ROOT)
_MAX_OUTPUT_CHARS = 2000
_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class CheckResult:
    command: str
    status: str  # "passed" | "failed" | "unavailable"
    exit_code: int | None
    stdout_summary: str
    stderr_summary: str
    timestamp: str


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _truncate(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… truncated ({len(text) - limit} more chars)"


def _run(argv: list[str], *, cwd: Path, display: str | None = None) -> CheckResult:
    command_str = display or " ".join(argv)
    try:
        proc = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except FileNotFoundError:
        return CheckResult(
            command=command_str,
            status="unavailable",
            exit_code=None,
            stdout_summary="",
            stderr_summary=f"{argv[0]} is not installed / not on PATH",
            timestamp=_now_iso(),
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            command=command_str,
            status="failed",
            exit_code=None,
            stdout_summary="",
            stderr_summary=f"Command timed out after {_TIMEOUT_SECONDS}s",
            timestamp=_now_iso(),
        )
    return CheckResult(
        command=command_str,
        status="passed" if proc.returncode == 0 else "failed",
        exit_code=proc.returncode,
        stdout_summary=_truncate(proc.stdout),
        stderr_summary=_truncate(proc.stderr),
        timestamp=_now_iso(),
    )


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _unavailable(command: str, reason: str) -> CheckResult:
    return CheckResult(
        command=command,
        status="unavailable",
        exit_code=None,
        stdout_summary="",
        stderr_summary=reason,
        timestamp=_now_iso(),
    )


def run_verification(
    *, repo_root: Path | None = None, backend_dir: Path | None = None
) -> list[dict]:
    """Run local checks against the current working tree and return their results
    as plain dicts, in the order they were run. Never raises — a missing tool
    (git/pytest/ruff/mypy) becomes an "unavailable" result, not a crash."""
    root = repo_root or REPO_ROOT
    backend = backend_dir or BACKEND_DIR
    checks: list[CheckResult] = []

    if shutil.which("git") is None:
        checks.append(_unavailable("git status --short", "git is not installed / not on PATH"))
        checks.append(_unavailable("git diff --stat", "git is not installed / not on PATH"))
    elif not (root / ".git").exists():
        # E.g. the production Docker image only ships app/, not the repo's git
        # history — that's an environment limitation, not something "failing".
        reason = f"{root} is not a git repository in this environment"
        checks.append(_unavailable("git status --short", reason))
        checks.append(_unavailable("git diff --stat", reason))
    else:
        checks.append(_run(["git", "status", "--short"], cwd=root))
        checks.append(_run(["git", "diff", "--stat"], cwd=root))

    if _module_available("pytest"):
        checks.append(_run([sys.executable, "-m", "pytest", "-q"], cwd=backend, display="pytest -q"))
    else:
        checks.append(_unavailable("pytest -q", "pytest is not installed in this environment"))

    if _module_available("ruff"):
        checks.append(_run([sys.executable, "-m", "ruff", "check", "."], cwd=backend, display="ruff check ."))
    else:
        checks.append(_unavailable("ruff check .", "ruff is not installed — skipped (optional tool)"))

    if _module_available("mypy"):
        checks.append(_run([sys.executable, "-m", "mypy", "app"], cwd=backend, display="mypy app"))
    else:
        checks.append(_unavailable("mypy app", "mypy is not installed — skipped (optional tool)"))

    return [asdict(c) for c in checks]


def summarize(checks: list[dict]) -> tuple[str, str]:
    """Roll per-check results up into an overall status + human-readable note.
    Unavailable tools are informational and never fail the run — only checks that
    actually executed and returned a non-zero exit code count against it."""
    ran = [c for c in checks if c["status"] != "unavailable"]
    failed = [c for c in ran if c["status"] == "failed"]
    unavailable = [c for c in checks if c["status"] == "unavailable"]

    if not ran:
        return "failed", "No checks could run — see individual results."

    status = "failed" if failed else "passed"

    parts = [f"{len(ran) - len(failed)}/{len(ran)} runnable checks passed"]
    if failed:
        parts.append("failed: " + ", ".join(c["command"] for c in failed))
    if unavailable:
        parts.append("unavailable: " + ", ".join(c["command"] for c in unavailable))
    return status, "; ".join(parts) + "."
