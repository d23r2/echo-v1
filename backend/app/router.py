from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import ChatMessage, ChatResult, ModelProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.grok_provider import GrokProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider

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
        self, preferred: str, system_prompt: str, messages: list[ChatMessage]
    ) -> tuple[ChatResult, str]:
        if preferred == "auto":
            last_error: Exception | None = None
            for provider in self.providers:
                available, _ = provider.available()
                if not available:
                    continue
                try:
                    return provider.chat(system_prompt, messages), provider.name
                except Exception as exc:  # try next provider in the fallback chain
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
            return provider.chat(system_prompt, messages), provider.name
        except Exception as exc:
            raise ProviderUnavailableError(f"{provider.label} request failed: {exc}") from exc


router = ModelRouter()
