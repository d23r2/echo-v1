"""ECHO Local Intelligence Engine v1 — Phase 5: Local Model Router.

Role-based routing around a single local (Ollama) install — not "one more
cloud provider," a way to point different parts of the pipeline at
different locally-installed models when the user has them, while degrading
gracefully to one shared default model when they don't. Nobody is required
to pull five separate Ollama models for this to work.
"""

import logging
import threading
from dataclasses import dataclass
from typing import Literal

import httpx

from app.config import get_settings
from app.core import metrics
from app.providers.base import ChatMessage, ChatResult
from app.providers.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)

ModelRole = Literal["fast", "reasoning", "coding", "critic", "writing"]
ALL_ROLES: list[ModelRole] = ["fast", "reasoning", "coding", "critic", "writing"]

# ECHO Layer 0 — bounds how many Ollama calls run at once across the whole
# process (a single local model instance chokes badly on concurrent
# requests). Sized from Settings.max_concurrent_model_requests at first use
# rather than import time, so tests that override the setting take effect.
_semaphore_lock = threading.Lock()
_semaphore: threading.Semaphore | None = None
_semaphore_size: int | None = None
_SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS = 30


def _get_semaphore() -> threading.Semaphore:
    global _semaphore, _semaphore_size
    size = get_settings().max_concurrent_model_requests
    with _semaphore_lock:
        if _semaphore is None or _semaphore_size != size:
            _semaphore = threading.Semaphore(max(1, size))
            _semaphore_size = size
        return _semaphore


@dataclass
class LocalModelCallResult:
    ok: bool
    text: str
    role: str
    model_requested: str
    model_used: str | None
    fallback_used: bool
    error: str | None
    chat_result: ChatResult | None = None


class LocalModelRouter:
    def __init__(self, provider: OllamaProvider | None = None):
        self.provider = provider or OllamaProvider()

    def available(self) -> tuple[bool, str | None]:
        return self.provider.available()

    def model_for_role(self, role: str) -> str:
        settings = get_settings()
        overrides = {
            "fast": settings.ollama_model_fast,
            "reasoning": settings.ollama_model_reasoning,
            "coding": settings.ollama_model_coding,
            "critic": settings.ollama_model_critic,
            "writing": settings.ollama_model_writing,
        }
        return overrides.get(role) or settings.ollama_model

    def call(self, role: ModelRole, system_prompt: str, messages: list[ChatMessage]) -> LocalModelCallResult:
        """Never raises. Ollama offline or unreachable -> clean ok=False
        result with a plain-language error, not a crash. A configured
        role-specific model that Ollama doesn't actually have installed ->
        one retry against the plain default model (LOCAL_MODEL_MAX_RETRIES
        governs whether this retry happens at all), reported via
        fallback_used so the caller can log/note it without surfacing raw
        Ollama error text to the user."""
        settings = get_settings()
        model = self.model_for_role(role)

        available, reason = self.provider.available()
        if not available:
            return LocalModelCallResult(
                ok=False, text="", role=role, model_requested=model, model_used=None,
                fallback_used=False, error=reason or "Ollama is not reachable.",
            )

        # ECHO Layer 0 — bounded concurrency: a single local Ollama instance
        # degrades badly under many simultaneous requests, so this caps how
        # many are in flight at once rather than letting them all queue
        # inside Ollama itself with no visibility. A timed-out acquire
        # returns a clean "busy" result instead of hanging indefinitely.
        semaphore = _get_semaphore()
        acquired = semaphore.acquire(timeout=_SEMAPHORE_ACQUIRE_TIMEOUT_SECONDS)
        if not acquired:
            metrics.increment("model_calls_total", provider="ollama", outcome="busy")
            return LocalModelCallResult(
                ok=False, text="", role=role, model_requested=model, model_used=None,
                fallback_used=False, error="Local models are busy right now — please try again in a moment.",
            )
        try:
            try:
                result = self.provider.chat(system_prompt, messages, model=model)
                metrics.increment("model_calls_total", provider="ollama", outcome="success")
                return LocalModelCallResult(
                    ok=True, text=result.text, role=role, model_requested=model, model_used=model,
                    fallback_used=False, error=None, chat_result=result,
                )
            except Exception as exc:
                metrics.increment("model_calls_total", provider="ollama", outcome="failure")
                logger.warning("local model role '%s' (model=%s) failed: %s", role, model, exc)
                default_model = settings.ollama_model
                if settings.local_model_max_retries < 1 or model == default_model:
                    return LocalModelCallResult(
                        ok=False, text="", role=role, model_requested=model, model_used=None,
                        fallback_used=False, error="Local model call failed.",
                    )
                try:
                    result = self.provider.chat(system_prompt, messages, model=default_model)
                    metrics.increment("model_calls_total", provider="ollama", outcome="success_fallback")
                    return LocalModelCallResult(
                        ok=True, text=result.text, role=role, model_requested=model, model_used=default_model,
                        fallback_used=True, error=f"Model for role '{role}' unavailable — used the default model instead.",
                        chat_result=result,
                    )
                except Exception as exc2:
                    metrics.increment("model_calls_total", provider="ollama", outcome="failure")
                    logger.warning("local model default-model fallback also failed: %s", exc2)
                    return LocalModelCallResult(
                        ok=False, text="", role=role, model_requested=model, model_used=None,
                        fallback_used=False, error="Local model call failed.",
                    )
        finally:
            semaphore.release()


def list_installed_models() -> tuple[list[str], str | None]:
    """Calls Ollama's GET /api/tags. Returns (model_names, error) — error is
    a clean, plain-language message (never a raw exception/traceback) when
    Ollama is offline or responds unexpectedly."""
    settings = get_settings()
    try:
        resp = httpx.get(f"{settings.ollama_base_url}/api/tags", timeout=3.0)
        if resp.status_code != 200:
            return [], f"Ollama responded with status {resp.status_code}"
        data = resp.json()
        names = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        return names, None
    except httpx.HTTPError:
        return [], "Ollama not reachable (is it running locally?)"
