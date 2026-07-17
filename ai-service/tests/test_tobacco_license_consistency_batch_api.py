from fastapi.testclient import TestClient

from app.api.tobacco_license_consistency import (
    get_file_store,
    get_review_repository,
    get_starrocks_sql_client,
)
from app.main import app
from tests.business_license_helpers import business_license_auth_headers


class StubRepository:
    def __init__(self):
        self.results = []

    def save(self, result):
        self.results.append(result)


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_batch_consistency_review_returns_each_demo_outcome():
    repository = StubRepository()
    app.dependency_overrides[get_review_repository] = lambda: repository
    app.dependency_overrides[get_starrocks_sql_client] = lambda: object()
    app.dependency_overrides[get_file_store] = lambda: object()
    client = TestClient(app)

    response = client.post(
        "/api/v1/tobacco-license-consistency/reviews/batch",
        headers=business_license_auth_headers(client),
        json={
            "store_identifiers": [
                "DEMO-STORE-001",
                "DEMO-STORE-002",
                "DEMO-STORE-003",
                "DEMO-STORE-004",
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["completed"] == 4
    assert payload["failed"] == 0
    assert len(repository.results) == 4
    outcomes = {item["store_identifier"]: item["report"]["overall_result"] for item in payload["items"]}
    assert outcomes["DEMO-STORE-001"] == "通过"
    assert outcomes["DEMO-STORE-002"] == "待校验"
    assert outcomes["DEMO-STORE-003"] == "待校验"
    assert outcomes["DEMO-STORE-004"] == "通过"
    assert payload["items"][0]["report"]["oa"]["requestid"] == 10001
    attachments = payload["items"][0]["report"]["oa"]["attachments"]
    assert [item["relative_path"] for item in attachments] == [
        "demo/holder-business-license.pdf",
        "demo/tobacco-license.pdf",
        "demo/store-in-store-agreement.pdf",
    ]


def test_batch_consistency_review_removes_duplicate_stores():
    repository = StubRepository()
    app.dependency_overrides[get_review_repository] = lambda: repository
    app.dependency_overrides[get_starrocks_sql_client] = lambda: object()
    app.dependency_overrides[get_file_store] = lambda: object()
    client = TestClient(app)

    response = client.post(
        "/api/v1/tobacco-license-consistency/reviews/batch",
        headers=business_license_auth_headers(client),
        json={"store_identifiers": ["DEMO-STORE-004", "DEMO-STORE-004"]},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(repository.results) == 1
