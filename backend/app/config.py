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

    # Model providers
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    xai_api_key: str | None = None
    xai_model: str = "grok-4"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    default_provider: str = "auto"

    # Persona tuning
    independence_nudge_every_n_turns: int = 6
    atlas_top_k: int = 5

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
