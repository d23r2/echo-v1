"""ECHO Cognitive Core v1 — Skill Library.

Reusable, named workflows ECHO knows how to run — checklists, not scripts.
Nothing here is auto-executed; app/services/action_system.py is the
separate, permission-gated system for actual side-effecting actions.
Matching is deterministic keyword matching, same convention as the rest of
Cognitive Core.
"""

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import SkillPattern, _now

SEED_SKILLS: list[dict] = [
    {
        "name": "Build Android APK",
        "description": "Build and verify the latest ECHO Android app.",
        "category": "release",
        "trigger_patterns": ["android apk", "build apk", "update apk", "android app"],
        "steps": [
            "inspect Capacitor config",
            "build the frontend (npm run build)",
            "run cap sync/copy",
            "run Gradle assembleDebug",
            "locate the built APK",
            "test install on device/emulator",
            "test backend connection from the app",
            "record the result",
        ],
        "required_tools": ["npm", "npx cap", "gradlew"],
        "success_criteria": ["frontend build passes", "Capacitor sync succeeds", "APK builds", "APK installs and connects to backend"],
        "common_failures": ["Android SDK/Gradle not installed", "backend URL still pointing at localhost", "stale frontend assets not synced"],
    },
    {
        "name": "Build Windows App",
        "description": "Build and verify the latest ECHO Windows app.",
        "category": "release",
        "trigger_patterns": ["windows app", "tauri build", "build windows"],
        "steps": [
            "inspect Tauri config",
            "build the frontend (npm run build)",
            "run the Tauri build",
            "locate the built artifact",
            "test launch",
            "record the result",
        ],
        "required_tools": ["npm", "tauri"],
        "success_criteria": ["frontend build passes", "Tauri build succeeds", "app launches and connects to backend"],
        "common_failures": ["Rust/Tauri toolchain not installed"],
    },
    {
        "name": "Run ECHO Release Verification",
        "description": "Run ECHO's full release readiness check.",
        "category": "release",
        "trigger_patterns": ["release status", "is echo green", "is echo ready", "release readiness", "release verification"],
        "steps": [
            "run backend tests",
            "run frontend build",
            "run any focused/new tests for this pass",
            "record Green/Yellow/Red honestly",
            "update the release report",
        ],
        "required_tools": ["pytest", "npm"],
        "success_criteria": ["backend tests pass", "frontend build passes", "status is assigned only from actual recorded results"],
        "common_failures": ["claiming Green without running the checks", "an unrelated flaky test being treated as a real failure"],
    },
    {
        "name": "Fix Failing Backend Test",
        "description": "Diagnose and fix a failing backend test.",
        "category": "troubleshooting",
        "trigger_patterns": ["failing test", "fix test", "test is failing", "broken test"],
        "steps": [
            "run the failing test with -vv for detail",
            "inspect the actual failure/assertion",
            "fix the smallest correct cause",
            "re-run the failing test",
            "run the full backend suite",
            "report the result",
        ],
        "required_tools": ["pytest"],
        "success_criteria": ["the specific test passes", "the full suite still passes", "no new regression introduced"],
        "common_failures": ["fixing a symptom instead of the root cause", "chasing an unrelated flaky test"],
    },
    {
        "name": "Create Claude Code Prompt",
        "description": "Produce a complete, structured Claude Code prompt.",
        "category": "writing",
        "trigger_patterns": ["claude code prompt", "give me a prompt", "write a prompt", "prompt to update"],
        "steps": ["define the goal", "include relevant context", "add rules/constraints", "add phases/tasks", "add tests", "add a final report format"],
        "required_tools": [],
        "success_criteria": ["prompt includes context", "prompt includes concrete tasks", "prompt includes rules", "prompt includes tests", "prompt includes a final report format"],
        "common_failures": ["a vague prompt with no way to tell when it's actually done"],
    },
    {
        "name": "Configure No-Billing Search",
        "description": "Set up Wikipedia/RSS/SearXNG search without any paid API.",
        "category": "system",
        "trigger_patterns": ["configure searxng", "no-billing search", "set up search", "configure rss"],
        "steps": [
            "enable Wikipedia lookups (no key needed)",
            "add a proper User-Agent string",
            "configure RSS feed URLs",
            "configure the SearXNG base URL",
            "test that sources display cleanly in the via-line",
        ],
        "required_tools": ["SearXNG"],
        "success_criteria": ["source display in chat metadata is clean", "no paid API key required anywhere in this setup"],
        "common_failures": ["Wikimedia rejecting requests without a proper User-Agent"],
    },
    {
        "name": "Improve ECHO Feature Safely",
        "description": "Add or improve an ECHO feature without breaking existing ones.",
        "category": "planning",
        "trigger_patterns": ["add a feature to echo", "improve echo", "new echo feature", "echo milestone"],
        "steps": [
            "inspect the current repo state first",
            "define a practical v1 scope",
            "implement the backend",
            "implement the frontend",
            "add tests",
            "run the build",
            "document what changed",
            "commit/tag if requested",
        ],
        "required_tools": ["pytest", "npm"],
        "success_criteria": ["backend tests pass", "frontend build passes", "docs updated", "no existing feature broken"],
        "common_failures": ["rebuilding more than was actually asked for"],
    },
]


