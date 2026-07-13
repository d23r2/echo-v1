"""Tests for Phase 2's provider error classification (provider_errors.py) —
pure function, no network calls.
"""

from app.provider_errors import COOLDOWN_CATEGORIES, classify_provider_error


class _FakeHTTPError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeHTTPStatusError(Exception):
    """Mimics httpx.HTTPStatusError's shape (status via .response.status_code)."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.response = _FakeResponse(status_code)


def test_bare_429_is_rate_limited():
    assert classify_provider_error(_FakeHTTPError("Too many requests", 429)) == "rate_limited"


def test_429_with_quota_text_is_quota_exceeded():
    exc = _FakeHTTPError("Error: insufficient quota for this request", 429)
    assert classify_provider_error(exc) == "quota_exceeded"


def test_quota_exceeded_text_without_status_code():
    exc = Exception("You have exceeded your current quota, please check your plan and billing details.")
    assert classify_provider_error(exc) == "quota_exceeded"


def test_credits_exhausted_text():
    exc = Exception("Your account credits exhausted, please add more credits.")
    assert classify_provider_error(exc) == "credit_exhausted"


def test_http_402_is_billing_required():
    assert classify_provider_error(_FakeHTTPError("Payment required", 402)) == "billing_required"


def test_billing_hard_limit_text():
    exc = Exception("You've hit your billing hard limit for this month.")
    assert classify_provider_error(exc) == "billing_required"


def test_http_401_is_auth_failed():
    assert classify_provider_error(_FakeHTTPError("Invalid API key", 401)) == "auth_failed"


def test_http_403_is_auth_failed():
    assert classify_provider_error(_FakeHTTPError("Forbidden", 403)) == "auth_failed"


def test_401_with_quota_text_is_still_classified_as_quota():
    # Text patterns are checked before status-code fallbacks, so a provider
    # that (unusually) returns 401 with quota wording is still caught correctly.
    exc = _FakeHTTPError("quota exceeded for this key", 401)
    assert classify_provider_error(exc) == "quota_exceeded"


def test_httpx_style_status_error_via_response_attribute():
    exc = _FakeHTTPStatusError("Gemini API error 429: rate limited", 429)
    assert classify_provider_error(exc) == "rate_limited"


def test_connection_error_is_network_error():
    assert classify_provider_error(ConnectionError("Failed to connect")) == "network_error"


def test_generic_400_is_invalid_request():
    assert classify_provider_error(_FakeHTTPError("Bad request", 400)) == "invalid_request"


def test_unrecognized_exception_is_unknown_error():
    assert classify_provider_error(Exception("something weird happened")) == "unknown_error"


def test_cooldown_categories_are_the_expected_set():
    assert COOLDOWN_CATEGORIES == {
        "rate_limited",
        "quota_exceeded",
        "credit_exhausted",
        "billing_required",
    }
