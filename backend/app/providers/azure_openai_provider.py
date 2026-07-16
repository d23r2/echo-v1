from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer


class AzureOpenAIProvider(ModelProvider):
    """Disabled by default (AZURE_OPENAI_ENABLED=false) — Azure is a paid,
    enterprise-oriented provider and is never treated as a free option.
    Even when enabled, app/router.py never puts it ahead of Ollama/Gemini in
    FREE_MODE, and its daily request count (AZURE_DAILY_REQUEST_LIMIT,
    enforced in app/router.py via app/usage.py) keeps it from being called
    past a self-imposed cap regardless of what Azure's own billing would
    otherwise allow."""

    name = "azure"
    label = "Azure OpenAI"

    def available(self) -> tuple[bool, str | None]:
        settings = get_settings()
        if not settings.azure_openai_enabled:
            return False, "Azure OpenAI is disabled (set AZURE_OPENAI_ENABLED=true to use it)"
        if not settings.azure_openai_endpoint:
            return False, "AZURE_OPENAI_ENDPOINT not set"
        if not settings.azure_openai_api_key:
            return False, "AZURE_OPENAI_API_KEY not set"
        if not settings.azure_openai_deployment:
            return False, "AZURE_OPENAI_DEPLOYMENT not set"
        return True, None

    def chat(self, system_prompt: str, messages: list[ChatMessage], model: str | None = None) -> ChatResult:
        from openai import AzureOpenAI

        settings = get_settings()
        client = AzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
        )
        response = client.chat.completions.create(
            model=settings.azure_openai_deployment,
            messages=[{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
        )
        raw = response.choices[0].message.content or ""
        return split_reasoning_and_answer(raw)
