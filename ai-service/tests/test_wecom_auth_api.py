from fastapi.testclient import TestClient
from urllib.parse import parse_qs, urlparse

from app.api import auth as auth_api
from app.core.config import settings
from app.integrations.wecom.client import WecomUser
from app.main import app


def test_wecom_provider_reports_configuration(monkeypatch):
    monkeypatch.setattr(settings, "wecom_corp_id", "corp")
    monkeypatch.setattr(settings, "wecom_agent_id", "1001")
    monkeypatch.setattr(settings, "wecom_secret", "secret")
    monkeypatch.setattr(settings, "wecom_redirect_uri", "https://example.com/callback")

    response = TestClient(app).get("/api/v1/auth/providers")

    assert response.status_code == 200
    provider = response.json()["providers"][0]
    assert provider["id"] == "wecom"
    assert provider["configured"] is True


def test_wecom_sso_start_returns_authorize_url(monkeypatch):
    monkeypatch.setattr(settings, "wecom_corp_id", "corp")
    monkeypatch.setattr(settings, "wecom_agent_id", "1001")
    monkeypatch.setattr(settings, "wecom_secret", "secret")
    monkeypatch.setattr(settings, "wecom_redirect_uri", "https://example.com/callback")

    response = TestClient(app).get("/api/v1/auth/sso/start?provider=wecom")

    assert response.status_code == 200
    redirect_url = response.json()["redirect_url"]
    state = parse_qs(urlparse(redirect_url).query)["state"][0]
    assert "open.work.weixin.qq.com/wwopen/sso/qrConnect" in redirect_url
    assert "appid=corp" in redirect_url
    assert "." in state
    assert len(state) <= 128


def test_wecom_sso_start_returns_work_oauth_url(monkeypatch):
    monkeypatch.setattr(settings, "wecom_corp_id", "corp")
    monkeypatch.setattr(settings, "wecom_agent_id", "1001")
    monkeypatch.setattr(settings, "wecom_secret", "secret")
    monkeypatch.setattr(settings, "wecom_redirect_uri", "https://example.com/callback")

    response = TestClient(app).get("/api/v1/auth/sso/start?provider=wecom&mode=work")

    assert response.status_code == 200
    redirect_url = response.json()["redirect_url"]
    assert "open.weixin.qq.com/connect/oauth2/authorize" in redirect_url
    assert "appid=corp" in redirect_url
    assert "scope=snsapi_base" in redirect_url
    assert redirect_url.endswith("#wechat_redirect")


def test_wecom_sso_callback_sets_session_cookie(monkeypatch):
    monkeypatch.setattr(settings, "wecom_corp_id", "corp")
    monkeypatch.setattr(settings, "wecom_agent_id", "1001")
    monkeypatch.setattr(settings, "wecom_secret", "secret")
    monkeypatch.setattr(settings, "wecom_redirect_uri", "https://example.com/callback")
    monkeypatch.setattr(settings, "wecom_unmatched_user_policy", "auto_create")
    monkeypatch.setattr(settings, "web_console_base_url", "")
    state = auth_api._create_sso_state("wecom")

    class FakeWecomClient:
        def resolve_login_user(self, code):
            assert code == "code-1"
            return WecomUser(user_id="wecom-reviewer", name="企微审核员", email="u@example.com")

    monkeypatch.setattr(auth_api, "WecomClient", FakeWecomClient)

    client = TestClient(app)
    response = client.get(
        f"/api/v1/auth/sso/callback?provider=wecom&code=code-1&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/#/review"
    assert "document_ai_review_session" in response.headers["set-cookie"]

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["username"] == "wecom-reviewer"
    assert me.json()["user"]["provider"] == "wecom"


def test_wecom_sso_callback_survives_missing_process_memory_state(monkeypatch):
    monkeypatch.setattr(settings, "wecom_corp_id", "corp")
    monkeypatch.setattr(settings, "wecom_agent_id", "1001")
    monkeypatch.setattr(settings, "wecom_secret", "secret")
    monkeypatch.setattr(settings, "wecom_redirect_uri", "https://example.com/callback")
    monkeypatch.setattr(settings, "web_console_base_url", "")
    state = auth_api._create_sso_state("wecom")

    class FakeWecomClient:
        def resolve_login_user(self, code):
            assert code == "code-1"
            return WecomUser(user_id="wecom-reviewer", name="企微审核员", email="u@example.com")

    monkeypatch.setattr(auth_api, "WecomClient", FakeWecomClient)

    response = TestClient(app).get(
        f"/api/v1/auth/sso/callback?provider=wecom&code=code-1&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/#/review"
    assert "document_ai_review_session" in response.headers["set-cookie"]


def test_wecom_sso_callback_accepts_legacy_signed_state_during_rollout(monkeypatch):
    monkeypatch.setattr(settings, "wecom_corp_id", "corp")
    monkeypatch.setattr(settings, "wecom_agent_id", "1001")
    monkeypatch.setattr(settings, "wecom_secret", "secret")
    monkeypatch.setattr(settings, "wecom_redirect_uri", "https://example.com/callback")
    monkeypatch.setattr(settings, "web_console_base_url", "")
    state = auth_api._sign_token(
        {
            "provider": "wecom",
            "expires_at": 4_102_444_800,
            "nonce": "legacy-rollout-state",
        }
    )

    class FakeWecomClient:
        def resolve_login_user(self, code):
            assert code == "code-1"
            return WecomUser(user_id="wecom-reviewer", name="企微审核员", email="u@example.com")

    monkeypatch.setattr(auth_api, "WecomClient", FakeWecomClient)

    response = TestClient(app).get(
        f"/api/v1/auth/sso/callback?provider=wecom&code=code-1&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/#/review"
    assert "document_ai_review_session" in response.headers["set-cookie"]


def test_wecom_sso_callback_rejects_tampered_state():
    state = auth_api._create_sso_state("wecom")
    response = TestClient(app).get(
        f"/api/v1/auth/sso/callback?provider=wecom&code=code-1&state={state}tampered"
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_SSO_STATE"


def test_wecom_sso_callback_rejects_invalid_state():
    response = TestClient(app).get(
        "/api/v1/auth/sso/callback?provider=wecom&code=code-1&state=missing"
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "INVALID_SSO_STATE"


def test_wecom_sso_callback_without_code_or_state_returns_to_workbench(monkeypatch):
    monkeypatch.setattr(settings, "web_console_base_url", "")

    response = TestClient(app).get(
        "/api/v1/auth/sso/callback?provider=wecom",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/#/review"
