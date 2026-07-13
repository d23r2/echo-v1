import base64

import httpx

from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer

_GEMINI_ROLE_MAP = {"user": "user", "assistant": "model"}


def _post_sanitized(url: str, *, params: dict, json: dict, timeout: float) -> httpx.Response:
    """Every httpx exception raised by a failed request here (HTTPStatusError,
    ConnectError, TimeoutException, ...) stringifies to include the full request
    URL — which always has the API key in it as a `?key=...` query param in this
    module. That message reaches HTTPException details and gets rendered verbatim
    in the UI's error banners, so a failed call would otherwise leak a live
    credential to the screen. Catch everything from httpx and re-raise sanitized."""
    try:
        resp = httpx.post(url, params=params, json=json, timeout=timeout)
        resp.raise_for_status()
        return resp
    except httpx.HTTPStatusError as exc:
        err = RuntimeError(f"Gemini API error {exc.response.status_code}: {exc.response.text[:300]}")
        # app.usage.is_rate_limit_error() checks this attribute (same convention the
        # anthropic/openai SDKs use) — preserve it so 429 tracking still works
        # despite the message itself no longer carrying the raw URL/key.
        err.status_code = exc.response.status_code  # type: ignore[attr-defined]
        raise err from None
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Gemini API request failed: {type(exc).__name__}") from None


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
        resp = _post_sanitized(
            url, params={"key": settings.gemini_api_key}, json=payload, timeout=60
        )
        data = resp.json()
        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        return split_reasoning_and_answer(raw)


def generate_image(prompt: str) -> bytes:
    """Calls Imagen (settings.gemini_image_model) — a distinct, PAID endpoint, never
    the free-tier gemini_model used for normal chat. Only invoked from the explicit
    POST /api/chat/generate-image action, never automatically from a chat turn."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.gemini_image_model}:predict"
    )
    payload = {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1}}
    resp = _post_sanitized(
        url, params={"key": settings.gemini_api_key}, json=payload, timeout=90
    )
    data = resp.json()
    predictions = data.get("predictions") or []
    if not predictions or "bytesBase64Encoded" not in predictions[0]:
        raise RuntimeError("No image returned by the model")
    return base64.b64decode(predictions[0]["bytesBase64Encoded"])
