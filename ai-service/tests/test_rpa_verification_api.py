from fastapi.testclient import TestClient

from app.api.rpa_verification import _stored_rpa_error_message
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


def test_stored_rpa_error_message_normalizes_legacy_false_without_response_id():
    rpa_info = {
        "status": "ERROR",
        "error_message": "官网验真返回失败，影刀未返回具体原因",
        "raw_yindao_response": {
            "status": "finish",
            "robotParams": {
                "outputs": [
                    {"name": "parameter", "type": "str", "value": "false"},
                    {"name": "responseId", "type": "str", "value": ""},
                ],
            },
        },
    }

    assert _stored_rpa_error_message(rpa_info) == "验真未完成：影刀未返回官网请求 ID"
