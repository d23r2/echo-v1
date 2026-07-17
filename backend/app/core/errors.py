"""ECHO Layer 0 — request ID propagation, standard error schema, and global
exception handling.

Deliberately additive, not a rewrite: the ~30 existing routers already raise
FastAPI's own `HTTPException(status_code=..., detail=...)` for expected error
cases, and that behavior is unchanged — FastAPI's built-in HTTPException
handler still runs exactly as before, so every existing test/route keeps its
current response shape. What's new here is for code going forward (this
milestone's own new endpoints, and any future one): a typed `ApiError` with
an explicit category, plus a catch-all for genuinely *unhandled* exceptions
so a bug in new code degrades to a clean generic message instead of a raw
traceback, matching the pattern router.py/chat.py already use by hand for
provider errors.
"""

import logging
import time
import uuid
from enum import StrEnum

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core import metrics
from app.core.logging import log_event, redact, request_id_var

logger = logging.getLogger(__name__)


class ErrorCategory(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    FEATURE_DISABLED = "FEATURE_DISABLED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_QUOTA_EXCEEDED = "PROVIDER_QUOTA_EXCEEDED"
    PROVIDER_BILLING_REQUIRED = "PROVIDER_BILLING_REQUIRED"
    OLLAMA_OFFLINE = "OLLAMA_OFFLINE"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    SEARCH_UNAVAILABLE = "SEARCH_UNAVAILABLE"
    CURRENT_INFO_UNVERIFIED = "CURRENT_INFO_UNVERIFIED"
    DATABASE_ERROR = "DATABASE_ERROR"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_ACCESS_DENIED = "FILE_ACCESS_DENIED"
    ACTION_CONFIRMATION_REQUIRED = "ACTION_CONFIRMATION_REQUIRED"
    DESTRUCTIVE_ACTION_BLOCKED = "DESTRUCTIVE_ACTION_BLOCKED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Categories where retrying the same request without changing anything could
# plausibly succeed (a transient provider hiccup, a rate limit that clears).
# Validation/permission/not-found categories are never retryable as-is.
_RETRYABLE_CATEGORIES = {
    ErrorCategory.PROVIDER_UNAVAILABLE,
    ErrorCategory.PROVIDER_RATE_LIMITED,
    ErrorCategory.OLLAMA_OFFLINE,
    ErrorCategory.SEARCH_UNAVAILABLE,
    ErrorCategory.DATABASE_ERROR,
}


class ApiError(Exception):
    """Raise this from new code that wants the standard error schema below.
    Existing routes' `raise HTTPException(...)` calls are untouched and keep
    working exactly as before — this is additive, not a replacement."""

    def __init__(self, category: ErrorCategory, message: str, status_code: int = 400):
        self.category = category
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def build_error_body(category: ErrorCategory, message: str, request_id: str | None) -> dict:
    """The standard error response shape — never includes a stack trace or
    raw exception text, only a clean pre-written message (see the handlers
    below for where the raw cause is logged instead, server-side only)."""
    return {
        "error": {
            "code": category.value,
            "message": message,
            "request_id": request_id,
            "retryable": category in _RETRYABLE_CATEGORIES,
        }
    }


_GENERIC_INTERNAL_MESSAGE = "Something went wrong on ECHO's end. This has been logged; please try again."
_GENERIC_VALIDATION_MESSAGE = "That request wasn't in the expected format."


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns (or reuses an inbound) X-Request-ID for every request, makes
    it available to log_event() via a contextvar for the duration of the
    request, echoes it back in the response header, and logs a compact
    request-completed event with method/path/status/elapsed — never the
    request body or query values, which could carry user content."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("x-request-id")
        request_id = incoming if incoming else str(uuid.uuid4())
        token = request_id_var.set(request_id)
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000
            metrics.increment("http_requests_total", status="500")
            metrics.increment("http_errors_total")
            metrics.record_duration("http_request_duration_ms", elapsed_ms)
            log_event(
                logger,
                "request_failed",
                level=logging.ERROR,
                elapsed_ms=elapsed_ms,
                error_category=ErrorCategory.INTERNAL_ERROR.value,
            )
            raise
        finally:
            request_id_var.reset(token)
        elapsed_ms = (time.monotonic() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        metrics.increment("http_requests_total", status=str(response.status_code))
        if response.status_code >= 400:
            metrics.increment("http_errors_total")
        metrics.record_duration("http_request_duration_ms", elapsed_ms)
        log_event(logger, f"{request.method} {request.url.path} -> {response.status_code}", elapsed_ms=elapsed_ms)
        return response


def register_exception_handlers(app: FastAPI) -> None:
    """Additive only — FastAPI's default HTTPException handler is left
    completely untouched, so every existing `raise HTTPException(...)` call
    site across the ~30 existing routers keeps its exact current response
    shape. These handlers only cover the new ApiError type and genuinely
    unhandled exceptions/validation errors."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError):
        request_id = request_id_var.get()
        logger.warning("ApiError: %s (%s)", redact(exc.message), exc.category.value)
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_body(exc.category, exc.message, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError):
        request_id = request_id_var.get()
        return JSONResponse(
            status_code=422,
            content=build_error_body(ErrorCategory.VALIDATION_ERROR, _GENERIC_VALIDATION_MESSAGE, request_id),
        )

    @app.exception_handler(Exception)
    async def _handle_unhandled_exception(request: Request, exc: Exception):
        request_id = request_id_var.get()
        # Full detail (type, message, stack) goes to the server log only —
        # this is the one place a truly unanticipated exception lands, so
        # it must never leak past this boundary into the HTTP response.
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=build_error_body(ErrorCategory.INTERNAL_ERROR, _GENERIC_INTERNAL_MESSAGE, request_id),
        )
