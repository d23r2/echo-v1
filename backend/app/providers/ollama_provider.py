import httpx

from app.config import get_settings
from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer


class OllamaProvider(ModelProvider):
    name = "ollama"
    label = "Local (Ollama)"

    def available(self) -> tuple[bool, str | None]:
        settings = get_settings()
        try:
            resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=1.5)
            if resp.status_code == 200:
                return True, None
            return False, f"Ollama responded with status {resp.status_code}"
        except httpx.HTTPError:
            return False, "Ollama not reachable (is it running locally?)"

    def chat(self, system_prompt: str, messages: list[ChatMessage]) -> ChatResult:
        settings = get_settings()
        payload = {
            "model": settings.ollama_model,
            "messages": [{"role": "system", "content": system_prompt}]
            + [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
        }
        resp = httpx.post(f"{settings.ollama_base_url}/api/chat", json=payload, timeout=120)
        resp.raise_for_status()
        raw = resp.json().get("message", {}).get("content", "")
        return split_reasoning_and_answer(raw)
