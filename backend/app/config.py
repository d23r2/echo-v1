from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    # Absolute path, not a bare ".env" — pydantic-settings resolves a relative
    # env_file against the process's CWD at import time, not this file's
    # location. That's silently wrong whenever the backend is launched from
    # anywhere other than backend/ itself (e.g. uvicorn's --app-dir backend
    # flag changes module resolution, not CWD) — .env then isn't found at
    # all, and every setting falls back to its field default with no error.
    # Confirmed in practice: OLLAMA_MODEL silently fell back to the default
    # "llama3.1" (not an installed model) instead of the real .env's
    # "llama3", and a real GEMINI_API_KEY was silently dropped, entirely
    # because of which directory the process happened to start from.
    model_config = SettingsConfigDict(env_file=str(BASE_DIR / ".env"), extra="ignore")

    # Server
    cors_origins: str = "http://localhost:5174,http://127.0.0.1:5174"

    # Storage
    database_url: str = f"sqlite:///{(DATA_DIR / 'echo.db').as_posix()}"
    chroma_dir: str = str(DATA_DIR / "chroma")
    attachments_dir: str = str(DATA_DIR / "attachments")
    max_attachment_bytes: int = 15 * 1024 * 1024  # 15MB total per request, enforced server-side too

    # Model providers
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    xai_api_key: str | None = None
    xai_model: str = "grok-4"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Distinct paid model (Imagen) — never used for normal chat, only explicit
    # image-generation requests. Separate from gemini_model, which stays free-tier.
    gemini_image_model: str = "imagen-4.0-fast-generate-001"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    default_provider: str = "auto"

    # --- Local Intelligence Engine v1 (app/services/local_intelligence_engine.py) ---
    # Off by default: this is a large new multi-call pipeline layered on top of the
    # existing single-call chat flow, and "don't break existing chat" outranks
    # defaulting a new, less-battle-tested path on. POST /api/chat/stream is
    # unaffected regardless of this flag — the engine only integrates into the
    # non-streaming endpoint for v1 (see routers/chat.py).
    local_intelligence_engine_enabled: bool = False
    local_model_routing_enabled: bool = True
    # Per-role model overrides — any left unset fall back to `ollama_model`
    # (the existing single default), so a fresh install with no role-specific
    # models pulled still works exactly as before this feature existed.
    ollama_model_fast: str | None = None
    ollama_model_reasoning: str | None = None
    ollama_model_coding: str | None = None
    ollama_model_critic: str | None = None
    ollama_model_writing: str | None = None
    local_model_default_role: str = "fast"
    local_model_timeout_seconds: int = 120
    local_model_max_retries: int = 1

    local_critic_enabled: bool = True
    local_critic_always_for_coding: bool = True
    local_critic_always_for_current_info: bool = True
    local_critic_max_repair_loops: int = 1

    # Cloud fallback stays optional and off by default — Ollama-only must be a
    # fully functional experience with zero paid-API dependence.
    cloud_fallback_enabled: bool = False
    cloud_fallback_require_user_confirmation: bool = True
    cloud_fallback_allowed_intents: str = "coding,code_review,complex_reasoning,long_document"
    cloud_fallback_daily_request_limit: int = 0
    cloud_fallback_monthly_cost_limit: float = 0

    local_context_max_chars: int = 12000
    local_context_max_memory_items: int = 5
    local_context_max_file_chunks: int = 5
    local_context_max_web_results: int = 5
    local_context_max_conversation_snippets: int = 5

    local_answer_quality_mode: str = "balanced"  # fast | balanced | deep

    @property
    def cloud_fallback_allowed_intent_list(self) -> list[str]:
        return [i.strip() for i in self.cloud_fallback_allowed_intents.split(",") if i.strip()]

    # Persona tuning
    independence_nudge_every_n_turns: int = 6
    atlas_top_k: int = 5

    # Provider fallback / free-mode tuning (Phase 2/3)
    # Ollama always participates in auto-mode's fallback chain (as the final
    # local option) unless explicitly turned off.
    ollama_always_available_fallback: bool = True
    # How long a provider that just hit a quota/credit/billing/rate-limit error
    # is skipped for, so the router doesn't keep paying the latency cost of a
    # doomed call every single turn. 0 disables cooldown entirely.
    provider_cooldown_minutes: int = 30
    # When true: prefer Ollama, treat free-tier providers as optional helpers,
    # and never call Azure or other paid-only providers even if configured —
    # see app/router.py's provider ordering.
    free_mode: bool = False

    # Azure OpenAI — disabled by default; never primary in FREE_MODE regardless
    # of this flag. All fields must be set for the provider to actually work;
    # missing config is treated the same as "not configured", not an error.
    azure_openai_enabled: bool = False
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_daily_request_limit: int | None = None
    azure_daily_token_limit: int | None = None

    # Image generation provider selection (Phase 6)
    image_provider: str = "auto"  # auto | gemini | ollama | comfyui | disabled
    comfyui_base_url: str | None = None

    # Reserved for a future free-tier provider integration (Groq/OpenRouter
    # both expose OpenAI-compatible chat completion APIs with a free tier).
    # Not yet wired to an actual ModelProvider — see PROJECT_HEALTH_REPORT.md's
    # known-gaps section. Setting these currently has no effect.
    openrouter_api_key: str | None = None
    groq_api_key: str | None = None

    # --- No-billing web search (app/web_search.py) ---
    # All disabled/absent by default — Echo works fully without any of these
    # configured, it just can't answer current/live questions (and says so
    # honestly instead of guessing). None of these require an API key or
    # billing; SearXNG is meant to be self-hosted (see docs/searxng-setup.md).
    web_search_enabled: bool = False
    web_search_provider: str = "searxng"  # searxng | disabled
    searxng_base_url: str | None = None
    web_search_max_results: int = 5
    web_fetch_timeout_seconds: int = 10
    # Simple in-memory TTL cache for identical queries — avoids hammering a
    # public/self-hosted SearXNG instance on repeated near-identical asks.
    web_search_cache_minutes: int = 10

    wiki_search_enabled: bool = True
    wiki_provider: str = "wikimedia"  # wikimedia | custom | disabled
    wiki_api_base_url: str = "https://en.wikipedia.org/w/api.php"
    wiki_max_results: int = 5
    wiki_fetch_timeout_seconds: int = 10
    # Wikimedia's API enforces its robot policy (https://w.wiki/4wJS) by
    # rejecting any User-Agent that doesn't look like ClientName/Version (URL;
    # contact) — a plain descriptive string with no URL-shaped token gets a
    # hard 403 (confirmed by hand against the real API). Also sent to
    # SearXNG/RSS/direct-page requests for consistency, though only Wikimedia
    # actually enforces this. None of this requires a key or account — it's
    # purely a client-identification string, not a credential.
    wiki_user_agent: str = (
        "EchoPersonalAI/1.0 (https://github.com/echo-project/echo; local self-hosted, "
        "no-billing search) python-httpx"
    )

    rss_search_enabled: bool = False
    rss_feed_urls: str = ""  # comma-separated
    rss_max_items_per_feed: int = 10
    rss_fetch_timeout_seconds: int = 10
    rss_cache_minutes: int = 10

    @property
    def rss_feed_url_list(self) -> list[str]:
        return [u.strip() for u in self.rss_feed_urls.split(",") if u.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- ECHO Action + Reliability Core v1: Conversation Auto-Summary ---
    conversation_auto_summary_enabled: bool = True
    conversation_auto_summary_min_messages: int = 8
    conversation_auto_summary_require_approval: bool = False

    # --- Action System v1 ---
    # On by default, unlike local_intelligence_engine_enabled/
    # cloud_fallback_enabled — the actual safety layer here is per-action
    # risk_level + the Permission Center (disabled/ask_first/allowed), not a
    # single master switch, since most actions just wrap already-safe
    # existing endpoints (create_task, atlas_search, ...). This flag exists
    # as an emergency full-stop, not the primary control.
    action_system_enabled: bool = True

    # --- Cognitive Core v1 ---
    # On by default — the actual gating is "only for medium/hard-difficulty
    # requests" (cognitive_core.py), so simple messages are unaffected either
    # way; this flag is a full-stop for the whole feature.
    cognitive_core_enabled: bool = True
    cognitive_concept_extraction_enabled: bool = True
    cognitive_skill_matching_enabled: bool = True
    # Never shown in the normal chat UI regardless of this flag (Phase 13
    # rule 3) — this only controls whether the Cognitive Core page exposes
    # the raw brief_text of recent briefs, for a developer looking at
    # /cognitive-core, not for anything injected into a chat reply.
    cognitive_show_developer_diagnostics: bool = False

    # ============================================================
    # ECHO Layer 0 — Infrastructure Foundation v1
    # ============================================================
    # These fields are additive — every field already above this section
    # remains unchanged (name, default, and semantics) so no existing test
    # or call site needed to change. New fields fill genuine gaps (app
    # identity, observability, safety defaults, performance knobs) rather
    # than re-declaring what already exists (e.g. cors_origins,
    # local_context_max_chars, cloud_fallback_enabled are already above).

    # --- Application identity ---
    app_name: str = "ECHO"
    app_env: str = "development"  # development | production | test
    app_version: str = "0.9.0"  # pre-1.0 — see ECHO_LAYER_0_INFRASTRUCTURE_FOUNDATION.md's versioning note
    debug: bool = False
    log_level: str = "INFO"  # DEBUG | INFO | WARNING | ERROR
    host: str = "0.0.0.0"
    port: int = 8000

    # --- Frontend origin (distinct from cors_origins, which is the full
    # comma-separated allowlist already used by CORSMiddleware above) ---
    frontend_url: str = "http://localhost:5174"

    # --- Database extras (database_url already exists above) ---
    database_echo: bool = False  # SQLAlchemy engine echo (raw SQL logging) — off by default, verbose
    database_backup_enabled: bool = True
    database_backup_path: str = str(DATA_DIR / "backups")

    # --- Ollama extras (ollama_base_url/ollama_model/ollama_model_* already exist above) ---
    ollama_enabled: bool = True
    ollama_timeout_seconds: int = 60

    # --- Feature flags not already covered by an existing *_enabled field
    # above (atlas/human_persona/operational_self_model/action_system/
    # cognitive_core/local_intelligence_engine/conversation_auto_summary
    # already exist — see their own sections above) ---
    developer_mode: bool = False
    voice_enabled: bool = True
    camera_enabled: bool = True
    image_generation_enabled: bool = True
    evaluation_lab_enabled: bool = True

    # --- Safety defaults (Permission Center's per-key PermissionSetting
    # table is the actual runtime source of truth for these at the
    # action/tool level — these are the install-level *initial* defaults it
    # seeds from, same "config.py is the starting default, DB is the mutable
    # source of truth" split used elsewhere in this app) ---
    file_write_enabled: bool = False
    code_execution_enabled: bool = False
    destructive_actions_enabled: bool = False
    public_push_enabled: bool = False

    # --- Performance ---
    request_timeout_seconds: int = 30
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    max_concurrent_model_requests: int = 2

    # --- ECHO Layer 2E: Context Selection v2 ---
    # Off by default, same "don't break existing chat" posture as
    # local_intelligence_engine_enabled above — when off,
    # LocalIntelligenceEngine.generate_response() gathers context exactly as
    # it did before this milestone (context_gatherer.gather_context() +
    # its own cognitive-brief call), unaffected by anything in
    # services/context_selector.py.
    context_selection_v2_enabled: bool = False

    # --- ECHO Layer 3A Part 2A: Core Identity data foundation ---
    # Default True (unlike the flags above): this milestone only adds new,
    # previously-nonexistent tables and a bootstrap seed — nothing existing
    # reads or is affected by them yet, so there's no "don't break existing
    # chat" risk to gate against. Runtime prompt integration (the part that
    # *would* change model-visible behavior) is explicitly Part 2B's job and
    # is gated at every runtime integration seam by this same flag. When
    # disabled, the legacy persona/prompt behavior remains byte-for-byte
    # active and identity tables may remain present but unused at runtime.
    core_identity_v1_enabled: bool = True
    core_identity_cache_ttl_seconds: int = 300

    # --- ECHO Layer 3A Part 2C: adaptive communication persona ---
    # Uses the existing PersonaSettings/RelationshipProfile/Atlas preference
    # stores.  Disabling this restores the legacy Human Persona prompt overlay
    # without changing or deleting any persisted preference data.
    persona_engine_v2_enabled: bool = True
    persona_cache_ttl_seconds: int = 300

    # --- Observability ---
    metrics_enabled: bool = True
    request_logging_enabled: bool = True
    diagnostics_enabled: bool = True
    error_reporting_enabled: bool = False  # no external error-reporting service wired up — local-first

    def validate_startup(self) -> list[str]:
        """Deterministic, no-raise config sanity check — returns a list of
        human-readable problems (empty if none). Called once at startup
        (see main.py's lifespan) so a bad .env value fails with a clear
        message instead of a confusing downstream error. Never raises
        itself — the caller decides whether a given problem is fatal."""
        problems: list[str] = []
        if not (1 <= self.port <= 65535):
            problems.append(f"port must be between 1 and 65535, got {self.port}")
        if self.log_level.upper() not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            problems.append(f"log_level must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL, got '{self.log_level}'")
        if self.app_env not in ("development", "production", "test"):
            problems.append(f"app_env must be one of development/production/test, got '{self.app_env}'")
        if self.request_timeout_seconds <= 0:
            problems.append(f"request_timeout_seconds must be positive, got {self.request_timeout_seconds}")
        if self.max_concurrent_model_requests <= 0:
            problems.append(f"max_concurrent_model_requests must be positive, got {self.max_concurrent_model_requests}")
        if self.cache_ttl_seconds < 0:
            problems.append(f"cache_ttl_seconds cannot be negative, got {self.cache_ttl_seconds}")
        if self.core_identity_cache_ttl_seconds < 0:
            problems.append(
                "core_identity_cache_ttl_seconds cannot be negative, got "
                f"{self.core_identity_cache_ttl_seconds}"
            )
        if self.persona_cache_ttl_seconds < 0:
            problems.append(
                "persona_cache_ttl_seconds cannot be negative, got "
                f"{self.persona_cache_ttl_seconds}"
            )
        return problems

    # Field names that must never appear in a diagnostics/status response —
    # matched by suffix so a future *_api_key/*_secret/*_token field is
    # excluded automatically without needing this list updated by hand.
    _SECRET_FIELD_SUFFIXES = ("_api_key", "_secret", "_token", "_password")

    def public_dict(self) -> dict:
        """A diagnostics-safe projection of settings — every *_api_key/
        *_secret/*_token/*_password field (present or future) is excluded by
        suffix match, not by an easy-to-forget explicit allowlist. Used by
        /api/system/diagnostics and nowhere else; never log full settings
        objects directly (see core/logging.py's redaction filter for the
        defense-in-depth backstop if something does)."""
        result = {}
        for key, value in self.model_dump().items():
            if key.endswith(self._SECRET_FIELD_SUFFIXES):
                continue
            result[key] = value
        return result


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
