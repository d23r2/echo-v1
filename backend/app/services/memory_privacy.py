"""ECHO Layer 1 — Memory Sensitivity and Privacy Engine (Phase 16).

Deterministic, regex/keyword-only, no model call — same style as
memory_conflicts.py/preference_detection.py/dependency_patterns.py. Gates
what memory capture is allowed to do *before* anything is written, per the
milestone's own non-negotiable rules 4/5/9: never auto-store secrets, never
auto-store highly sensitive personal information without explicit request,
never let memory be used to manipulate the user (out of scope for a
classifier, enforced by persona.py's directives instead).

This module answers five questions and nothing else:
- classify_sensitivity(content) -> how sensitive is this text?
- can_store(sensitivity, explicit_request) -> is storing it allowed right now?
- can_retrieve(sensitivity, purpose) -> should retrieval surface it for this purpose?
- can_display(sensitivity, developer_mode) -> should the UI show it plainly?
- can_export(sensitivity) -> should export include it?
- redact_for_log(text) -> the text, safe to write to a log line.
"""

import re

from app.core.logging import redact as _log_redact

# ---- Secret detection: content that must NEVER be stored as a normal memory,
# even if the user explicitly asks (rule: "Secret content must never be
# stored as normal memory"). Deliberately broader/more aggressive than
# core/logging.py's redaction patterns, since the cost of a false positive
# here (asking the user to store it themselves) is much lower than the cost
# of a false negative (a real credential landing in the DB and Chroma).
_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|access[_-]?token|refresh[_-]?token|"
               r"private[_-]?key|recovery[_-]?code|auth[_-]?token)\b\s*[:=]\s*\S{4,}"),
    re.compile(r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b"),  # card-number-shaped
    re.compile(r"(?i)\b\d{3}-\d{2}-\d{4}\b"),  # SSN-shaped
]

# ---- Highly sensitive categories: allowed only on explicit user request or
# an existing approved policy, never auto-captured from opportunistic
# extraction (see chat.py's _extract_memory()).
_HIGHLY_SENSITIVE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(diagnosed with|my (medication|prescription|therapist|psychiatrist)|"
               r"mental health|hiv|std|medical (condition|record|history))\b", re.IGNORECASE),
    re.compile(r"\b(lawsuit|criminal record|arrested|legal charges|court case)\b", re.IGNORECASE),
    re.compile(r"\b(bank account number|routing number|account balance|credit score)\b", re.IGNORECASE),
    re.compile(r"\b(passport number|driver'?s licen[cs]e number|national id|social security number)\b", re.IGNORECASE),
    re.compile(r"\b(my (home )?address is|i live at)\b.*\d", re.IGNORECASE),
]

# ---- Ordinary-personal signals: plainly personal but not high-stakes — most
# preference/profile statements land here by default.
_PRIVATE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(my (relationship|dating|marriage|divorce)|feeling (depressed|anxious|suicidal))\b", re.IGNORECASE),
]

_EXPLICIT_DO_NOT_REMEMBER = [
    re.compile(r"\bdo not remember\b", re.IGNORECASE),
    re.compile(r"\bdon'?t remember (this|that)\b", re.IGNORECASE),
    re.compile(r"\bdon'?t save (this|that)\b", re.IGNORECASE),
    re.compile(r"\bnot for memory\b", re.IGNORECASE),
    re.compile(r"\bdo not remember anything from this conversation\b", re.IGNORECASE),
]

_FORGET_REQUEST = [
    re.compile(r"\bforget (that|this|it)\b", re.IGNORECASE),
    re.compile(r"\bdelete (that|this) memory\b", re.IGNORECASE),
    re.compile(r"\bdo not use (that|this) again\b", re.IGNORECASE),
]

SensitivityLevel = str  # "public" | "ordinary_personal" | "private" | "highly_sensitive" | "secret"


def is_secret(content: str) -> bool:
    """True if `content` looks like it contains a credential/secret. Never
    raises — a classifier bug must fail toward NOT storing, not toward
    silently storing a real secret, so callers should treat an exception
    here as "treat as secret" (see can_store's own try/except)."""
    if not content:
        return False
    return any(p.search(content) for p in _SECRET_PATTERNS)


def classify_sensitivity(content: str) -> SensitivityLevel:
    """Never raises — an unexpected input degrades to the safest
    classification (highly_sensitive), never to "public"."""
    try:
        if not content or not content.strip():
            return "ordinary_personal"
        if is_secret(content):
            return "secret"
        if any(p.search(content) for p in _HIGHLY_SENSITIVE_PATTERNS):
            return "highly_sensitive"
        if any(p.search(content) for p in _PRIVATE_PATTERNS):
            return "private"
        return "ordinary_personal"
    except Exception:
        return "highly_sensitive"


def detect_do_not_remember(message: str) -> bool:
    """'Do not remember the next thing I say' / 'don't save this' — must
    prevent storage of whatever follows (see chat.py integration)."""
    return bool(message) and any(p.search(message) for p in _EXPLICIT_DO_NOT_REMEMBER)


def detect_forget_request(message: str) -> bool:
    """'Forget that' / 'delete this memory' — should initiate a
    deletion/archival workflow, not just skip future capture."""
    return bool(message) and any(p.search(message) for p in _FORGET_REQUEST)


def can_store(sensitivity: SensitivityLevel, *, explicit_request: bool) -> tuple[bool, str]:
    """Returns (allowed, reason). `explicit_request` means the user directly
    asked ECHO to remember this specific content (not just that the message
    happens to look durable) — the only thing that can unlock storing
    highly_sensitive content. Secret content is never allowed, full stop."""
    if sensitivity == "secret":
        return False, "Content looks like a credential or secret and is never stored as memory."
    if sensitivity == "highly_sensitive" and not explicit_request:
        return False, "Highly sensitive personal information requires an explicit remember request."
    return True, ""


def can_retrieve(sensitivity: SensitivityLevel, *, purpose: str = "general") -> bool:
    """Sensitive memories should not be injected into the prompt unless the
    turn is genuinely about that topic — `purpose` is a coarse hint
    (memory_retrieval.py passes "general" for ordinary chat context, and a
    more specific purpose when a request is unambiguously about that
    memory's own subject). Secret-classified rows should never exist after
    can_store's gate, but this stays defensive regardless."""
    if sensitivity == "secret":
        return False
    if sensitivity == "highly_sensitive":
        return purpose != "general"
    return True


def can_display(sensitivity: SensitivityLevel, *, developer_mode: bool = False) -> bool:
    """Whether the Memory Center should show this memory's raw content
    plainly vs. requiring an explicit reveal action. Developer mode never
    unlocks secret content (there shouldn't be any stored) but does allow
    inspecting highly_sensitive rows directly, matching this app's existing
    "developer mode sees more diagnostics" pattern."""
    if sensitivity == "secret":
        return False
    if sensitivity == "highly_sensitive":
        return developer_mode
    return True


def can_export(sensitivity: SensitivityLevel) -> bool:
    """Export should never include secret or highly_sensitive content by
    default (Phase 19's "warn before including sensitive memory")."""
    return sensitivity not in ("secret", "highly_sensitive")


def redact_for_log(text: str) -> str:
    """Delegates to core.logging.redact() — one redaction implementation,
    not two competing ones."""
    return _log_redact(text)
