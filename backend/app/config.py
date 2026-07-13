from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
