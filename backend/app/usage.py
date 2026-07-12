"""Per-provider daily request counters and 429 tracking.

Deliberately does not hardcode any provider's rate limits — tiers/accounts/models
vary and change over time. This only records what actually happened (a successful
call, or a real 429 response) and lets the caller react to that.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import ProviderUsageDaily

# Gemini resets its free-tier quota at midnight Pacific. Anthropic/OpenAI/Grok don't
# publish a fixed reset convention the same way, so midnight UTC is used as a
# reasonable default for those rather than guessing wrong.
_PROVIDER_RESET_TZ = {
    "gemini": ZoneInfo("America/Los_Angeles"),
    "anthropic": timezone.utc,
    "openai": timezone.utc,
    "grok": timezone.utc,
}


def _date_key(provider: str) -> str:
    tz = _PROVIDER_RESET_TZ.get(provider, timezone.utc)
    return datetime.now(tz).strftime("%Y-%m-%d")


def _as_utc_isoformat(dt: datetime) -> str:
    # SQLite drops tzinfo on read-back even for a DateTime(timezone=True) column, so
    # a value written via datetime.now(timezone.utc) comes back naive. Without this,
    # the ISO string has no offset and a browser's `new Date(...)` parses it as local
    # time instead of UTC — silently corrupting the "is this recent" comparison the
    # frontend does against last_429_at by however many hours off UTC the browser is.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _get_or_create_row(db: Session, provider: str) -> ProviderUsageDaily:
    date_key = _date_key(provider)
    row = (
        db.query(ProviderUsageDaily)
        .filter_by(provider=provider, date_key=date_key)
        .first()
    )
    if row is None:
        row = ProviderUsageDaily(provider=provider, date_key=date_key, request_count=0)
        db.add(row)
    return row


def record_request(db: Session, provider: str) -> None:
    row = _get_or_create_row(db, provider)
    row.request_count += 1
    db.commit()


def record_429(db: Session, provider: str) -> None:
    row = _get_or_create_row(db, provider)
    row.last_429_at = datetime.now(timezone.utc)
    db.commit()


def is_rate_limit_error(exc: Exception) -> bool:
    """SDK-agnostic 429 check: anthropic/openai SDK errors expose `.status_code`
    directly, httpx.HTTPStatusError (used by the Gemini provider) exposes it via
    `.response.status_code`."""
    status = getattr(exc, "status_code", None)
    if status == 429:
        return True
    response = getattr(exc, "response", None)
    return response is not None and getattr(response, "status_code", None) == 429


def get_usage_summary(db: Session) -> dict[str, dict]:
    settings = get_settings()
    configured_keys = {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "grok": settings.xai_api_key,
        "gemini": settings.gemini_api_key,
    }
    summary: dict[str, dict] = {}
    for provider, key in configured_keys.items():
        if not key:
            continue
        date_key = _date_key(provider)
        row = (
            db.query(ProviderUsageDaily)
            .filter_by(provider=provider, date_key=date_key)
            .first()
        )
        summary[provider] = {
            "requests_today": row.request_count if row else 0,
            "last_429_at": _as_utc_isoformat(row.last_429_at) if row and row.last_429_at else None,
        }
    return summary
