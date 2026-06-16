from datetime import datetime

from fastapi.testclient import TestClient

from app.main import app


def test_health_check_matches_api_contract():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")

    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ai-service"
    assert data["version"] == "v1"

    timestamp = datetime.fromisoformat(data["timestamp"])
    assert timestamp.tzinfo is not None
