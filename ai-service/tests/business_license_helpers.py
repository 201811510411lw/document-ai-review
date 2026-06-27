from fastapi.testclient import TestClient

from app.core.config import settings
from app.integrations.mysql_client import MySqlSettings
from app.repositories.review_result_repository import MySQLReviewResultRepository


def business_license_fields(
    *,
    subject_name: str = "成都示例商贸有限公司",
    credit_code: str = "91510100MA0000000X",
    document_type: str = "business_license",
    valid_to: str = "2030-01-01",
) -> dict:
    return {
        "document_type": document_type,
        "subject_name": subject_name,
        "credit_code": credit_code,
        "business_address": "成都市高新区天府大道 1 号",
        "legal_person": "张三",
        "valid_from": "2020-01-02",
        "valid_to": valid_to,
        "subject_name_evidence": "名称：成都示例商贸有限公司",
        "credit_code_evidence": "统一社会信用代码：91510100MA0000000X",
        "valid_to_evidence": "营业期限：2020年01月02日至2030年01月01日",
    }


def business_license_json(**overrides) -> str:
    import json

    return json.dumps(
        business_license_fields(**overrides),
        ensure_ascii=False,
    )


def business_license_text() -> str:
    return (
        "营业执照\n"
        "统一社会信用代码：91510100MA0000000X\n"
        "名称：成都示例商贸有限公司\n"
        "住所：成都市高新区天府大道 1 号\n"
        "法定代表人：张三\n"
        "营业期限：2020年01月02日至2030年01月01日\n"
    )


def business_license_repository() -> MySQLReviewResultRepository:
    return MySQLReviewResultRepository(
        MySqlSettings(
            host="127.0.0.1",
            port=3306,
            user="review",
            password="secret",
            database="document_ai_review",
        )
    )


def business_license_auth_headers(client: TestClient, monkeypatch=None) -> dict[str, str]:
    if monkeypatch is not None:
        monkeypatch.setenv("WEB_CONSOLE_AUTH_USERNAME", "reviewer")
        monkeypatch.setenv("WEB_CONSOLE_AUTH_PASSWORD", "reviewer123")
        monkeypatch.setattr(settings, "web_console_auth_username", "reviewer")
        monkeypatch.setattr(settings, "web_console_auth_password", "reviewer123")
    else:
        settings.web_console_auth_username = "reviewer"
        settings.web_console_auth_password = "reviewer123"
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "reviewer", "password": "reviewer123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