def seed_skills(db: Session) -> None:
    """Idempotent — only inserts skills that don't already exist by name,
    marked source via trigger_patterns/steps being present (no separate
    source_type field on SkillPattern; the seed list itself is the source
    of truth for what "system" skills look like)."""
    existing_names = {s.name for s in db.query(SkillPattern).all()}
    for entry in SEED_SKILLS:
        if entry["name"] in existing_names:
            continue
        db.add(
            SkillPattern(
                name=entry["name"],
                description=entry["description"],
                category=entry["category"],
                trigger_patterns_json=entry["trigger_patterns"],
                steps_json=entry["steps"],
                required_tools_json=entry["required_tools"],
                success_criteria_json=entry["success_criteria"],
                common_failures_json=entry["common_failures"],
            )
        )
    db.commit()


def list_skills(db: Session, category: str | None = None, include_archived: bool = False) -> list[SkillPattern]:
    query = db.query(SkillPattern)
    if not include_archived:
        query = query.filter(SkillPattern.archived_at.is_(None))
    if category:
        query = query.filter(SkillPattern.category == category)
    return query.order_by(SkillPattern.name).all()


def search_skills(db: Session, query: str) -> list[SkillPattern]:
    like = f"%{query.strip()}%"
    return (
        db.query(SkillPattern)
        .filter(SkillPattern.archived_at.is_(None))
        .filter(or_(SkillPattern.name.ilike(like), SkillPattern.description.ilike(like)))
        .all()
    )


def create_skill(db: Session, **fields) -> SkillPattern:
    name = fields.get("name", "").strip()
    if not name:
        raise ValueError("A skill name is required.")
    existing = db.query(SkillPattern).filter(SkillPattern.name == name, SkillPattern.archived_at.is_(None)).first()
    if existing:
        raise ValueError(f"A skill named '{name}' already exists.")
    skill = SkillPattern(
        name=name,
        description=fields.get("description", ""),
        category=fields.get("category", "other"),
        trigger_patterns_json=fields.get("trigger_patterns", []),
        steps_json=fields.get("steps", []),
        required_tools_json=fields.get("required_tools", []),
        success_criteria_json=fields.get("success_criteria", []),
        common_failures_json=fields.get("common_failures", []),
    )
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


def update_skill(db: Session, skill_id: str, updates: dict) -> SkillPattern:
    skill = db.get(SkillPattern, skill_id)
    if skill is None:
        raise ValueError("That skill doesn't exist.")
    field_map = {"steps": "steps_json", "success_criteria": "success_criteria_json"}
    for field, value in updates.items():
        if value is None:
            continue
        setattr(skill, field_map.get(field, field), value)
    db.commit()
    db.refresh(skill)
    return skill


def archive_skill(db: Session, skill_id: str) -> SkillPattern:
    skill = db.get(SkillPattern, skill_id)
    if skill is None:
        raise ValueError("That skill doesn't exist.")
    skill.archived_at = _now()
    db.commit()
    db.refresh(skill)
    return skill


def suggest_plan(db: Session, user_message: str) -> SkillPattern | None:
    """Returns the single best-matching skill (or None) — used by
    POST /api/cognitive/skills/{id}/suggest-plan's sibling free-text lookup
    and by cognitive_core.select_relevant_skills() for brief-building."""
    from app.services.cognitive_core import select_relevant_skills

    matches = select_relevant_skills(db, user_message, limit=1)
    return matches[0] if matches else None
