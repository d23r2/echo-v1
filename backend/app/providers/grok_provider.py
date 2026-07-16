from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer


class GrokProvider(ModelProvider):
    name = "grok"
    label = "Grok (xAI)"

    def available(self) -> tuple[bool, str | None]:
        settings = get_settings()
        if not settings.xai_api_key:
            return False, "XAI_API_KEY not set"
        return True, None

    def chat(self, system_prompt: str, messages: list[ChatMessage], model: str | None = None) -> ChatResult:
        from openai import OpenAI  # xAI Grok exposes an OpenAI-compatible endpoint

        settings = get_settings()
        client = OpenAI(api_key=settings.xai_api_key, base_url="https://api.x.ai/v1")
        response = client.chat.completions.create(
            model=settings.xai_model,
            messages=[{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
        )
        raw = response.choices[0].message.content or ""
        return split_reasoning_and_answer(raw)
