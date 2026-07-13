import logging

from sqlalchemy.orm import Session

from app import usage
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ChatMessage, ChatResult, ModelProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.grok_provider import GrokProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Ollama is local/self-hosted with no quota concept — never tracked.
_USAGE_TRACKED_PROVIDERS = {"anthropic", "openai", "grok", "gemini"}

# Priority order for "auto" mode.
_PROVIDERS: list[ModelProvider] = [
    AnthropicProvider(),
    OpenAIProvider(),
    GeminiProvider(),
    GrokProvider(),
    OllamaProvider(),
]


class NoProviderAvailableError(Exception):
    pass


class ProviderUnavailableError(Exception):
    pass


class ModelRouter:
    def __init__(self, providers: list[ModelProvider] | None = None):
        self.providers = providers or _PROVIDERS

    def get_provider(self, name: str) -> ModelProvider | None:
        return next((p for p in self.providers if p.name == name), None)

    def statuses(self) -> list[dict]:
        out = []
        for p in self.providers:
            available, reason = p.available()
            out.append({"name": p.name, "label": p.label, "available": available, "reason": reason})
        return out

    def chat(
        self,
        preferred: str,
        system_prompt: str,
        messages: list[ChatMessage],
        db: Session | None = None,
    ) -> tuple[ChatResult, str, str | None]:
        """Returns (result, provider_used, fallback_note). fallback_note is set only
        in auto mode, only when a higher-priority provider was skipped this turn
        because it 429'd — e.g. "gemini rate-limited; used ollama" — so the caller can
        surface which provider actually answered and why it wasn't the usual one."""

        def _track_success(provider: ModelProvider) -> None:
            if db is not None and provider.name in _USAGE_TRACKED_PROVIDERS:
                usage.record_request(db, provider.name)

        def _track_failure(provider: ModelProvider, exc: Exception) -> None:
            if (
                db is not None
                and provider.name in _USAGE_TRACKED_PROVIDERS
                and usage.is_rate_limit_error(exc)
            ):
                usage.record_429(db, provider.name)

        if preferred == "auto":
            last_error: Exception | None = None
            rate_limited_this_turn: list[str] = []
            for provider in self.providers:
                available, _ = provider.available()
                if not available:
                    continue
                try:
                    result = provider.chat(system_prompt, messages)
                    _track_success(provider)
                    fallback_note = (
                        f"{', '.join(rate_limited_this_turn)} rate-limited this turn; replied via {provider.name}"
                        if rate_limited_this_turn
                        else None
                    )
                    return result, provider.name, fallback_note
                except Exception as exc:
                    # Previously silent — a provider failing (e.g. a rate limit) and
                    # auto mode quietly falling back to a weaker provider (like one
                    # with no vision support) was completely invisible in the logs.
                    logger.warning(
                        "auto mode: %s failed, trying next provider: %s", provider.name, exc
                    )
                    _track_failure(provider, exc)
                    if usage.is_rate_limit_error(exc):
                        rate_limited_this_turn.append(provider.name)
                    last_error = exc
                    continue
            if last_error:
                raise NoProviderAvailableError(
                    f"All providers failed; last error: {last_error}"
                ) from last_error
            raise NoProviderAvailableError(
                "No model provider is available. Set an API key or run Ollama locally."
            )

        provider = self.get_provider(preferred)
        if provider is None:
            raise ValueError(f"Unknown provider '{preferred}'")
        available, reason = provider.available()
        if not available:
            raise ProviderUnavailableError(f"{provider.label} is unavailable: {reason}")
        try:
            result = provider.chat(system_prompt, messages)
            _track_success(provider)
            return result, provider.name, None
        except Exception as exc:
            _track_failure(provider, exc)
            raise ProviderUnavailableError(f"{provider.label} request failed: {exc}") from exc


router = ModelRouter()
