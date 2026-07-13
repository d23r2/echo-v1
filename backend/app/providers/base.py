import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass

_FULL_ENVELOPE_RE = re.compile(
    r"REASONING:\s*(.*?)\s*ANSWER:\s*(.*?)\s*MEMORY:\s*(.*)", re.DOTALL | re.IGNORECASE
)
_TRACE_RE = re.compile(r"REASONING:\s*(.*?)\s*ANSWER:\s*(.*)", re.DOTALL | re.IGNORECASE)
_MEMORY_MARKER_RE = re.compile(r"\s*MEMORY:\s*", re.IGNORECASE)


@dataclass
class ChatResult:
    text: str
    reasoning: str | None
    memory_json: str | None = None
    # "complete" | "partial" | "missing" | "malformed" — see split_reasoning_and_answer()
    # and app/envelope_stream.py for how this is computed. Never inferred beyond what
    # the raw text actually contains; a "missing"/"malformed" result never has a
    # fabricated `reasoning` value — it's always None in that case.
    envelope_status: str = "missing"
    envelope_degradation_reason: str | None = None

    @property
    def reasoning_available(self) -> bool:
        return bool(self.reasoning)

    @property
    def memory_block_available(self) -> bool:
        return self.memory_json is not None


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str
    # (mime_type, raw_bytes) pairs — only meaningful on a user message, and only a
    # provider with real vision support (currently just Gemini) does anything with
    # this; others simply ignore it and rely on the text content alone.
    images: list[tuple[str, bytes]] | None = None


def split_reasoning_and_answer(raw: str) -> ChatResult:
    """Persona.py asks every model to emit a `REASONING: ... ANSWER: ... MEMORY: ...`
    envelope (the MEMORY section is optional/older-format-compatible).

    This lets us surface a transparent reasoning trace, and opportunistically extract
    an Atlas memory candidate, from the model's own stated output (not hidden
    chain-of-thought, not a second model call) in a provider-agnostic way. Falls back
    gracefully through two-part envelope, then raw-text-as-answer, if the model didn't
    follow the format — small/local models often don't.
    """
    stripped = raw.strip()

    match = _FULL_ENVELOPE_RE.match(stripped)
    if match:
        reasoning, answer, memory = match.groups()
        return ChatResult(
            text=answer.strip(),
            reasoning=reasoning.strip(),
            memory_json=memory.strip(),
            envelope_status="complete",
        )

    match = _TRACE_RE.match(stripped)
    if match:
        reasoning, answer = match.groups()
        return ChatResult(
            text=answer.strip(),
            reasoning=reasoning.strip(),
            envelope_status="partial",
            envelope_degradation_reason="Model provided REASONING and ANSWER but no MEMORY: block.",
        )

    # Model answered directly with no REASONING:/ANSWER: prefix at all, but may still
    # have appended a MEMORY: block per its instructions (persona.py). Truncate at that
    # marker so the raw JSON never reaches the displayed/saved answer.
    marker = _MEMORY_MARKER_RE.search(stripped)
    if marker:
        return ChatResult(
            text=stripped[: marker.start()].strip(),
            reasoning=None,
            memory_json=stripped[marker.end() :].strip(),
            envelope_status="malformed",
            envelope_degradation_reason=(
                "Model answered directly without a REASONING:/ANSWER: prefix, but attempted "
                "a MEMORY: block afterward — reasoning is unavailable for this reply."
            ),
        )

    return ChatResult(
        text=stripped,
        reasoning=None,
        envelope_status="missing",
        envelope_degradation_reason=(
            "Model did not return the expected REASONING:/ANSWER:/MEMORY: envelope — "
            "reasoning is unavailable for this reply."
        ),
    )


class ModelProvider(ABC):
    name: str
    label: str

    @abstractmethod
    def available(self) -> tuple[bool, str | None]:
        """Return (is_available, reason_if_not)."""

    @abstractmethod
    def chat(self, system_prompt: str, messages: list[ChatMessage]) -> ChatResult:
        ...

    def stream_chat(self, system_prompt: str, messages: list[ChatMessage]) -> Iterator[str]:
        """Yield raw reply text as it becomes available, for POST /api/chat/stream.
        Default: no real token-level streaming — call the existing non-streaming
        chat() and re-emit its already-parsed result as one chunk, reconstructed
        into the same REASONING:/ANSWER:/MEMORY: shape so the caller's envelope
        parser (app/envelope_stream.py) re-derives the same text/reasoning/memory
        AND the same envelope_status — never inventing markers the model didn't
        actually produce. Providers with a cheap native streaming transport
        override this for real incremental delivery (currently just Ollama)."""
        result = self.chat(system_prompt, messages)
        if result.envelope_status == "missing":
            # No envelope at all originally — don't fabricate REASONING:/MEMORY:
            # markers that were never in the model's output; yielding the raw
            # answer text lets the receiving parser correctly re-derive "missing"
            # too, instead of a fake "complete" classification.
            yield result.text
            return
        reasoning_part = result.reasoning if result.reasoning is not None else ""
        lines = [f"REASONING: {reasoning_part}", f"ANSWER: {result.text}"]
        if result.memory_json is not None:
            # Omitted (not "MEMORY: NONE") when the model never produced a MEMORY:
            # block at all — collapsing that into "NONE" would make the receiving
            # parser think the model explicitly said "nothing to remember", which
            # is a different, meaningful diagnostic state (see memory_extraction.py).
            lines.append(f"MEMORY: {result.memory_json}")
        yield "\n".join(lines)
