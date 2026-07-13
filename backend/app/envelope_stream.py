"""Incremental REASONING:/ANSWER:/MEMORY: envelope parsing for streamed chat
replies (Goal 11). Providers stream raw text pieces as they arrive; this class
figures out, chunk by chunk, which pieces belong to the user-facing ANSWER
section — the only thing ever safe to stream straight to the client — while
REASONING and MEMORY stay buffered server-side until the reply is complete.

MEMORY is never streamed, malformed or not: the state machine only ever exposes
text once it has entered the ANSWER section, and stops exposing anything the
moment a MEMORY: marker is seen. If a model never emits recognizable envelope
markers at all, this falls back to streaming its raw output directly rather
than showing the user nothing.

result() is built entirely from this parser's own tracked marker positions,
never by re-running split_reasoning_and_answer() (base.py's non-streaming
parser) against the full raw text — that regex requires REASONING: to precede
ANSWER:, which is stricter than what this class needs to have already started
streaming live. Re-parsing with a stricter rule could disagree with what was
already sent to the client; using the same positions for both guarantees the
streamed preview and the saved message always agree.
"""

import re

from app.providers.base import ChatResult, split_reasoning_and_answer

_ANSWER_RE = re.compile(r"ANSWER:", re.IGNORECASE)
_MEMORY_RE = re.compile(r"\n?MEMORY:", re.IGNORECASE)
_REASONING_RE = re.compile(r"REASONING:", re.IGNORECASE)
_REASONING_PREFIX_RE = re.compile(r"REASONING:\s*", re.IGNORECASE)

# How many raw characters to tolerate with neither REASONING: nor ANSWER: having
# appeared yet before concluding the model isn't going to follow the envelope at
# all. Generous enough to cover normal token-by-token arrival of "REASONING:"
# itself; once REASONING: has been seen at all, there's no cap on how long we'll
# wait for ANSWER: (a real reasoning section can legitimately run long).
_FALLBACK_THRESHOLD = 80

# Never emit the last few characters of the answer-so-far immediately — hold
# them back until either more text confirms they're not the start of a
# "MEMORY:" marker, or the stream ends. Without this, a marker split across two
# provider chunks (e.g. "...done\nMEM" | "ORY: {...}") would leak the "MEM"
# fragment to the client before it's recognized as part of the marker.
_HOLD_BACK = len("\nMEMORY:") + 2


class EnvelopeStreamParser:
    def __init__(self) -> None:
        self.raw = ""
        self._state = "before_answer"  # before_answer -> in_answer -> after_answer
        self._answer_marker_start: int | None = None  # position of "ANSWER:" itself
        self._answer_start = 0  # position of the first real answer character
        self._answer_end_pos: int | None = None  # set once a MEMORY: marker is found
        self._memory_content_start: int | None = None  # position right after "MEMORY:"
        self._emitted_len = 0
        self._fallback = False

    def feed(self, chunk: str) -> str:
        """Feed the next raw text chunk; returns any new ANSWER-section text this
        chunk makes available to stream to the client (may be empty)."""
        if not chunk:
            return ""
        self.raw += chunk

        if self._state == "after_answer":
            return ""

        if self._state == "before_answer":
            match = _ANSWER_RE.search(self.raw)
            if match:
                self._state = "in_answer"
                self._answer_marker_start = match.start()
                self._answer_start = match.end()
            elif not _REASONING_RE.search(self.raw) and len(self.raw) > _FALLBACK_THRESHOLD:
                # Doesn't look like it's heading toward the envelope at all —
                # better to stream something than leave the user staring at
                # nothing until the whole reply finishes.
                self._fallback = True
                self._state = "in_answer"
                self._answer_marker_start = 0
                self._answer_start = 0
            else:
                return ""

        # Skip whitespace right after the ANSWER: marker (or at the very start,
        # in fallback mode) character by character as it arrives — only while
        # nothing has been emitted yet, so this never touches whitespace that's
        # legitimately part of the answer later on. Doing this here (rather than
        # via \s* on the marker regex) keeps behavior identical whether the
        # marker and its trailing space arrive in one chunk or split across many.
        if self._emitted_len == 0:
            while self._answer_start < len(self.raw) and self.raw[self._answer_start] in " \t\r\n":
                self._answer_start += 1

        already_emitted_to = self._answer_start + self._emitted_len
        memory_match = _MEMORY_RE.search(self.raw, self._answer_start)
        if memory_match:
            end = memory_match.start()
            self._state = "after_answer"
            self._answer_end_pos = end
            self._memory_content_start = memory_match.end()
        else:
            end = max(already_emitted_to, len(self.raw) - _HOLD_BACK)

        new_text = self.raw[already_emitted_to:end]
        self._emitted_len += len(new_text)
        return new_text

    def result(self) -> ChatResult:
        """Call once the stream is exhausted."""
        answer_end = self._answer_end_pos if self._answer_end_pos is not None else len(self.raw)
        memory_json = (
            self.raw[self._memory_content_start :].strip()
            if self._memory_content_start is not None
            else None
        )

        if self._fallback:
            # No REASONING:/ANSWER: markers looked real early on, so there's no
            # reasoning to extract — but if a MEMORY: marker still turned up
            # later (e.g. a model that answers directly, then tries to bolt on
            # an envelope as an afterthought), the answer must still be cut
            # there. Never fall back to the *entire* raw text once a memory
            # marker has been found — that would leak its JSON into the saved,
            # user-visible answer.
            return ChatResult(
                text=self.raw[self._answer_start : answer_end].strip(),
                reasoning=None,
                memory_json=memory_json,
            )

        if self._answer_marker_start is None:
            # ANSWER: never appeared at all, and the length-based fallback never
            # triggered either (e.g. a very short cut-off reply) — same
            # last-resort behavior as the non-streaming parser.
            return split_reasoning_and_answer(self.raw)

        reasoning_text = self.raw[: self._answer_marker_start]
        prefix_match = _REASONING_PREFIX_RE.match(reasoning_text)
        reasoning = reasoning_text[prefix_match.end() :].strip() if prefix_match else None
        if reasoning == "":
            reasoning = None

        answer_text = self.raw[self._answer_start : answer_end].strip()

        return ChatResult(text=answer_text, reasoning=reasoning, memory_json=memory_json)
