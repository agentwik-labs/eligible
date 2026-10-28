from fastapi.testclient import TestClient

from eligible.api import app


def test_healthz_returns_ok() -> None:
    response = TestClient(app).get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["models"]["judge"] == "claude-haiku-5-5"
