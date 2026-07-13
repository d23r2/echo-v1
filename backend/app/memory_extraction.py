"""Turns conversation into Atlas memory writes, without a second model call.

Two paths:
- Explicit ("remember that I prefer tea") — detected with a plain regex and saved
  directly from the user's own words. No LLM judgment involved, so it can't be
  silently dropped by a flaky model call or rate limiting.
- Implicit (opportunistic) — Echo's own single chat-completion call is asked to also
  emit a MEMORY: section (see persona.py); this module just has to parse whatever
  comes back, robustly, since models routinely wrap JSON in prose or code fences
  despite instructions not to.
"""

import json
import re
from dataclasses import dataclass

_EXPLICIT_PATTERNS = [
    re.compile(r"\bplease remember\b", re.IGNORECASE),
    re.compile(r"\bremember (that|this)\b", re.IGNORECASE),
    re.compile(r"\bnote (that|this) down\b", re.IGNORECASE),
    re.compile(r"\bkeep in mind (that)?\b", re.IGNORECASE),
    re.compile(r"\bdon'?t forget\b", re.IGNORECASE),
    re.compile(r"\bfor future reference\b", re.IGNORECASE),
    re.compile(r"\bmake a note\b", re.IGNORECASE),
]

_STRIP_PREFIX_RE = re.compile(
    r"^(please\s+)?(remember|note|keep in mind|make a note|don'?t forget)\s*(that|this)?\s*[:,-]?\s*",
    re.IGNORECASE,
)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_VALID_STATUSES = {"Verified", "Inferred", "Hypothesis", "Narrative"}


def is_explicit_remember_request(message: str) -> bool:
    return any(p.search(message) for p in _EXPLICIT_PATTERNS)


def extract_explicit_memory(message: str) -> str:
    """Strip a leading 'remember that / please note / ...' phrase, keep the rest."""
    cleaned = _STRIP_PREFIX_RE.sub("", message.strip(), count=1).strip()
    return cleaned or message.strip()


@dataclass(frozen=True)
class MemoryParseDiagnostic:
    """Why a MEMORY: block did or didn't produce a saved memory — for diagnostics
    only (see app.routers.chat._log_memory_diagnostic). Never changes what gets
    saved; parse_memory_json() below has the exact same save/reject behavior it
    always had, just now expressed as a thin wrapper over the diagnostic-tracking
    version."""

    memory_block_present: bool
    was_none: bool
    json_detected: bool
    parse_succeeded: bool
    rejection_reason: str | None


def parse_memory_json(raw: str | None) -> dict | None:
    """Parse the model's MEMORY: section into Atlas fields, or None if there's nothing
    worth saving (including on any parse/validation failure — fails closed, never raises).
    """
    data, _diagnostic = parse_memory_json_with_diagnostics(raw)
    return data


def parse_memory_json_with_diagnostics(raw: str | None) -> tuple[dict | None, MemoryParseDiagnostic]:
    """Same parsing/validation as parse_memory_json(), but also reports *why*
    nothing was saved when that happens — used for the memory-extraction
    diagnostics log, never to change save/reject behavior."""
    if not raw or not raw.strip():
        return None, MemoryParseDiagnostic(
            memory_block_present=False,
            was_none=False,
            json_detected=False,
            parse_succeeded=False,
            rejection_reason="No MEMORY: block in the model's reply",
        )

    text = raw.strip()
    if text.strip('."\' ').upper() == "NONE":
        return None, MemoryParseDiagnostic(
            memory_block_present=True,
            was_none=True,
            json_detected=False,
            parse_succeeded=False,
            rejection_reason="MEMORY was NONE",
        )

    # Try the raw text first, then fall back to the first {...} block — models
    # frequently wrap the JSON in a code fence or a sentence of preamble/postamble.
    json_detected = bool(text.lstrip().startswith("{") or _first_json_block(text))
    fail_reason: str | None = None
    for candidate in (text, _first_json_block(text)):
        if not candidate:
            continue
        data, reason = _try_parse(candidate)
        if data is not None:
            return data, MemoryParseDiagnostic(
                memory_block_present=True,
                was_none=False,
                json_detected=True,
                parse_succeeded=True,
                rejection_reason=None,
            )
        fail_reason = fail_reason or reason

    return None, MemoryParseDiagnostic(
        memory_block_present=True,
        was_none=False,
        json_detected=json_detected,
        parse_succeeded=False,
        rejection_reason=fail_reason or "MEMORY: block did not contain a JSON object",
    )


def _first_json_block(text: str) -> str | None:
    match = _JSON_BLOCK_RE.search(text)
    return match.group(0) if match else None


def _try_parse(candidate: str) -> tuple[dict | None, str | None]:
    """Returns (parsed_fields, None) on success, or (None, human_readable_reason)
    on failure — the reason is what shows up in the diagnostics log."""
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None, "Malformed JSON"
    if not isinstance(data, dict):
        return None, "MEMORY JSON was not an object"

    content = str(data.get("content") or "").strip()
    if not content:
        return None, "Missing content field"

    status = data.get("epistemic_status")
    if status not in _VALID_STATUSES:
        status = "Inferred"

    try:
        confidence = float(data.get("confidence", 0.6))
    except (TypeError, ValueError):
        confidence = 0.6
    confidence = max(0.0, min(1.0, confidence))

    tags = data.get("tags")
    if not isinstance(tags, list):
        tags = []
    tags = [str(t) for t in tags if isinstance(t, (str, int, float))]

    return {"content": content, "epistemic_status": status, "confidence": confidence, "tags": tags}, None
