import base64

import httpx

from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer

_GEMINI_ROLE_MAP = {"user": "user", "assistant": "model"}


def _message_to_parts(message: ChatMessage) -> list[dict]:
    parts: list[dict] = []
    if message.content:
        parts.append({"text": message.content})
    for mime_type, raw_bytes in message.images or []:
        parts.append(
            {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(raw_bytes).decode("ascii")}}
        )
    return parts


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
                {"role": _GEMINI_ROLE_MAP[m.role], "parts": _message_to_parts(m)} for m in messages
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
