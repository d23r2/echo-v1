from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer


class OpenAIProvider(ModelProvider):
    name = "openai"
    label = "OpenAI (GPT)"

    def available(self) -> tuple[bool, str | None]:
        settings = get_settings()
        if not settings.openai_api_key:
            return False, "OPENAI_API_KEY not set"
        return True, None

    def chat(self, system_prompt: str, messages: list[ChatMessage], model: str | None = None) -> ChatResult:
        from openai import OpenAI

        settings = get_settings()
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
        )
        raw = response.choices[0].message.content or ""
        return split_reasoning_and_answer(raw)
