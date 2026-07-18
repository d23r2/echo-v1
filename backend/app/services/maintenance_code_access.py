"""ECHO Supervised Maintenance Workspace v1 — CodeAccessService.

Read-only, policy-gated access to the one owner-approved repository. Every
operation passes the full containment pipeline
(docs/supervised_maintenance/architecture.md §6) before any file content is
returned: canonicalization, repository-root containment, symlink/junction
resolution, approved-scope check, secret-filename check, file-type/size
check, and secret-content scan. There is no arbitrary file-read endpoint —
every path in this module goes through `_validate_and_resolve()`.

Search/symbol lookup here is a bounded plain-text scan, not an AST index —
an honestly-stated limitation (see threat_model.md and protected_scope.md).
"""

import hashlib
import logging
import re
import stat as stat_module
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.models import ApprovedRepository
from app.services.self_modification_governance import _LIKELY_SECRET_PATTERNS, _canonical_path

logger = logging.getLogger(__name__)

_MAX_LIST_ENTRIES = 500
_BINARY_SNIFF_BYTES = 8192
_GIT_TIMEOUT_SECONDS = 30

# .env.example and similarly-named templates are explicitly allowed even
# though they'd otherwise match the .env* pattern below.
_ALLOWED_TEMPLATE_EXCEPTIONS = frozenset({".env.example", ".env.sample", ".env.template"})

_SECRET_FILENAME_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^\.env(\..+)?$",
        r".*\.pem$",
        r".*\.key$",
        r".*\.p12$",
        r".*\.pfx$",
        r"^credentials\..+$",
        r"^secrets\..+$",
        r"^id_rsa(\..+)?$",
        r"^id_ed25519(\..+)?$",
        r"^id_ecdsa(\..+)?$",
        r"^id_dsa(\..+)?$",
        r".*\.db$",
        r".*\.sqlite3?$",
    )
)


class CodeAccessError(Exception):
    """Base class. Every message here is always safe to display to a human
    or return to the model — never includes matched secret content or raw
    exception text."""


class CodeAccessPermissionError(CodeAccessError):
    pass


class CodeAccessRejectedError(CodeAccessError):
    """A path or content failed the containment/secret pipeline."""


@dataclass(frozen=True)
class FileEntry:
    path: str
    size_bytes: int
    is_directory: bool


@dataclass(frozen=True)
class FileContent:
    path: str
    content: str
    sha256: str


@dataclass(frozen=True)
class SearchHit:
    path: str
    line: int
    text: str


_ACTIVE_MODES = frozenset({"analyse_only", "propose_only", "sandbox_verify", "human_approved_local_commit"})


def _check_mode(repository: ApprovedRepository) -> None:
    settings = get_settings()
    if not settings.supervised_maintenance_enabled or not settings.supervised_analysis_enabled:
        raise CodeAccessPermissionError(
            "Supervised Maintenance analysis is disabled (SUPERVISED_MAINTENANCE_ENABLED / "
            "SUPERVISED_ANALYSIS_ENABLED)."
        )
    if not repository.enabled:
        raise CodeAccessPermissionError("This repository is disabled.")
    if repository.capability_mode not in _ACTIVE_MODES:
        raise CodeAccessPermissionError(
            f"This repository's capability mode is '{repository.capability_mode}' — "
            "read access requires at least analyse_only."
        )


def _repo_root(repository: ApprovedRepository) -> Path:
    return Path(repository.root_path_reference)


def _in_scope(repository: ApprovedRepository, canonical: str, *, for_write: bool) -> bool:
    scope = repository.permitted_proposal_paths if for_write else repository.permitted_read_paths
    for entry in scope:
        pattern = entry.casefold()
        if pattern.startswith("*"):
            if canonical.endswith(pattern[1:]):
                return True
        elif pattern.endswith("/"):
            # A directory prefix also matches the bare directory itself
            # (no trailing slash) — e.g. pattern "backend/tests/" must
            # match both "backend/tests/foo.py" and a listing request for
            # "backend/tests" itself.
            if canonical == pattern.rstrip("/") or canonical.startswith(pattern):
                return True
        elif canonical == pattern:
            # Exact-file patterns (e.g. "backend/requirements.txt") match
            # only themselves, never as a directory prefix.
            return True
    return False


