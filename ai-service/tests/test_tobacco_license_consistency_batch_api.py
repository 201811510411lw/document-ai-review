from app.api import tobacco_license_consistency as consistency_api
from app.api.tobacco_license_consistency import BatchConsistencyReviewRequest
from app.integrations.starrocks.tobacco_license_sources import TobaccoLicenseSourceFile


def test_consistency_requires_both_license_document_roles():
    source = TobaccoLicenseSourceFile(
        requestid=1,
        docid=2,
        imagefile_id=3,
        document_role="tobacco_license",
        file_real_path="/data/oaec/test.zip",
    )

    assert consistency_api._missing_required_document_roles([source]) == [
        "business_license",
    ]


def test_batch_consistency_review_removes_duplicate_stores(monkeypatch):
    calls = []

    def stub_create_consistency_review(*, request, **_kwargs):
        calls.append(request.store_identifier)
        return {
            "task_id": f"task-{request.store_identifier}",
            "report": {
                "id": f"task-{request.store_identifier}",
                "overall_result": "通过",
            },
        }

    monkeypatch.setattr(
        consistency_api,
        "create_consistency_review",
        stub_create_consistency_review,
    )

    result = consistency_api.create_consistency_reviews_batch(
        request=BatchConsistencyReviewRequest(
            store_identifiers=["STORE-001", "STORE-001", "STORE-002"],
        ),
        current_user={"username": "reviewer"},
        sql_client=object(),
        file_store=object(),
        repository=object(),
    )

    assert calls == ["STORE-001", "STORE-002"]
    assert result["total"] == 2
    assert result["completed"] == 2
    assert result["failed"] == 0
    assert [item["store_identifier"] for item in result["items"]] == [
        "STORE-001",
        "STORE-002",
    ]
