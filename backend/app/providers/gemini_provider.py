import httpx

from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer

_GEMINI_ROLE_MAP = {"user": "user", "assistant": "model"}


class GeminiProvider(ModelProvider):
    name = "gemini"
    label = "Gemini (Google)"

    def available(self) -> tuple[bool, str | None]:
        settings = get_settings()
        if not settings.gemini_api_key:
            return False, "GEMINI_API_KEY not set"
        return True, None

    def chat(self, system_prompt: str, messages: list[ChatMessage]) -> ChatResult:
        settings = get_settings()
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.gemini_model}:generateContent"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [
                {"role": _GEMINI_ROLE_MAP[m.role], "parts": [{"text": m.content}]} for m in messages
            ],
        }
        resp = httpx.post(
            url,
            params={"key": settings.gemini_api_key},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        return split_reasoning_and_answer(raw)
