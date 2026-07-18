"""ECHO Layer 0 — Provider and Model Registry.

Wraps the existing `ModelRouter`/`ModelProvider.available()`/
`usage.get_active_cooldown()` machinery (app/router.py, app/usage.py) into
the structured record shape Layer 0 wants — it does not re-implement
provider selection, fallback ordering, or cooldown/quota classification,
all of which already exist and are already tested (see
test_router_fallback.py, test_provider_cooldown.py). This module only adds
metadata (category, capabilities, priority) that's static per provider and
formats it for GET /api/system/providers / /api/system/models.

ECHO Layer 2D adds capability/speed/privacy/context-size tags plus measured
health metrics (avg latency, failure rate) read from the existing
app/core/metrics.py counters — still no new instrumentation path, just a
read of what ModelRouter.chat()/LocalModelRouter.call() already record.
"""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app import usage
from app.config import Settings
from app.core import metrics
from app.router import ModelRouter

# ECHO Layer 2D — the capability vocabulary Phase 1 asks for. A provider's
# capabilities are a static, honest declaration of what that model family is
# actually good at — not a measured score (measured signal is latency/
# failure-rate, tracked separately below).
Capability = str  # planning|extraction|classification|coding|reasoning|critique|writing|summarization|vision|embeddings|tool_calling|json_reliability
SpeedClass = str  # fast|medium|slow
PrivacyClass = str  # local|cloud

# Static capability metadata — doesn't change at runtime, so it's plain data
# here rather than something each ModelProvider subclass would need its own
# new abstract methods for.
_PROVIDER_META: dict[str, dict] = {
    "anthropic": dict(
        category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=1,
        capabilities=["planning", "reasoning", "coding", "critique", "writing", "summarization", "json_reliability"], speed_class="medium", privacy_class="cloud", context_size=200000,
    ),
    "openai": dict(
        category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=2,
        capabilities=["planning", "reasoning", "coding", "critique", "writing", "summarization", "json_reliability"], speed_class="medium", privacy_class="cloud", context_size=128000,
    ),
    "gemini": dict(
        category="cloud_llm", requires_api_key=True, is_paid=False, supports_streaming=True, supports_tools=False, supports_vision=True, priority=3,
        capabilities=["reasoning", "coding", "writing", "summarization", "vision", "classification"], speed_class="fast", privacy_class="cloud", context_size=1000000,
    ),
    "grok": dict(
        category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=4,
        capabilities=["reasoning", "coding", "writing", "summarization"], speed_class="medium", privacy_class="cloud", context_size=128000,
    ),
    "azure": dict(
        category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=True, supports_tools=False, supports_vision=False, priority=5,
        capabilities=["planning", "reasoning", "coding", "critique", "writing", "summarization", "json_reliability"], speed_class="medium", privacy_class="cloud", context_size=128000,
    ),
    "ollama": dict(
        category="local_llm", requires_api_key=False, is_paid=False, supports_streaming=True, supports_tools=False, supports_vision=False, priority=0,
        capabilities=["planning", "extraction", "classification", "coding", "reasoning", "critique", "writing", "summarization"], speed_class="medium", privacy_class="local", context_size=8192,
    ),
}

# ECHO Layer 2D — the "typical capabilities" a local model *role* is used
# for (distinct from a provider's overall capabilities above) — matches
# local_intelligence_engine.py's actual usage of each role exactly, so this
# is a description of existing behavior, not a new policy.
_ROLE_CAPABILITIES: dict[str, list[str]] = {
    "fast": ["extraction", "classification", "writing"],
    "reasoning": ["planning", "reasoning"],
    "coding": ["coding"],
    "critic": ["critique", "json_reliability"],
    "writing": ["writing", "summarization"],
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
    # ECHO Layer 2D
    capabilities: list[str] = field(default_factory=list)
    speed_class: str = "medium"
    privacy_class: str = "cloud"
    context_size: int = 8192
    measured_avg_latency_ms: float | None = None
    measured_failure_rate: float | None = None
    measured_sample_count: int = 0


@dataclass
class LocalModelRoleRecord:
    role: str
    configured_model: str | None
    falls_back_to_default: bool
    # ECHO Layer 2D
    capabilities: list[str] = field(default_factory=list)


def _health_metrics(provider_name: str) -> tuple[float | None, float | None, int]:
    """Reads the existing app/core/metrics.py counters ModelRouter.chat()/
    LocalModelRouter.call() already record — no new instrumentation path,
    just a summary read. Returns (avg_latency_ms, failure_rate, sample_count)
    — all None/0 when nothing has been recorded yet (e.g. right after
    startup, or in a fresh test process)."""
    snap = metrics.snapshot()
    counters = snap["counters"]
    durations = snap["durations"]

    success = counters.get(f"model_calls_total[outcome=success,provider={provider_name}]", 0)
    success += counters.get(f"model_calls_total[outcome=success_fallback,provider={provider_name}]", 0)
    failure = counters.get(f"model_calls_total[outcome=failure,provider={provider_name}]", 0)
    total = success + failure
    failure_rate = (failure / total) if total > 0 else None

    duration_key = f"model_call_duration_ms[provider={provider_name}]"
    duration_summary = durations.get(duration_key)
    avg_latency = duration_summary["avg_ms"] if duration_summary else None
    sample_count = duration_summary["count"] if duration_summary else 0

    return avg_latency, failure_rate, sample_count


def build_provider_registry(settings: Settings, router: ModelRouter, db: Session | None = None) -> list[ProviderRecord]:
    """Never raises — a provider's own `.available()` call is already
    exception-safe (see each provider's implementation), and cooldown
    lookups degrade to 'unknown' rather than propagating a DB error."""
    records: list[ProviderRecord] = []
    for status in router.statuses():
        name = status["name"]
        meta = _PROVIDER_META.get(
            name,
            dict(category="cloud_llm", requires_api_key=True, is_paid=True, supports_streaming=False, supports_tools=False, supports_vision=False, priority=99,
                 capabilities=[], speed_class="medium", privacy_class="cloud", context_size=8192),
        )
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

        avg_latency, failure_rate, sample_count = _health_metrics(name)

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
                capabilities=list(meta.get("capabilities", [])),
                speed_class=meta.get("speed_class", "medium"),
                privacy_class=meta.get("privacy_class", "cloud"),
                context_size=meta.get("context_size", 8192),
                measured_avg_latency_ms=avg_latency,
                measured_failure_rate=failure_rate,
                measured_sample_count=sample_count,
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
                capabilities=list(_ROLE_CAPABILITIES.get(role, [])),
            )
        )
    return records
