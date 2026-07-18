"""Fixed command dispatcher baked into Echo's self-modification sandbox image.

The host passes one symbolic check name. No arbitrary command, shell fragment,
path, environment value, or network target can be supplied through this entry
point. The container itself is started with networking disabled and only the
disposable worktree mounted at /workspace.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path("/workspace")
BACKEND = WORKSPACE / "backend"
FRONTEND = WORKSPACE / "frontend"
IMAGE_NODE_MODULES = Path("/opt/frontend/node_modules")

COMMANDS: dict[str, tuple[Path, list[str]]] = {
    "backend-pytest": (
        BACKEND,
        [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q"],
    ),
    "backend-ruff": (
        BACKEND,
        [sys.executable, "-m", "ruff", "check", "app", "tests"],
    ),
    "frontend-typecheck": (
        FRONTEND,
        ["npm", "run", "typecheck"],
    ),
    "frontend-build": (
        FRONTEND,
        ["npm", "run", "build"],
    ),
}


def _safe_environment() -> dict[str, str]:
    # Construct from constants instead of inheriting Docker/host values. Vite
    # therefore cannot receive a VITE_* secret and tests cannot see provider
    # credentials through os.environ.
    return {
        "PATH": "/opt/venv/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp/home",
        "TMPDIR": "/tmp",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
        "CI": "true",
        "NO_COLOR": "1",
    }


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        print("Unknown or missing allowlisted check name.", file=sys.stderr)
        return 64
    if not WORKSPACE.is_dir():
        print("Disposable workspace mount is missing.", file=sys.stderr)
        return 72

    check_name = sys.argv[1]
    cwd, argv = COMMANDS[check_name]
    if not cwd.is_dir():
        print(f"Required project directory is missing for {check_name}.", file=sys.stderr)
        return 72

    node_modules = FRONTEND / "node_modules"
    created_link = False
    if check_name.startswith("frontend-"):
        if node_modules.exists() or node_modules.is_symlink():
            print("Unexpected frontend/node_modules exists in the disposable worktree.", file=sys.stderr)
            return 73
        os.symlink(IMAGE_NODE_MODULES, node_modules, target_is_directory=True)
        created_link = True

    try:
        completed = subprocess.run(argv, cwd=cwd, env=_safe_environment(), check=False)
        return completed.returncode
    finally:
        if created_link:
            node_modules.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
