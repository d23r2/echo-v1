"""Fake ModelProvider implementations for router tests — no real network calls,
no API keys required. Shared between test_router_fallback.py and anything else
that needs a controllable provider.
"""

from collections.abc import Iterator

from app.providers.base import ChatMessage, ChatResult, ModelProvider, split_reasoning_and_answer


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
        chat_result: ChatResult | None = None,
        stream_chunks: list[str] | None = None,
        stream_raises_after: int | None = None,
    ):
        self.name = name
        self.label = label or name
        self._available = available
        self._unavailable_reason = unavailable_reason
        self._raises = raises
        self._response_text = response_text
        # If set, chat() returns this exact ChatResult (full control over
        # reasoning/memory_json/envelope_status) instead of building a plain
        # text-only, no-envelope result from response_text.
        self._chat_result = chat_result
        # If set, stream_chat() yields these raw chunks one at a time instead of
        # falling back to the base class's single-reconstructed-chunk default —
        # lets tests exercise real incremental streaming without needing Ollama.
        self._stream_chunks = stream_chunks
        # If set, raise self._raises after yielding this many stream chunks
        # (0 = fail before any chunk, matching a connection-open failure).
        self._stream_raises_after = stream_raises_after
        self.chat_call_count = 0
        self.stream_call_count = 0
        # Records the `model` kwarg from the most recent chat()/stream_chat()
        # call — lets role-based-routing tests (LocalModelRouter) assert which
        # model name was actually requested without needing a real Ollama.
        self.last_model_requested: str | None = None
        self.system_prompts: list[str] = []

    def available(self) -> tuple[bool, str | None]:
        return self._available, self._unavailable_reason

    def chat(self, system_prompt: str, messages: list[ChatMessage], model: str | None = None) -> ChatResult:
        self.chat_call_count += 1
        self.last_model_requested = model
        self.system_prompts.append(system_prompt)
        if self._raises is not None:
            raise self._raises
        if self._chat_result is not None:
            return self._chat_result
        # Route through the real parser, same as every actual provider's chat()
        # does — so envelope_status/envelope_degradation_reason are computed
        # faithfully instead of silently defaulting to "missing reason: None".
        # `response_text` without any REASONING:/ANSWER:/MEMORY: markers parses
        # to the exact same .text unchanged, so this doesn't affect existing
        # tests that only check .text.
        return split_reasoning_and_answer(self._response_text)

    def stream_chat(self, system_prompt: str, messages: list[ChatMessage], model: str | None = None) -> Iterator[str]:
        self.stream_call_count += 1
        self.last_model_requested = model
        if self._stream_chunks is None:
            yield from super().stream_chat(system_prompt, messages, model=model)
            return
        for i, piece in enumerate(self._stream_chunks):
            if self._stream_raises_after is not None and i == self._stream_raises_after:
                raise self._raises
            yield piece
        if self._stream_raises_after is not None and self._stream_raises_after >= len(self._stream_chunks):
            raise self._raises
