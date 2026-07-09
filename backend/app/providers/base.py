import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

_TRACE_RE = re.compile(r"REASONING:\s*(.*?)\s*ANSWER:\s*(.*)", re.DOTALL | re.IGNORECASE)


@dataclass
class ChatResult:
    text: str
    reasoning: str | None


@dataclass
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


def split_reasoning_and_answer(raw: str) -> ChatResult:
    """Persona.py asks every model to emit a `REASONING: ... ANSWER: ...` envelope.

    This lets us surface a transparent reasoning trace from the model's own stated
    output (not hidden chain-of-thought) in a provider-agnostic way. Falls back to
    treating the whole response as the answer if the model didn't follow the format.
    """
    match = _TRACE_RE.match(raw.strip())
    if match:
        reasoning, answer = match.groups()
        return ChatResult(text=answer.strip(), reasoning=reasoning.strip())
    return ChatResult(text=raw.strip(), reasoning=None)


class ModelProvider(ABC):
    name: str
    label: str

    @abstractmethod
    def available(self) -> tuple[bool, str | None]:
        """Return (is_available, reason_if_not)."""

    @abstractmethod
    def chat(self, system_prompt: str, messages: list[ChatMessage]) -> ChatResult:
        ...
