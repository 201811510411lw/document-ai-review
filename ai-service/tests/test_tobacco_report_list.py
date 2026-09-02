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


def test_tobacco_report_detail_exposes_callback_audit():
    history = [
        {
            "status": "SENT",
            "target": "https://oa.lsym.cn:8080/api/bicallback/result",
            "request_payload": {"requestid": 584412},
            "http_status": 200,
            "response_body": {"code": 0},
            "business_accepted": True,
        }
    ]

    report = wecom_frontend._frontend_tobacco_report(
        {
            "task_id": "tc-oa-callback",
            "document_type": "business_tobacco_consistency",
            "review_status": "FAILED",
            "risk_level": "HIGH",
            "needs_manual_review": True,
            "oa_callback": history[0],
            "oa_callback_history": history,
        },
        detail=True,
    )

    assert report["oa_callback"] == history[0]
    assert report["oa_callback_history"] == history


def test_tobacco_report_detail_exposes_backend_rule_suggestion():
    report = wecom_frontend._frontend_tobacco_report(
        {
            "task_id": "tc-oa-evidence",
            "document_type": "business_tobacco_consistency",
            "review_status": "PENDING_MANUAL_REVIEW",
            "risk_level": "MEDIUM",
            "needs_manual_review": True,
            "rule_results": [
                {
                    "rule_code": "TOBACCO_LICENSE_EVIDENCE_FOR_CONSISTENCY",
                    "rule_name": "烟草证关键字段证据完整",
                    "passed": False,
                    "message": "烟草证关键字段证据完整不足",
                    "details": {},
                }
            ],
        },
        detail=True,
    )

    assert report["rule_results"][0]["suggestion"] == (
        "请重新上传清晰、完整的烟草证原件，确保企业名称、负责人、经营地址、"
        "许可证号、有效期及对应原文清晰可见。"
    )


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
