"""ECHO Layer 0 — Provider and Model Registry.

Wraps the existing `ModelRouter`/`ModelProvider.available()`/
`usage.get_active_cooldown()` machinery (app/router.py, app/usage.py) into
the structured record shape Layer 0 wants — it does not re-implement
provider selection, fallback ordering, or cooldown/quota classification,
all of which already exist and are already tested (see
test_router_fallback.py, test_provider_cooldown.py). This module only adds
metadata (category, capabilities, priority) that's static per provider and
formats it for GET /api/system/providers / /api/system/models.
"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app import usage
from app.config import Settings
from app.router import ModelRouter

# Static capability metadata — doesn't change at runtime, so it's plain data
# here rather than something each ModelProvider subclass would need its own
# new abstract methods for.
_PROVIDER_META: dict[str, dict] = {
    "anthropic": dict(category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=1),
    "openai": dict(category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=2),
    "gemini": dict(category="cloud_llm", requires_api_key=True, is_paid=False, supports_streaming=True, supports_tools=False, supports_vision=True, priority=3),
    "grok": dict(category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=4),
    "azure": dict(category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=5),
    "ollama": dict(category="local_llm", requires_api_key=False, is_paid=False, supports_streaming=True, supports_tools=False, supports_vision=False, priority=0),
}

_SEARCH_PROVIDERS: list[dict] = [
    dict(provider_id="wiki", display_name="Wikipedia", category="wiki", requires_api_key=False, is_paid=False),
    dict(provider_id="rss", display_name="RSS feeds", category="rss", requires_api_key=False, is_paid=False),
    dict(provider_id="searxng", display_name="SearXNG", category="web_search", requires_api_key=False, is_paid=False),
    dict(provider_id="direct_page", display_name="Direct page fetch", category="direct_page", requires_api_key=False, is_paid=False),
]

_LOCAL_MODEL_ROLES = ("fast", "reasoning", "coding", "critic", "writing")


@dataclass
class ProviderRecord:
    provider_id: str
    display_name: str
    category: str
    enabled: bool
    configured: bool
    available: bool
    health: str  # healthy | degraded | offline | not_configured
    requires_api_key: bool
    is_paid_or_metered: bool
    priority: int
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_vision: bool = False
    cooldown_active: bool = False
    last_error_category: str | None = None
    reason: str | None = None


@dataclass
class LocalModelRoleRecord:
    role: str
    configured_model: str | None
    falls_back_to_default: bool


def build_provider_registry(settings: Settings, router: ModelRouter, db: Session | None = None) -> list[ProviderRecord]:
    """Never raises — a provider's own `.available()` call is already
    exception-safe (see each provider's implementation), and cooldown
    lookups degrade to 'unknown' rather than propagating a DB error."""
    records: list[ProviderRecord] = []
    for status in router.statuses():
        name = status["name"]
        meta = _PROVIDER_META.get(name, dict(category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=False, supports_tools=False, supports_vision=False, priority=99))
        available = bool(status["available"])
        reason = status.get("reason")
        configured = available or not (reason and "not set" in (reason or "").lower())

        cooldown_active = False
        last_error_category = None
        if db is not None:
            try:
                cooldown = usage.get_active_cooldown(db, name)
                if cooldown is not None:
                    cooldown_active = True
                    last_error_category = cooldown.category
            except Exception:
                pass

        if not configured:
            health = "not_configured"
        elif cooldown_active:
            health = "degraded"
        elif available:
            health = "healthy"
        else:
            health = "offline"

        records.append(
            ProviderRecord(
                provider_id=name,
                display_name=status.get("label", name),
                category=meta["category"],
                enabled=True,
                configured=configured,
                available=available,
                health=health,
                requires_api_key=meta["requires_api_key"],
                is_paid_or_metered=meta["is_paid"],
                priority=meta["priority"],
                supports_streaming=meta["supports_streaming"],
                supports_tools=meta["supports_tools"],
                supports_vision=meta["supports_vision"],
                cooldown_active=cooldown_active,
                last_error_category=last_error_category,
                reason=reason,
            )
        )

    for search_meta in _SEARCH_PROVIDERS:
        pid = search_meta["provider_id"]
        if pid == "wiki":
            enabled = settings.wiki_search_enabled and settings.wiki_provider != "disabled"
            configured = True
        elif pid == "rss":
            enabled = settings.rss_search_enabled
            configured = bool(settings.rss_feed_url_list)
        elif pid == "searxng":
            enabled = settings.web_search_enabled and settings.web_search_provider == "searxng"
            configured = bool(settings.searxng_base_url)
        else:
            enabled = settings.web_search_enabled
            configured = True
        available = enabled and configured
        records.append(
            ProviderRecord(
                provider_id=pid,
                display_name=search_meta["display_name"],
                category=search_meta["category"],
                enabled=enabled,
                configured=configured,
                available=available,
                health="healthy" if available else ("not_configured" if not configured else "offline"),
                requires_api_key=search_meta["requires_api_key"],
                is_paid_or_metered=search_meta["is_paid"],
                priority=10,
                reason=None if available else ("disabled" if not enabled else "missing configuration"),
            )
        )
    return records


def build_local_model_roles(settings: Settings) -> list[LocalModelRoleRecord]:
    """Role -> configured model name, falling back to the single default
    `ollama_model` when a role-specific override isn't set — mirrors
    local_model_router.py's own fallback logic exactly, read-only here."""
    records = []
    for role in _LOCAL_MODEL_ROLES:
        configured = getattr(settings, f"ollama_model_{role}", None)
        records.append(
            LocalModelRoleRecord(
                role=role,
                configured_model=configured or settings.ollama_model,
                falls_back_to_default=configured is None,
            )
        )
    return records
