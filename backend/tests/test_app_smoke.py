"""Foundation smoke test: the FastAPI app must import and start without
crashing. Deliberately does not test any feature behavior — see the other
test_*.py files for that.
"""

from fastapi.testclient import TestClient

from app.main import app


def test_app_imports_and_health_endpoint_responds():
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "codename": "Seed", "version": "1.0"}
