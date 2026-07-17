"""ECHO Layer 0 — structured logging + secret redaction.

Every module already uses `logging.getLogger(__name__)` (the established
convention in this codebase — see router.py, chat.py, action_system.py,
etc.). This module doesn't replace that; it configures the root logger once
at startup (see main.py's lifespan) with a formatter that's either compact
dev-readable text or structured JSON-ish output, and attaches a redaction
filter so a secret can never reach stdout/a log file even if some future
code accidentally logs a settings object or a raw exception containing one.

Never logs by default: full user messages, raw prompt content, API keys,
bearer tokens, authorization headers, passwords. `log_event()` is the
opt-in structured helper for the safe fields (request id, conversation id,
action/tool run id, provider id, elapsed time, error category) — nothing
routes user content into it implicitly.
"""

import logging
import re
import sys
import time
from contextvars import ContextVar

# ============================================================================
# Redaction
# ============================================================================

# Ordered (pattern, replacement) — checked against the fully-formatted log
# line, not just known field names, so a secret embedded inside a raw
# exception message (e.g. an HTTP client library echoing the request it
# just made) is still caught.
_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[A-Za-z0-9_-]{10,}"), "sk-***REDACTED***"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._-]{10,}", re.IGNORECASE), "Bearer ***REDACTED***"),
    (re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]{10,}"), r"\1***REDACTED***"),
    (re.compile(r"(?i)((?:api[_-]?key|secret|password|token)['\"]?\s*[:=]\s*['\"]?)[^\s'\",}]{4,}"), r"\1***REDACTED***"),
]


def redact(text: str) -> str:
    """Never raises — a redaction bug must never break logging itself."""
    if not text:
        return text
    try:
        result = text
        for pattern, replacement in _REDACTION_PATTERNS:
            result = pattern.sub(replacement, result)
        return result
    except Exception:
        return text


class RedactingFilter(logging.Filter):
    """Applied to every handler — redacts the fully-rendered message, not
    just record.msg, so %-style args and any extra fields are covered too."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            pass
        return True


# ============================================================================
# Formatters
# ============================================================================


class _DevFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = _extract_extras(record)
        if extras:
            extra_str = " ".join(f"{k}={v}" for k, v in extras.items())
            return f"{base} | {extra_str}"
        return base


class _StructuredFormatter(logging.Formatter):
    """Compact key=value structured output (not full JSON — avoids adding a
    JSON-logging dependency for a local-first single-process app; still
    trivially greppable/parseable). Order: timestamp, level, logger, event,
    then any extras."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, "%Y-%m-%dT%H:%M:%S")
        parts = [
            f"ts={timestamp}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f'msg="{record.getMessage()}"',
        ]
        for key, value in _extract_extras(record).items():
            parts.append(f"{key}={value}")
        if record.exc_info:
            parts.append(f'error_category={getattr(record, "error_category", "INTERNAL_ERROR")}')
        return " ".join(parts)


_SAFE_EXTRA_KEYS = (
    "request_id",
    "conversation_id",
    "action_run_id",
    "tool_run_id",
    "provider_id",
    "elapsed_ms",
    "error_category",
    "event",
)


def _extract_extras(record: logging.LogRecord) -> dict:
    return {key: getattr(record, key) for key in _SAFE_EXTRA_KEYS if hasattr(record, key)}


# ============================================================================
# Setup
# ============================================================================

_configured = False


def configure_logging(*, level: str = "INFO", structured: bool = False) -> None:
    """Idempotent — safe to call more than once (e.g. once from main.py's
    lifespan, once again from a test fixture) without duplicating handlers."""
    global _configured
    root = logging.getLogger()
    root.setLevel(level.upper())

    if _configured:
        return

    handler = logging.StreamHandler(stream=sys.stdout)
    formatter: logging.Formatter = (
        _StructuredFormatter() if structured else _DevFormatter(fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    handler.setFormatter(formatter)
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    _configured = True


# ============================================================================
# Structured event helper + request-scoped context
# ============================================================================

# Populated by the request-ID middleware (see core/errors.py) for the
# duration of one request — log_event() picks it up automatically so call
# sites don't need to thread request_id through every function signature.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    conversation_id: str | None = None,
    action_run_id: str | None = None,
    tool_run_id: str | None = None,
    provider_id: str | None = None,
    elapsed_ms: float | None = None,
    error_category: str | None = None,
) -> None:
    """The one sanctioned way to emit a structured event with safe context
    fields. Deliberately has no `message`/`prompt`/`content` parameter —
    nothing here can accidentally carry raw user text into logs."""
    extra = {"event": event, "request_id": request_id_var.get()}
    if conversation_id:
        extra["conversation_id"] = conversation_id
    if action_run_id:
        extra["action_run_id"] = action_run_id
    if tool_run_id:
        extra["tool_run_id"] = tool_run_id
    if provider_id:
        extra["provider_id"] = provider_id
    if elapsed_ms is not None:
        extra["elapsed_ms"] = round(elapsed_ms, 1)
    if error_category:
        extra["error_category"] = error_category
    extra = {k: v for k, v in extra.items() if v is not None}
    logger.log(level, event, extra=extra)


class Timer:
    """Tiny context-manager for elapsed_ms — `with Timer() as t: ...` then
    `t.elapsed_ms`. No dependency, just time.monotonic() bookkeeping."""

    def __enter__(self) -> "Timer":
        self._start = time.monotonic()
        self.elapsed_ms = 0.0
        return self

    def __exit__(self, *exc_info) -> None:
        self.elapsed_ms = (time.monotonic() - self._start) * 1000
