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