def _validate_and_resolve(repository: ApprovedRepository, relative_path: str, *, for_write: bool = False) -> Path:
    """The full containment pipeline. Raises CodeAccessRejectedError with a
    safe, specific reason on any failure."""
    if not relative_path or "\x00" in relative_path:
        raise CodeAccessRejectedError("Empty or invalid path.")
    candidate = relative_path.strip().replace("\\", "/")
    if candidate.startswith("/"):
        raise CodeAccessRejectedError("Absolute paths are not permitted.")
    if re.match(r"^[A-Za-z]:", candidate):
        raise CodeAccessRejectedError("Absolute (drive-letter) paths are not permitted.")
    if ".." in candidate.split("/"):
        raise CodeAccessRejectedError("Path traversal ('..') is not permitted.")
    if ":" in candidate:
        # NTFS Alternate Data Stream syntax ("file.txt:hidden_stream"). A
        # colon can never appear in a legitimate relative path component on
        # any platform this app targets, so this is an unconditional reject
        # rather than an attempt to allowlist safe colon usage.
        raise CodeAccessRejectedError("Alternate data stream syntax is not permitted.")

    root = _repo_root(repository).resolve()
    unresolved = root / candidate
    try:
        resolved = unresolved.resolve(strict=False)
    except OSError as exc:
        raise CodeAccessRejectedError("Path could not be resolved.") from exc

    # Symlink / Windows-junction escape: the fully resolved path must still
    # sit inside the repository root. Path.resolve() follows both symlinks
    # and junctions, so this single check catches either escape mechanism.
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise CodeAccessRejectedError("Path resolves outside the approved repository root.") from exc

    canonical = _canonical_path(candidate)
    if not _in_scope(repository, canonical, for_write=for_write):
        raise CodeAccessRejectedError(f"'{relative_path}' is outside this repository's approved scope.")

    filename = resolved.name
    if filename not in _ALLOWED_TEMPLATE_EXCEPTIONS and any(p.match(filename) for p in _SECRET_FILENAME_PATTERNS):
        raise CodeAccessRejectedError("This file matches a blocked secret-file pattern and cannot be accessed.")

    return resolved


def list_repository_files(repository: ApprovedRepository, subpath: str = "") -> list[FileEntry]:
    _check_mode(repository)
    root = _repo_root(repository).resolve()
    base = _validate_and_resolve(repository, subpath) if subpath else root
    if not base.is_dir():
        raise CodeAccessRejectedError("Not a directory.")
    entries: list[FileEntry] = []
    for child in sorted(base.iterdir())[:_MAX_LIST_ENTRIES]:
        rel = str(child.relative_to(root)).replace("\\", "/")
        try:
            _validate_and_resolve(repository, rel if not child.is_dir() else rel + "/.")
        except CodeAccessRejectedError:
            # Silently omit out-of-scope/secret/unsafe entries from a
            # listing rather than failing the whole directory — a listing
            # is not a promise every visible name is individually readable.
            if not child.is_dir():
                continue
        entries.append(
            FileEntry(path=rel, size_bytes=child.stat().st_size if child.is_file() else 0, is_directory=child.is_dir())
        )
    return entries


def read_repository_file(repository: ApprovedRepository, relative_path: str) -> FileContent:
    _check_mode(repository)
    resolved = _validate_and_resolve(repository, relative_path)
    if not resolved.exists():
        raise CodeAccessRejectedError("File not found.")
    st = resolved.stat()
    if not stat_module.S_ISREG(st.st_mode):
        raise CodeAccessRejectedError("Not a regular file (device/pipe/socket/directory paths are rejected).")
    limit = get_settings().supervised_maintenance_max_read_bytes
    if st.st_size > limit:
        raise CodeAccessRejectedError(f"File exceeds the {limit}-byte read limit.")
    raw = resolved.read_bytes()
    if b"\x00" in raw[:_BINARY_SNIFF_BYTES]:
        raise CodeAccessRejectedError("Binary files are not readable by default.")
    text = raw.decode("utf-8", errors="replace")
    if any(pattern.search(text) for pattern in _LIKELY_SECRET_PATTERNS):
        raise CodeAccessRejectedError("This file's content matches a secret-shaped pattern and cannot be returned.")
    return FileContent(path=relative_path, content=text, sha256=hashlib.sha256(raw).hexdigest())


