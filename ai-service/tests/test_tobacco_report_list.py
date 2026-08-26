import pytest
from fastapi import HTTPException

from app.api import wecom_frontend


class StubRepository:
    def __init__(self, items=None, error=None):
        self.items = items or []
        self.error = error

    def list_qc_reviews(self, **_kwargs):
        if self.error is not None:
            raise self.error
        return {"items": self.items, "total": len(self.items)}


def test_tobacco_reports_maps_repository_items(monkeypatch):
    monkeypatch.setattr(wecom_frontend, "list_tobacco_reports", lambda: [])
    repository = StubRepository(
        items=[
            {
                "task_id": "prod-review-1",
                "document_type": "business_tobacco_consistency",
                "supplier_name": "生产门店",
                "review_status": "REVIEWED",
                "risk_level": "NONE",
                "needs_manual_review": False,
            }
        ]
    )

    result = wecom_frontend.tobacco_reports(
        _current_user={"username": "reviewer"},
        repository=repository,
    )

    assert [record["id"] for record in result["records"]] == ["prod-review-1"]
    assert result["stats"] == {"total": 1, "passed": 1, "failed": 0, "pending": 0}


def test_tobacco_reports_does_not_treat_running_parent_as_pass(monkeypatch):
    monkeypatch.setattr(wecom_frontend, "list_tobacco_reports", lambda: [])
    result = wecom_frontend.tobacco_reports(
        _current_user={"username": "reviewer"},
        repository=StubRepository(
            items=[
                {
                    "task_id": "tc-oa-running",
                    "document_type": "business_tobacco_consistency",
                    "review_status": "RUNNING",
                    "risk_level": "NONE",
                    "needs_manual_review": False,
                }
            ]
        ),
    )

    assert result["records"][0]["overall_result"] == "待校验"
    assert result["stats"] == {"total": 1, "passed": 0, "failed": 0, "pending": 1}


def test_tobacco_report_does_not_mark_empty_comparison_fields_as_matching():
    report = wecom_frontend._frontend_tobacco_report(
        {
            "task_id": "tc-oa-empty-fields",
            "document_type": "business_tobacco_consistency",
            "review_status": "PENDING_MANUAL_REVIEW",
            "risk_level": "MEDIUM",
            "needs_manual_review": True,
            "business_license_fields": {
                "subject_name": None,
                "business_address": None,
                "legal_person": None,
            },
            "tobacco_license_fields": {
                "subject_name": None,
                "business_address": None,
                "legal_person": None,
            },
            "rule_results": [],
        },
        detail=True,
    )

    assert report["name_match"] == "待校验"
    assert report["address_match"] == "待校验"
    assert report["person_match"] == "待校验"


def test_tobacco_reports_returns_empty_records_for_empty_repository(monkeypatch):
    monkeypatch.setattr(wecom_frontend, "list_tobacco_reports", lambda: [])

    result = wecom_frontend.tobacco_reports(
        _current_user={"username": "reviewer"},
        repository=StubRepository(),
    )

    assert result["records"] == []
    assert result["stats"] == {"total": 0, "passed": 0, "failed": 0, "pending": 0}


def test_tobacco_reports_exposes_database_failure(monkeypatch):
    monkeypatch.setattr(wecom_frontend, "list_tobacco_reports", lambda: [])

    with pytest.raises(HTTPException) as exc_info:
        wecom_frontend.tobacco_reports(
            _current_user={"username": "reviewer"},
            repository=StubRepository(error=RuntimeError("database unavailable")),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["code"] == "REVIEW_DATABASE_UNAVAILABLE"
