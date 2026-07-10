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


def parse_memory_json(raw: str | None) -> dict | None:
    """Parse the model's MEMORY: section into Atlas fields, or None if there's nothing
    worth saving (including on any parse/validation failure — fails closed, never raises).
    """
    if not raw:
        return None
    text = raw.strip()
    if not text or text.strip('."\' ').upper() == "NONE":
        return None

    # Try the raw text first, then fall back to the first {...} block — models
    # frequently wrap the JSON in a code fence or a sentence of preamble/postamble.
    for candidate in (text, _first_json_block(text)):
        if not candidate:
            continue
        data = _try_parse(candidate)
        if data is not None:
            return data
    return None


def _first_json_block(text: str) -> str | None:
    match = _JSON_BLOCK_RE.search(text)
    return match.group(0) if match else None


def _try_parse(candidate: str) -> dict | None:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    content = str(data.get("content") or "").strip()
    if not content:
        return None

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

    return {"content": content, "epistemic_status": status, "confidence": confidence, "tags": tags}
