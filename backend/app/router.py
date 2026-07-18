import logging
import time
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app import usage
from app.config import get_settings
from app.core import metrics
from app.provider_errors import COOLDOWN_CATEGORIES, classify_provider_error
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.azure_openai_provider import AzureOpenAIProvider
from app.providers.base import ChatMessage, ChatResult, ModelProvider
from app.providers.gemini_provider import GeminiProvider
from app.providers.grok_provider import GrokProvider
from app.providers.ollama_provider import OllamaProvider
from app.providers.openai_provider import OpenAIProvider

logger = logging.getLogger(__name__)

# Ollama is local/self-hosted with no quota concept — never tracked. Azure is
# tracked so AZURE_DAILY_REQUEST_LIMIT (a self-imposed cap, separate from
# whatever Azure's own billing allows) can actually be enforced.
_USAGE_TRACKED_PROVIDERS = {"anthropic", "openai", "grok", "gemini", "azure"}

# Priority order for normal (non-FREE_MODE) "auto" mode. FREE_MODE uses its
# own chain — see ModelRouter._auto_candidates().
_PROVIDERS: list[ModelProvider] = [
    AnthropicProvider(),
    OpenAIProvider(),
    GeminiProvider(),
    GrokProvider(),
    AzureOpenAIProvider(),
    OllamaProvider(),
]

# FREE_MODE's provider order: Ollama (local, free, preferred) first, then
# Gemini's free tier, then Azure only if explicitly enabled/configured and
# still under its own daily cap, then Ollama again as a final fallback if
# every cloud option above failed. Anthropic/OpenAI/Grok (paid-only, no free
# tier) are deliberately excluded from this chain even if their keys happen
# to be configured — FREE_MODE only reaches them if the user explicitly pins
# to that provider by name, which bypasses this chain entirely.
_FREE_MODE_ORDER = ["ollama", "gemini", "azure", "ollama"]


class NoProviderAvailableError(Exception):
    pass


class ProviderUnavailableError(Exception):
    pass


# Shown to the user as-is (via HTTPException detail) — deliberately generic.
# Full technical detail (the actual exception each provider raised) is always
# logged server-side via logger.warning below, never dropped, just not shown
# raw in the chat UI.
#
# Two distinct messages: _NO_PROVIDER_MESSAGE covers "nothing was even
# available to try" (no keys configured, Ollama not reachable at all — auto
# mode's loop never attempted a call). _PROVIDERS_FAILED_MESSAGE covers "one
# or more providers were tried and every single one failed" (cloud
# quota/billing/auth errors plus Ollama also being unreachable), which is a
# meaningfully different situation for the user to act on.
_NO_PROVIDER_MESSAGE = "No AI provider is currently available. Check API keys or local Ollama."
_PROVIDERS_FAILED_MESSAGE = (
    "No AI provider is currently available. Cloud providers are unavailable/quota-limited "
    "and Ollama is not running."
)

# Exact wording required when auto mode's final answer came from Ollama after
# at least one cloud provider failed this turn — the user-facing signal that
# a paid provider was skipped, not that anything is actually broken.
_OLLAMA_FALLBACK_NOTE = "Cloud providers were unavailable or quota-limited, so Echo replied using Ollama."


def _track_success(db: Session | None, provider: ModelProvider, elapsed_ms: float | None = None) -> None:
    metrics.increment("model_calls_total", provider=provider.name, outcome="success")
    if elapsed_ms is not None:
        # ECHO Layer 2D — feeds providers/registry.py's measured_avg_latency_ms;
        # a plain read of this counter, no new instrumentation path.
        metrics.record_duration("model_call_duration_ms", elapsed_ms, provider=provider.name)
    if db is not None and provider.name in _USAGE_TRACKED_PROVIDERS:
        usage.record_request(db, provider.name)


def _track_failure(db: Session | None, provider: ModelProvider, exc: Exception) -> None:
    metrics.increment("model_calls_total", provider=provider.name, outcome="failure")
    if db is not None and provider.name in _USAGE_TRACKED_PROVIDERS and usage.is_rate_limit_error(exc):
        usage.record_429(db, provider.name)


def _classify_and_maybe_cooldown(db: Session | None, provider: ModelProvider, exc: Exception) -> str:
    """Classifies the failure and, for categories worth waiting out
    (quota/credit/billing/rate-limit), records a cooldown so auto mode skips
    this provider for a while instead of re-trying a call it already knows
    will fail. Returns the category for the caller's own bookkeeping."""
    category = classify_provider_error(exc)
    if db is not None and category in COOLDOWN_CATEGORIES:
        usage.set_cooldown(db, provider.name, category)
    return category


