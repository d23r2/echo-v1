"""Deterministic detection of durable user preference / learning-style statements
that aren't phrased as an explicit "remember that..." request (see
memory_extraction.is_explicit_remember_request for that separate, narrower path)
but still describe how the user wants Echo to behave going forward — e.g. "when
you explain things to me, lead with an example" or "I prefer step-by-step
explanations". Regex-only, no model calls, fully deterministic and local — same
style as dependency_patterns.py and memory_conflicts.py.

The key distinction this makes: a *durable, general* instruction ("from now on...",
"I prefer...", "when you explain... to me") vs. a *one-off* request scoped to the
current message ("can you explain this with an example?"). Only the former is
memory-worthy — a casual one-off request isn't a standing preference just because
it mentions "explain" or "example".
"""

import re
from dataclasses import dataclass

_LEARNING_STYLE_KEYWORDS = re.compile(
    r"\b(explain|explanation|explanations|teach|teaching|learn|learning|theory|"
    r"example|examples|step-by-step|walk me through)\b",
    re.IGNORECASE,
)

_TECHNICAL_KEYWORDS = re.compile(r"\btechnical\b", re.IGNORECASE)

# Each of these signals a *durable/general* instruction, not a one-off request
# about the current message. "Can you explain this?" matches none of these.
_DURABILITY_PATTERNS = [
    re.compile(r"\bwhen you (explain|describe|teach|answer|respond|walk me through)\b", re.IGNORECASE),
    re.compile(r"\bi learn better\b", re.IGNORECASE),
    re.compile(r"\bi prefer\b", re.IGNORECASE),
    re.compile(r"\bi'?d rather\b", re.IGNORECASE),
    re.compile(r"\bfrom now on\b", re.IGNORECASE),
    re.compile(r"\bnext time\b", re.IGNORECASE),
    re.compile(r"\bgoing forward\b", re.IGNORECASE),
    re.compile(r"\bin the future\b", re.IGNORECASE),
    re.compile(r"\balways\b", re.IGNORECASE),
    re.compile(r"\bdon'?t (start|begin|open|lead) with\b", re.IGNORECASE),
]


@dataclass(frozen=True)
class PreferenceDetection:
    content: str
    tags: list[str]
    source: str  # "explicit_user_preference" | "learning_style_detection"


def detect_preference_statement(message: str) -> PreferenceDetection | None:
    """Returns a PreferenceDetection if `message` reads as a durable user
    preference/learning-style instruction, or None otherwise. Never raises."""
    if not message or not any(p.search(message) for p in _DURABILITY_PATTERNS):
        return None

    is_learning_style = bool(_LEARNING_STYLE_KEYWORDS.search(message))

    tags = ["user-stated"]
    if is_learning_style:
        tags.append("learning_style")
        if re.search(r"\bexplain|\bexplanation", message, re.IGNORECASE):
            tags.append("explanation_style")
        if _TECHNICAL_KEYWORDS.search(message):
            tags.append("technical_explanations")

    source = "learning_style_detection" if is_learning_style else "explicit_user_preference"

    return PreferenceDetection(content=message.strip(), tags=tags, source=source)
