from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from tests.business_license_helpers import business_license_auth_headers


def test_rpa_capability_reports_disabled_state(monkeypatch):
    monkeypatch.setattr(settings, "rpa_verification_tobacco_enabled", False)
    client = TestClient(app)

    response = client.get(
        "/api/v1/tobacco-license/rpa-verify-capability",
        headers=business_license_auth_headers(client),
    )

    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "disabled_reason": "RPA 验真功能未启用",
    }


def test_rpa_verify_rejects_request_when_capability_is_disabled(monkeypatch):
    monkeypatch.setattr(settings, "rpa_verification_tobacco_enabled", False)
    client = TestClient(app)

    response = client.post(
        "/api/v1/tobacco-license/rpa-verify",
        headers=business_license_auth_headers(client),
        json={
            "task_id": "tc-disabled",
            "certificate_no": "510100100001",
            "store_name": "测试门店",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == {
        "code": "RPA_VERIFICATION_DISABLED",
        "message": "RPA 验真功能未启用",
    }