def _build_fallback_note(
    provider: ModelProvider, rate_limited_this_turn: list[str], cloud_failed_this_turn: bool
) -> str | None:
    if provider.name == "ollama" and cloud_failed_this_turn:
        return _OLLAMA_FALLBACK_NOTE
    if rate_limited_this_turn:
        return f"{', '.join(rate_limited_this_turn)} rate-limited this turn; replied via {provider.name}"
    return None


class ModelRouter:
    def __init__(self, providers: list[ModelProvider] | None = None):
        self.providers = providers or _PROVIDERS

    def get_provider(self, name: str) -> ModelProvider | None:
        return next((p for p in self.providers if p.name == name), None)

    def _azure_within_daily_limit(self, db: Session | None) -> bool:
        settings = get_settings()
        if settings.azure_daily_request_limit is None:
            return True
        if db is None:
            # Can't check without a session — fail open rather than silently
            # blocking Azure for callers that don't pass one (e.g. ad hoc
            # scripts); the request-count-based limit is only meaningful once
            # a db session is available to read it from.
            return True
        return usage.get_daily_request_count(db, "azure") < settings.azure_daily_request_limit

    def _auto_candidates(self, db: Session | None = None) -> list[ModelProvider]:
        """Auto mode's provider order. Ollama is dropped from the normal chain
        when OLLAMA_ALWAYS_AVAILABLE_FALLBACK=false — pinning to "ollama"
        directly still works, this only affects whether auto mode falls back
        to it. FREE_MODE=true replaces the whole chain with _FREE_MODE_ORDER
        (Ollama -> Gemini free tier -> Azure if enabled+within its daily cap
        -> Ollama again), skipping paid-only providers entirely unless the
        user explicitly pins to one by name."""
        settings = get_settings()
        if settings.free_mode:
            order = _FREE_MODE_ORDER
        elif settings.ollama_always_available_fallback:
            order = [p.name for p in self.providers]
        else:
            order = [p.name for p in self.providers if p.name != "ollama"]

        candidates = []
        for name in order:
            provider = self.get_provider(name)
            if provider is None:
                continue
            if provider.name == "azure" and not self._azure_within_daily_limit(db):
                continue
            candidates.append(provider)
        return candidates

    def statuses(self) -> list[dict]:
        out = []
        for p in self.providers:
            available, reason = p.available()
            out.append({"name": p.name, "label": p.label, "available": available, "reason": reason})
        return out

    def chat(
        self,
        preferred: str,
        system_prompt: str,
        messages: list[ChatMessage],
        db: Session | None = None,
    ) -> tuple[ChatResult, str, str | None]:
        """Returns (result, provider_used, fallback_note). fallback_note is set only
        in auto mode, only when a higher-priority provider was skipped this turn
        because it failed (rate limit, quota, credit, billing, etc.) — so the
        caller can surface which provider actually answered and why it wasn't
        the usual one."""

        if preferred == "auto":
            last_error: Exception | None = None
            rate_limited_this_turn: list[str] = []
            cloud_failed_this_turn = False
            for provider in self._auto_candidates(db):
                available, _ = provider.available()
                if not available:
                    continue
                if db is not None and usage.get_active_cooldown(db, provider.name) is not None:
                    logger.info("auto mode: skipping %s, still in cooldown", provider.name)
                    continue
                try:
                    call_start = time.monotonic()
                    result = provider.chat(system_prompt, messages)
                    _track_success(db, provider, elapsed_ms=(time.monotonic() - call_start) * 1000)
                    fallback_note = _build_fallback_note(provider, rate_limited_this_turn, cloud_failed_this_turn)
                    return result, provider.name, fallback_note
                except Exception as exc:
                    # Previously silent — a provider failing (e.g. a rate limit) and
                    # auto mode quietly falling back to a weaker provider (like one
                    # with no vision support) was completely invisible in the logs.
                    logger.warning(
                        "auto mode: %s failed, trying next provider: %s", provider.name, exc
                    )
                    _track_failure(db, provider, exc)
                    category = _classify_and_maybe_cooldown(db, provider, exc)
                    if usage.is_rate_limit_error(exc) or category == "rate_limited":
                        rate_limited_this_turn.append(provider.name)
                    if provider.name != "ollama":
                        cloud_failed_this_turn = True
                    last_error = exc
                    continue
            if last_error:
                raise NoProviderAvailableError(_PROVIDERS_FAILED_MESSAGE) from last_error
            raise NoProviderAvailableError(_NO_PROVIDER_MESSAGE)

        provider = self.get_provider(preferred)
        if provider is None:
            raise ValueError(f"Unknown provider '{preferred}'")
        available, reason = provider.available()
        if not available:
            raise ProviderUnavailableError(f"{provider.label} is unavailable: {reason}")
        if db is not None:
            cooldown = usage.get_active_cooldown(db, provider.name)
            if cooldown is not None:
                raise ProviderUnavailableError(
                    f"{provider.label} is temporarily unavailable after a recent "
                    f"{cooldown.category.replace('_', ' ')} error. Try Auto, another provider, "
                    "or wait a bit before retrying."
                )
        try:
            call_start = time.monotonic()
            result = provider.chat(system_prompt, messages)
            _track_success(db, provider, elapsed_ms=(time.monotonic() - call_start) * 1000)
            return result, provider.name, None
        except Exception as exc:
            logger.warning("pinned provider %s failed: %s", provider.name, exc)
            _track_failure(db, provider, exc)
            _classify_and_maybe_cooldown(db, provider, exc)
            raise ProviderUnavailableError(
                f"{provider.label} is currently unavailable. Try Auto or another provider."
            ) from exc

    def stream_chat(
        self,
        preferred: str,
        system_prompt: str,
        messages: list[ChatMessage],
        db: Session | None = None,
    ) -> Iterator[tuple[str, ModelProvider, str | None]]:
        """Streaming counterpart to chat(): yields (raw_text_chunk, provider,
        fallback_note) tuples as they arrive. fallback_note is only meaningful on
        the first yielded tuple, same convention as chat().

        Fallback only happens *before* any chunk has been produced for a given
        provider attempt — providers are lazy generators, so requesting the first
        chunk is what actually opens the connection, and a failure there is
        treated exactly like chat()'s try/except. Once a chunk has been
        successfully yielded for a provider, this commits to it: a later failure
        mid-stream propagates as an exception rather than silently switching
        providers after the client may have already rendered partial output.
        """
        if preferred == "auto":
            candidates = self._auto_candidates(db)
        else:
            provider = self.get_provider(preferred)
            if provider is None:
                raise ValueError(f"Unknown provider '{preferred}'")
            candidates = [provider]

        last_error: Exception | None = None
        rate_limited_this_turn: list[str] = []
        cloud_failed_this_turn = False

        for provider in candidates:
            available, reason = provider.available()
            if not available:
                if preferred != "auto":
                    raise ProviderUnavailableError(f"{provider.label} is unavailable: {reason}")
                continue

            if db is not None:
                cooldown = usage.get_active_cooldown(db, provider.name)
                if cooldown is not None:
                    if preferred != "auto":
                        raise ProviderUnavailableError(
                            f"{provider.label} is temporarily unavailable after a recent "
                            f"{cooldown.category.replace('_', ' ')} error. Try Auto, another provider, "
                            "or wait a bit before retrying."
                        )
                    logger.info("stream: skipping %s, still in cooldown", provider.name)
                    continue

            gen = provider.stream_chat(system_prompt, messages)
            stream_start = time.monotonic()
            try:
                first_chunk = next(gen)
            except StopIteration:
                first_chunk = None
            except Exception as exc:
                logger.warning(
                    "stream: %s failed before yielding, trying next provider: %s", provider.name, exc
                )
                _track_failure(db, provider, exc)
                category = _classify_and_maybe_cooldown(db, provider, exc)
                if preferred != "auto":
                    raise ProviderUnavailableError(
                        f"{provider.label} is currently unavailable. Try Auto or another provider."
                    ) from exc
                if usage.is_rate_limit_error(exc) or category == "rate_limited":
                    rate_limited_this_turn.append(provider.name)
                if provider.name != "ollama":
                    cloud_failed_this_turn = True
                last_error = exc
                continue

            # Time-to-first-chunk, not total stream duration — the more
            # useful "how fast did this feel" latency signal for streaming.
            _track_success(db, provider, elapsed_ms=(time.monotonic() - stream_start) * 1000)
            fallback_note = _build_fallback_note(provider, rate_limited_this_turn, cloud_failed_this_turn)
            if first_chunk:
                yield first_chunk, provider, fallback_note
            for chunk in gen:
                yield chunk, provider, None
            return

        if last_error:
            raise NoProviderAvailableError(_PROVIDERS_FAILED_MESSAGE) from last_error
        raise NoProviderAvailableError(_NO_PROVIDER_MESSAGE)


router = ModelRouter()
