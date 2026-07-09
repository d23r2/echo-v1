from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer


class AnthropicProvider(ModelProvider):
    name = "anthropic"
    label = "Claude (Anthropic)"

    def available(self) -> tuple[bool, str | None]:
        settings = get_settings()
        if not settings.anthropic_api_key:
            return False, "ANTHROPIC_API_KEY not set"
        return True, None

    def chat(self, system_prompt: str, messages: list[ChatMessage]) -> ChatResult:
        import anthropic

        settings = get_settings()
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        raw = "".join(block.text for block in response.content if block.type == "text")
        return split_reasoning_and_answer(raw)