def calculate_file_hash(repository: ApprovedRepository, relative_path: str) -> str:
    return read_repository_file(repository, relative_path).sha256


def search_repository_text(
    repository: ApprovedRepository, query: str, *, subpath: str = "", max_results: int = 50
) -> list[SearchHit]:
    """A bounded plain-text scan across approved files — not an index, not
    an AST search. Every candidate file still goes through the full
    read_repository_file() pipeline, so a match can never surface a
    secret-shaped or out-of-scope file's content."""
    _check_mode(repository)
    if not query or len(query) < 2:
        raise CodeAccessRejectedError("Query must be at least 2 characters.")
    root = _repo_root(repository).resolve()
    base = _validate_and_resolve(repository, subpath) if subpath else root
    results: list[SearchHit] = []
    scanned = 0
    for path in sorted(base.rglob("*")):
        if scanned >= _MAX_LIST_ENTRIES or len(results) >= max_results:
            break
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            content = read_repository_file(repository, rel)
        except CodeAccessRejectedError:
            continue
        scanned += 1
        for line_number, line in enumerate(content.content.splitlines(), start=1):
            if query in line:
                results.append(SearchHit(path=rel, line=line_number, text=line.strip()[:300]))
                if len(results) >= max_results:
                    break
    return results


def locate_symbol(repository: ApprovedRepository, symbol: str, *, subpath: str = "") -> list[SearchHit]:
    """Text-search based, not AST-based — see the module docstring's honest
    limitation note. Good enough to point a human at candidate definitions;
    not a substitute for a real language server."""
    return search_repository_text(repository, symbol, subpath=subpath)


def find_symbol_references(repository: ApprovedRepository, symbol: str, *, subpath: str = "") -> list[SearchHit]:
    return search_repository_text(repository, symbol, subpath=subpath, max_results=200)


def inspect_dependency_manifest(repository: ApprovedRepository) -> list[FileContent]:
    candidates = ["backend/requirements.txt", "frontend/package.json", "frontend/package-lock.json"]
    results = []
    for candidate in candidates:
        try:
            results.append(read_repository_file(repository, candidate))
        except CodeAccessRejectedError:
            continue
    return results


def inspect_test_files(repository: ApprovedRepository, subpath: str = "backend/tests") -> list[FileEntry]:
    return list_repository_files(repository, subpath)


def inspect_documentation(repository: ApprovedRepository, subpath: str = "docs") -> list[FileEntry]:
    return list_repository_files(repository, subpath)


def _run_git_readonly(repository: ApprovedRepository, argv: list[str]) -> str:
    """Only ever called with a hardcoded, read-only argv from this module —
    never with caller-supplied arguments — matching the "no unrestricted
    shell" requirement (this is CommandPolicy applied to Git specifically)."""
    _check_mode(repository)
    root = _repo_root(repository).resolve()
    try:
        proc = subprocess.run(
            ["git", *argv], cwd=root, capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeAccessRejectedError("Git command could not run.") from exc
    if proc.returncode != 0:
        raise CodeAccessRejectedError("Git command failed.")
    return proc.stdout


def inspect_git_status(repository: ApprovedRepository) -> str:
    return _run_git_readonly(repository, ["status", "--short"])


def inspect_git_diff(repository: ApprovedRepository, *, staged: bool = False) -> str:
    argv = ["diff", "--stat"] + (["--cached"] if staged else [])
    return _run_git_readonly(repository, argv)


def inspect_git_commit(repository: ApprovedRepository, commit_ref: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{7,40}|HEAD", commit_ref):
        raise CodeAccessRejectedError("Invalid commit reference format.")
    return _run_git_readonly(repository, ["show", "--stat", commit_ref])


def calculate_repository_snapshot(repository: ApprovedRepository) -> str:
    return _run_git_readonly(repository, ["rev-parse", "HEAD"]).strip()
