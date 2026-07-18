"""ECHO Action + Reliability Core v1 — Safety and Permission Center.

Single shared local-device policy (no multi-user auth in this milestone —
see CLAUDE.md/the milestone spec's explicit exclusion). Every permission_key
below is checked by both action_system.py and tool_registry.py before a
side-effecting action/tool is allowed to run at all.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import PermissionSetting

# key -> (default level, description, risk_level). Levels: allowed | ask_first | disabled.
DEFAULT_PERMISSIONS: list[dict] = [
    {
        "key": "memory_write",
        "level": "ask_first",
        "risk_level": "medium",
        "description": "Saving a new Atlas memory candidate. Matches the existing memory-candidate review flow — nothing is ever written to Atlas directly.",
    },
    {
        "key": "action_create_task",
        "level": "allowed",
        "risk_level": "low",
        "description": "Creating a new task via chat or the Action Center.",
    },
    {
        "key": "action_update_task",
        "level": "ask_first",
        "risk_level": "low",
        "description": "Changing an existing task's status, due date, or details.",
    },
    {
        "key": "action_create_project",
        "level": "allowed",
        "risk_level": "low",
        "description": "Creating a new project via chat or the Action Center.",
    },
    {
        "key": "action_schedule_reminder",
        "level": "allowed",
        "risk_level": "low",
        "description": "Adding a reminder or schedule item.",
    },
    {
        "key": "web_search",
        "level": "allowed",
        "risk_level": "low",
        "description": "No-billing web search via SearXNG. Has no effect unless WEB_SEARCH_ENABLED is also configured — this only controls whether ECHO is allowed to use it when it is.",
    },
    {
        "key": "wiki_search",
        "level": "allowed",
        "risk_level": "low",
        "description": "Free Wikipedia lookups for background/stable facts.",
    },
    {
        "key": "rss_search",
        "level": "allowed",
        "risk_level": "low",
        "description": "Reading configured RSS feeds for current headlines.",
    },
    {
        "key": "cloud_api_use",
        "level": "disabled",
        "risk_level": "medium",
        "description": "Falling back to a paid/cloud model provider. Disabled by default — ECHO is local-first and this only matters if you've also configured a cloud API key and CLOUD_FALLBACK_ENABLED.",
    },
    {
        "key": "file_read",
        "level": "ask_first",
        "risk_level": "medium",
        "description": "Reading a Library file's contents for summarization or search.",
    },
    {
        "key": "file_write",
        "level": "ask_first",
        "risk_level": "high",
        "description": "Writing or modifying a file on disk.",
    },
    {
        "key": "code_execution",
        "level": "ask_first",
        "risk_level": "high",
        "description": "Running a shell/build command. No action in this milestone actually executes code — this exists so a future one is safe by default.",
    },
    {
        "key": "release_build_commands",
        "level": "ask_first",
        "risk_level": "high",
        "description": "Recording or running release/build checks (pytest, npm build, APK/Tauri builds).",
    },
    {
        "key": "voice_input",
        "level": "allowed",
        "risk_level": "low",
        "description": "Using the browser's speech-to-text to fill the chat input. Runs entirely in your browser — no audio is ever sent to ECHO's backend.",
    },
    {
        "key": "voice_output",
        "level": "allowed",
        "risk_level": "low",
        "description": "Reading ECHO's replies aloud using the browser's built-in text-to-speech.",
    },
    {
        "key": "camera_input",
        "level": "ask_first",
        "risk_level": "medium",
        "description": "Using the device camera to capture an image for ECHO to look at. No image is stored or sent anywhere without a separate, explicit approval at capture time.",
    },
    {
        "key": "image_generation",
        "level": "disabled",
        "risk_level": "medium",
        "description": "Generating images. Only has an effect if an image provider is actually configured (see IMAGE_PROVIDER) — disabled by default since this often means a paid API.",
    },
    {
        "key": "delete_archive_data",
        "level": "ask_first",
        "risk_level": "destructive",
        "description": "Archiving or deleting a project, task, knowledge item, or memory. Always soft-archive, never a hard delete, regardless of this setting.",
    },
    {
        "key": "self_modification_propose",
        "level": "allowed",
        "risk_level": "low",
        "description": "Drafting a supervised self-modification proposal or submitting a patch revision for review. Creates database rows only — no file on disk is touched by this step.",
    },
    {
        "key": "self_modification_sandbox_run",
        "level": "ask_first",
        "risk_level": "high",
        "description": "Running a self-modification proposal's patch and verification checks inside an isolated git worktree sandbox. Also requires SELF_MODIFICATION_SANDBOX_ENABLED.",
    },
    {
        "key": "self_modification_approve",
        "level": "ask_first",
        "risk_level": "high",
        "description": "Recording an explicit simulated-human review decision for one exact patch hash. Approval wording is verified again by the self-modification governance service.",
    },
    {
        "key": "self_modification_deploy",
        "level": "disabled",
        "risk_level": "destructive",
        "description": "Applying an approved self-modification patch to an isolated local branch. Disabled by default — also requires SELF_MODIFICATION_DEPLOYMENT_ENABLED, which is off by default and out of scope for production deployment entirely.",
    },
    {
        "key": "self_modification_rollback",
        "level": "allowed",
        "risk_level": "high",
        "description": "Removing a self-modification deployment worktree and its isolated local branch. Remains available while the kill switch is active.",
    },
    {
        "key": "self_modification_kill_switch",
        "level": "ask_first",
        "risk_level": "destructive",
        "description": "Activating or resetting the self-modification emergency stop. Reset is Founder-only and requires a reason; role labels are simulated in this single-user app.",
    },
]

_DEFAULTS_BY_KEY = {p["key"]: p for p in DEFAULT_PERMISSIONS}


@dataclass(frozen=True)
class PermissionCheck:
    allowed: bool
    needs_confirmation: bool
    reason: str


def list_permissions(db: Session) -> list[PermissionSetting]:
    ensure_defaults(db)
    return db.query(PermissionSetting).order_by(PermissionSetting.permission_key).all()


def ensure_defaults(db: Session) -> None:
    """Idempotent — db.py's init_db() already seeds these at startup, but
    tests that build a fresh in-memory DB per test call this directly."""
    existing = {p.permission_key for p in db.query(PermissionSetting).all()}
    for perm in DEFAULT_PERMISSIONS:
        if perm["key"] in existing:
            continue
        db.add(
            PermissionSetting(
                permission_key=perm["key"], level=perm["level"], description=perm["description"], risk_level=perm["risk_level"]
            )
        )
    db.commit()


def get_permission(db: Session, key: str) -> PermissionSetting | None:
    return db.query(PermissionSetting).filter(PermissionSetting.permission_key == key).first()


def set_permission_level(db: Session, key: str, level: str) -> PermissionSetting:
    ensure_defaults(db)
    setting = get_permission(db, key)
    if setting is None:
        raise ValueError(f"Unknown permission key '{key}'")
    setting.level = level
    db.commit()
    db.refresh(setting)
    return setting


def check(db: Session, permission_key: str | None) -> PermissionCheck:
    """The one function action_system.py/tool_registry.py actually call.
    A None permission_key means the action/tool has no permission gate at
    all (still subject to its own risk_level confirmation rule)."""
    if permission_key is None:
        return PermissionCheck(allowed=True, needs_confirmation=False, reason="no permission gate")
    setting = get_permission(db, permission_key)
    level = setting.level if setting is not None else _DEFAULTS_BY_KEY.get(permission_key, {}).get("level", "ask_first")
    if level == "disabled":
        return PermissionCheck(allowed=False, needs_confirmation=False, reason=f"'{permission_key}' is disabled in the Permission Center")
    if level == "ask_first":
        return PermissionCheck(allowed=True, needs_confirmation=True, reason=f"'{permission_key}' requires confirmation")
    return PermissionCheck(allowed=True, needs_confirmation=False, reason=f"'{permission_key}' is allowed")
