import re
from abc import ABC, abstractmethod
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
        return ChatResult(text=answer.strip(), reasoning=reasoning.strip(), memory_json=memory.strip())

    match = _TRACE_RE.match(stripped)
    if match:
        reasoning, answer = match.groups()
        return ChatResult(text=answer.strip(), reasoning=reasoning.strip())

    # Model answered directly with no REASONING:/ANSWER: prefix at all, but may still
    # have appended a MEMORY: block per its instructions (persona.py). Truncate at that
    # marker so the raw JSON never reaches the displayed/saved answer.
    marker = _MEMORY_MARKER_RE.search(stripped)
    if marker:
        return ChatResult(
            text=stripped[: marker.start()].strip(),
            reasoning=None,
            memory_json=stripped[marker.end() :].strip(),
        )

    return ChatResult(text=stripped, reasoning=None)


class ModelProvider(ABC):
    name: str
    label: str

    @abstractmethod
    def available(self) -> tuple[bool, str | None]:
        """Return (is_available, reason_if_not)."""

    @abstractmethod
    def chat(self, system_prompt: str, messages: list[ChatMessage]) -> ChatResult:
        ...
