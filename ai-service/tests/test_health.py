from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import WebConsoleStaticFiles, app


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


def test_web_console_frontend_routes_fallback_to_index(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    test_app = FastAPI()
    test_app.mount("/", WebConsoleStaticFiles(directory=tmp_path, html=True))
    client = TestClient(test_app)

    response = client.get("/reviews")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<div id="root"></div>' in response.text


def test_missing_api_routes_do_not_fallback_to_web_console(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    test_app = FastAPI()
    test_app.mount("/", WebConsoleStaticFiles(directory=tmp_path, html=True))
    client = TestClient(test_app)

    response = client.get("/api/v1/missing-route")

    assert response.status_code == 404


def test_missing_static_assets_do_not_fallback_to_web_console(tmp_path):
    (tmp_path / "index.html").write_text('<div id="root"></div>', encoding="utf-8")
    test_app = FastAPI()
    test_app.mount("/", WebConsoleStaticFiles(directory=tmp_path, html=True))
    client = TestClient(test_app)

    response = client.get("/missing.js")

    assert response.status_code == 404
