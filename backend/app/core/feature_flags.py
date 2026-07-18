"""ECHO Layer 0 — Feature Flag Registry.

Consolidates the *existence* of every major ECHO subsystem into one
queryable list (GET /api/system/features, see routers/system.py) without
duplicating the config values themselves — every `enabled` here is read
straight from `app.config.Settings` or an existing DB-backed settings row
(CognitiveSettings, InterfaceSettings), never re-declared.

This is deliberately separate from the existing `/api/features` endpoint
(app/routers/features.py), which answers a narrower, different question —
"which chat/image providers actually work right now" (with cooldown/quota
detail) — and which the frontend already depends on unchanged. This
registry answers the broader Layer 0 question: "which ECHO subsystem exists
and is switched on," across everything from Atlas to Android support.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings


@dataclass
class FeatureFlag:
    key: str
    display_name: str
    enabled: bool
    source: str  # default | environment | runtime_setting
    dependency_status: str  # ok | missing_dependency | unavailable
    available: bool
    unavailable_reason: str | None = None
    restart_required: bool = False
    user_facing: bool = True
    developer_only: bool = False


def _flag(
    key: str,
    display_name: str,
    enabled: bool,
    *,
    source: str = "environment",
    dependency_ok: bool = True,
    unavailable_reason: str | None = None,
    restart_required: bool = False,
    user_facing: bool = True,
    developer_only: bool = False,
) -> FeatureFlag:
    available = enabled and dependency_ok
    return FeatureFlag(
        key=key,
        display_name=display_name,
        enabled=enabled,
        source=source,
        dependency_status="ok" if dependency_ok else "missing_dependency",
        available=available,
        unavailable_reason=None if available else (unavailable_reason or ("disabled" if not enabled else "missing dependency")),
        restart_required=restart_required,
        user_facing=user_facing,
        developer_only=developer_only,
    )


def list_feature_flags(settings: Settings, db: Session | None = None) -> list[FeatureFlag]:
    """Never raises — a broken optional dependency check degrades to
    'missing_dependency' rather than throwing, since this feeds a status
    page that must stay usable even when something else is unhealthy."""
    flags: list[FeatureFlag] = []

    flags.append(_flag("chat", "Chat", True, source="default", restart_required=False))
    flags.append(
        _flag(
            "ollama",
            "Ollama (local models)",
            settings.ollama_enabled,
            dependency_ok=bool(settings.ollama_base_url),
            unavailable_reason=None if settings.ollama_base_url else "OLLAMA_BASE_URL not set",
            restart_required=True,
        )
    )
    flags.append(
        _flag(
            "cloud_fallback",
            "Cloud fallback",
            settings.cloud_fallback_enabled,
            restart_required=True,
            developer_only=True,
        )
    )
    flags.append(_flag("atlas", "Atlas memory", True, source="default"))
    flags.append(
        _flag(
            "cognitive_core",
            "Cognitive Core",
            settings.cognitive_core_enabled,
            restart_required=True,
        )
    )
    flags.append(
        _flag(
            "local_intelligence",
            "Local Intelligence Engine",
            settings.local_intelligence_engine_enabled,
            dependency_ok=settings.ollama_enabled,
            unavailable_reason=None if settings.ollama_enabled else "requires Ollama",
            restart_required=True,
        )
    )
    flags.append(_flag("human_persona", "Human Persona", True, source="default"))
    flags.append(
        _flag(
            "core_identity",
            "Core Identity runtime",
            settings.core_identity_v1_enabled,
            restart_required=True,
            developer_only=True,
        )
    )
    flags.append(
        _flag(
            "adaptive_persona",
            "Adaptive communication persona",
            settings.persona_engine_v2_enabled,
            restart_required=True,
        )
    )
    flags.append(
        _flag(
            "operational_self_model",
            "Operational Self-Model",
            True,  # actual on/off is the InterfaceSettings DB row, checked by callers with db access
            source="runtime_setting",
        )
    )
    flags.append(_flag("skill_engine", "Skill Library", True, source="default"))
    flags.append(_flag("action_system", "Action System", settings.action_system_enabled, restart_required=True))
    flags.append(_flag("permission_center", "Permission Center", True, source="default", developer_only=True))
    flags.append(_flag("evaluation_lab", "Evaluation Lab", settings.evaluation_lab_enabled, developer_only=True))
    flags.append(_flag("knowledge_vault", "Knowledge Vault", True, source="default"))
    flags.append(_flag("projects", "Projects", True, source="default"))
    flags.append(_flag("tasks", "Tasks", True, source="default"))
    flags.append(_flag("schedule", "Schedule", True, source="default"))
    flags.append(_flag("library", "Library", True, source="default"))
    flags.append(
        _flag(
            "wiki",
            "Wikipedia search",
            settings.wiki_search_enabled,
            dependency_ok=settings.wiki_provider != "disabled",
        )
    )
    flags.append(
        _flag(
            "rss",
            "RSS feeds",
            settings.rss_search_enabled,
            dependency_ok=bool(settings.rss_feed_url_list),
            unavailable_reason=None if settings.rss_feed_url_list else "no RSS_FEED_URLS configured",
        )
    )
    flags.append(
        _flag(
            "searxng",
            "SearXNG web search",
            settings.web_search_enabled and settings.web_search_provider == "searxng",
            dependency_ok=bool(settings.searxng_base_url),
            unavailable_reason=None if settings.searxng_base_url else "no SEARXNG_BASE_URL configured",
        )
    )
    flags.append(_flag("direct_page_fetch", "Direct page fetch", settings.web_search_enabled))
    flags.append(_flag("voice", "Voice input/output", settings.voice_enabled, user_facing=True))
    flags.append(_flag("camera", "Camera capture", settings.camera_enabled, user_facing=True))
    flags.append(_flag("image_generation", "Image generation", settings.image_generation_enabled))
    flags.append(_flag("android_support", "Android app", True, source="default", user_facing=False))
    flags.append(_flag("windows_support", "Windows app", True, source="default", user_facing=False))
    flags.append(_flag("developer_mode", "Developer mode", settings.developer_mode, developer_only=True))
    flags.append(_flag("advanced_navigation", "Advanced navigation", True, source="runtime_setting"))
    flags.append(
        _flag(
            "supervised_self_modification",
            "Supervised self-modification",
            settings.supervised_self_modification_enabled,
            restart_required=True,
            developer_only=True,
        )
    )
    flags.append(
        _flag(
            "self_modification_sandbox",
            "Self-modification sandbox execution",
            settings.self_modification_sandbox_enabled,
            dependency_ok=settings.supervised_self_modification_enabled,
            unavailable_reason=None if settings.supervised_self_modification_enabled else "requires supervised_self_modification",
            restart_required=True,
            developer_only=True,
        )
    )
    flags.append(
        _flag(
            "self_modification_deployment",
            "Self-modification local-branch deployment",
            settings.self_modification_deployment_enabled,
            dependency_ok=settings.supervised_self_modification_enabled and settings.self_modification_sandbox_enabled,
            unavailable_reason=None
            if (settings.supervised_self_modification_enabled and settings.self_modification_sandbox_enabled)
            else "requires supervised_self_modification and self_modification_sandbox",
            restart_required=True,
            developer_only=True,
        )
    )
    flags.append(
        _flag(
            "self_modification_frontend",
            "Self-modification governance UI",
            settings.self_modification_frontend_enabled,
            restart_required=True,
            developer_only=True,
        )
    )

    return flags


def get_flag(settings: Settings, key: str) -> FeatureFlag | None:
    for flag in list_feature_flags(settings):
        if flag.key == key:
            return flag
    return None
