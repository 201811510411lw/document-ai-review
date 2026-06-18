from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_web_console_login_and_me_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "web_console_auth_username", "reviewer")
    monkeypatch.setattr(settings, "web_console_auth_password", "reviewer123")
    client = TestClient(app)

    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "reviewer123"},
    )

    assert login_response.status_code == 200
    payload = login_response.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"] == {
        "username": "reviewer",
        "display_name": "审核员",
    }

    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )

    assert me_response.status_code == 200
    assert me_response.json()["user"]["username"] == "reviewer"


def test_web_console_login_allows_local_dev_cors_preflight():
    client = TestClient(app)

    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in response.headers["access-control-allow-methods"]


def test_web_console_login_rejects_invalid_credentials(monkeypatch):
    monkeypatch.setattr(settings, "web_console_auth_username", "reviewer")
    monkeypatch.setattr(settings, "web_console_auth_password", "reviewer123")
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "INVALID_CREDENTIALS",
        "message": "用户名或密码错误",
    }


def test_web_console_me_requires_bearer_token():
    client = TestClient(app)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == {
        "code": "UNAUTHORIZED",
        "message": "请先登录工作台",
    }
