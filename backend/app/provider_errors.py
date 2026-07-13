"""Classifies a provider failure into a safe, actionable category — text-pattern
+ HTTP-status based, not tied to any one SDK's exception shape (anthropic/openai
raise typed errors with `.status_code`; httpx.HTTPStatusError — used by the
Gemini/Azure providers — exposes it via `.response.status_code`).

This is purely diagnostic/routing information: app/router.py decides what to do
with a category (fall back, apply a cooldown, etc.), and callers must never put
the raw exception text in front of the user — only a clean category-derived
message. See app/router.py's _NO_PROVIDER_MESSAGE and friends.
"""

import re
from typing import Literal

ErrorCategory = Literal[
    "rate_limited",
    "quota_exceeded",
    "credit_exhausted",
    "billing_required",
    "auth_failed",
    "provider_unavailable",
    "network_error",
    "invalid_request",
    "unknown_error",
]

_CREDIT_PATTERNS = [
    re.compile(r"credits?\s+exhausted", re.IGNORECASE),
    re.compile(r"insufficient credit", re.IGNORECASE),
]
_BILLING_PATTERNS = [
    re.compile(r"billing limit reached", re.IGNORECASE),
    re.compile(r"billing hard limit", re.IGNORECASE),
    re.compile(r"payment required", re.IGNORECASE),
    re.compile(r"usage limit", re.IGNORECASE),
]
_QUOTA_PATTERNS = [
    re.compile(r"insufficient quota", re.IGNORECASE),
    re.compile(r"free tier exhausted", re.IGNORECASE),
    # Covers both word orders real providers use, e.g. OpenAI's actual message
    # "You exceeded your current quota, please check your plan and billing
    # details." as well as "quota exceeded"/"account quota exceeded".
    re.compile(r"\bquota\b.{0,15}\bexceeded\b|\bexceeded\b.{0,15}\bquota\b", re.IGNORECASE),
]

# Categories where retrying the exact same provider again right away is
# pointless — worth a cooldown so the router doesn't keep paying the latency
# cost of a doomed call every single turn. auth_failed/invalid_request are
# persistent config problems a cooldown wouldn't help with; network_error and
# provider_unavailable are transient in a different way (may recover any
# second) so aren't cooled down either — only true "wait for quota to refill"
# categories are.
COOLDOWN_CATEGORIES: frozenset[ErrorCategory] = frozenset(
    {"rate_limited", "quota_exceeded", "credit_exhausted", "billing_required"}
)


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    if response is not None:
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
    return None


def classify_provider_error(exc: Exception) -> ErrorCategory:
    """Never raises — worst case falls through to 'unknown_error'."""
    text = str(exc)
    status = _status_code(exc)

    # Text patterns first: providers frequently return a 429 for both plain
    # rate limiting AND quota/credit exhaustion, so the message text is the
    # only reliable way to tell those apart.
    if any(p.search(text) for p in _CREDIT_PATTERNS):
        return "credit_exhausted"
    if any(p.search(text) for p in _BILLING_PATTERNS):
        return "billing_required"
    if any(p.search(text) for p in _QUOTA_PATTERNS):
        return "quota_exceeded"

    if status == 402:
        return "billing_required"
    if status == 429:
        return "rate_limited"
    if status in (401, 403):
        return "auth_failed"

    type_name = type(exc).__name__
    module_name = type(exc).__module__
    if isinstance(exc, (ConnectionError, TimeoutError)) or (
        module_name.startswith("httpx") and ("Connect" in type_name or "Timeout" in type_name)
    ):
        return "network_error"

    if status is not None and 400 <= status < 500:
        return "invalid_request"

    return "unknown_error"
