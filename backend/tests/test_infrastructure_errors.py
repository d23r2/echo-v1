"""ECHO Layer 0 — request ID propagation + standard error schema.

Builds a small standalone FastAPI app wired with the real
RequestIDMiddleware/register_exception_handlers (not the production app) so
these tests can exercise ApiError/validation/unhandled-exception paths
without adding test-only routes to the real app. Also confirms the real
app (TestClient against app.main.app) echoes X-Request-ID on a normal route.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.errors import ApiError, ErrorCategory, RequestIDMiddleware, register_exception_handlers


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)

    class Payload(BaseModel):
        value: int

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    @app.get("/boom-api-error")
    def boom_api_error():
        raise ApiError(ErrorCategory.PROVIDER_UNAVAILABLE, "The requested service is unavailable right now.", 503)

    @app.get("/boom-unhandled")
    def boom_unhandled():
        raise RuntimeError("some internal detail with a secret sk-abcdefghijklmnop1234567890")

    @app.post("/validate")
    def validate(payload: Payload):
        return {"value": payload.value}

    return app


client = TestClient(_build_test_app(), raise_server_exceptions=False)


def test_normal_response_gets_request_id_header():
    resp = client.get("/ok")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0


def test_inbound_request_id_is_echoed_back():
    resp = client.get("/ok", headers={"X-Request-ID": "my-custom-id-123"})
    assert resp.headers["X-Request-ID"] == "my-custom-id-123"


def test_api_error_produces_standard_schema():
    resp = client.get("/boom-api-error")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert body["error"]["message"] == "The requested service is unavailable right now."
    assert body["error"]["retryable"] is True
    assert body["error"]["request_id"] is not None


def test_unhandled_exception_returns_generic_message_not_raw_detail():
    resp = client.get("/boom-unhandled")
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    raw = resp.text
    assert "RuntimeError" not in raw
    assert "sk-abcdefghijklmnop1234567890" not in raw
    assert "some internal detail" not in raw


def test_validation_error_uses_standard_schema():
    resp = client.post("/validate", json={"value": "not-an-int"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in body["error"]


def test_non_retryable_category_marked_correctly():
    resp = client.post("/validate", json={"value": "nope"})
    body = resp.json()
    assert body["error"]["retryable"] is False


def test_real_app_normal_route_still_has_request_id():
    from app.db import init_db
    from app.main import app as real_app

    init_db()
    real_client = TestClient(real_app)
    resp = real_client.get("/api/health")
    assert resp.status_code == 200
    assert "X-Request-ID" in resp.headers


def test_real_app_existing_http_exception_shape_unchanged():
    """A known 404 from an existing router must still return FastAPI's
    default {"detail": ...} shape, not the new standard error schema — this
    is the guarantee that existing frontend error handling (which parses
    `detail`) was never touched by this milestone."""
    from app.db import init_db
    from app.main import app as real_app

    init_db()
    real_client = TestClient(real_app)
    resp = real_client.delete("/api/atlas/nonexistent-id-xyz")
    assert resp.status_code == 404
    body = resp.json()
    assert "detail" in body
    assert "error" not in body
