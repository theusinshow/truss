from fastapi.testclient import TestClient

from truss_api.main import app


client = TestClient(app)


def test_root_returns_ok() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"app": "truss-agent", "status": "ok"}


def test_health_returns_storage_layout() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"] == "truss-agent"
    assert payload["status"] == "ok"
    assert set(payload["storage"].keys()) == {
        "data",
        "db",
        "originals",
        "renders",
        "cache",
    }
