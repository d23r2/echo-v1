"""Fake ModelProvider implementations for router tests — no real network calls,
no API keys required. Shared between test_router_fallback.py and anything else
that needs a controllable provider.
"""

from collections.abc import Iterator

from app.providers.base import ChatMessage, ChatResult, ModelProvider


class FakeRateLimitError(Exception):
    """Mimics what app.usage.is_rate_limit_error() looks for — anthropic/openai's
    SDK errors set .status_code directly; this does the same without needing a
    real SDK exception."""

    status_code = 429


class FakeProviderError(Exception):
    """A generic (non-rate-limit) provider failure — e.g. a bad request or a
    transient network error that isn't a 429."""


class FakeProvider(ModelProvider):
    def __init__(
        self,
        name: str,
        *,
        label: str | None = None,
        available: bool = True,
        unavailable_reason: str | None = None,
        raises: Exception | None = None,
        response_text: str = "ok",
        stream_chunks: list[str] | None = None,
        stream_raises_after: int | None = None,
    ):
        self.name = name
        self.label = label or name
        self._available = available
        self._unavailable_reason = unavailable_reason
        self._raises = raises
        self._response_text = response_text
        # If set, stream_chat() yields these raw chunks one at a time instead of
        # falling back to the base class's single-reconstructed-chunk default —
        # lets tests exercise real incremental streaming without needing Ollama.
        self._stream_chunks = stream_chunks
        # If set, raise self._raises after yielding this many stream chunks
        # (0 = fail before any chunk, matching a connection-open failure).
        self._stream_raises_after = stream_raises_after
        self.chat_call_count = 0
        self.stream_call_count = 0

    def available(self) -> tuple[bool, str | None]:
        return self._available, self._unavailable_reason

    def chat(self, system_prompt: str, messages: list[ChatMessage]) -> ChatResult:
        self.chat_call_count += 1
        if self._raises is not None:
            raise self._raises
        return ChatResult(text=self._response_text, reasoning=None)

    def stream_chat(self, system_prompt: str, messages: list[ChatMessage]) -> Iterator[str]:
        self.stream_call_count += 1
        if self._stream_chunks is None:
            yield from super().stream_chat(system_prompt, messages)
            return
        for i, piece in enumerate(self._stream_chunks):
            if self._stream_raises_after is not None and i == self._stream_raises_after:
                raise self._raises
            yield piece
        if self._stream_raises_after is not None and self._stream_raises_after >= len(self._stream_chunks):
            raise self._raises
