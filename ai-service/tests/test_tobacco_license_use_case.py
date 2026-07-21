from app.models import ReviewDocumentInput, ReviewInput, ReviewStatus, RiskLevel
from app.services.review_service import ReviewService
from app.workflows.tobacco_license import workflow as tobacco_license_workflow
from tests.pdf_helpers import write_minimal_pdf


BASE_FIELDS = {
    "document_type": "tobacco_license",
    "subject_name": "成都示例烟草商行",
    "business_address": "成都市高新区天府大道 1 号",
    "legal_person": "张三",
    "license_no": "烟专零售许第510100000001号",
    "valid_to": "2099-12-31",
}


class StubFileAdapter:
    def __init__(self, fields):
        self.fields = fields

    def extract_text(self, source):
        return {
            "text": "",
            "structured_fields": self.fields,
            "metadata": {"implementation_status": "stub"},
        }


def test_tobacco_license_standard_document_passes(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter(BASE_FIELDS),
    )

    result = ReviewService().review(
        _review_input(tmp_path),
        use_case_name="tobacco_license",
    )

    assert result.use_case_name == "tobacco_license"
    assert result.document_type == "tobacco_license"
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.skill_result["extracted_fields"]["license_no"] == "烟专零售许第510100000001号"


def test_tobacco_license_missing_required_fields_routes_manual_review(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter({"document_type": "tobacco_license", "license_no": "烟专零售许第1号"}),
    )

    result = ReviewService().review(
        _review_input(tmp_path),
        use_case_name="tobacco_license",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.needs_manual_review is True
    assert "subject_name 缺失" in result.manual_review.reasons


def test_tobacco_license_expired_document_is_high_risk(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "valid_to": "2000-01-01"}),
    )

    result = ReviewService().review(
        _review_input(tmp_path),
        use_case_name="tobacco_license",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.HIGH
    assert result.needs_manual_review is True


def test_tobacco_license_expiring_within_thirty_days_routes_manual_review(
    tmp_path,
    monkeypatch,
):
    class FixedDate:
        @classmethod
        def today(cls):
            from datetime import date

            return date(2026, 6, 15)

        @classmethod
        def fromisoformat(cls, value):
            from datetime import date

            return date.fromisoformat(value)

    monkeypatch.setattr(tobacco_license_workflow, "date", FixedDate)
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "valid_to": "2026-07-01"}),
    )

    result = ReviewService().review(
        _review_input(tmp_path),
        use_case_name="tobacco_license",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.MEDIUM
    assert result.needs_manual_review is True


def test_tobacco_license_normalizes_chinese_validity_date(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "valid_to": "2029年06月01日"}),
    )

    result = ReviewService().review(
        _review_input(tmp_path),
        use_case_name="tobacco_license",
    )

    assert result.status == ReviewStatus.REVIEWED
    assert result.skill_result["normalized_fields"]["valid_to"] == "2029-06-01"


def test_non_tobacco_license_input_routes_high_risk_manual_review(tmp_path, monkeypatch):
    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter({**BASE_FIELDS, "document_type": "business_license"}),
    )

    result = ReviewService().review(
        _review_input(tmp_path),
        use_case_name="tobacco_license",
    )

    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
    assert result.risk_level == RiskLevel.HIGH
    assert "无法确认文件是烟草专卖零售许可证" in result.manual_review.reasons


def _review_input(tmp_path):
    pdf_path = tmp_path / "tobacco-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    return ReviewInput(
        file=ReviewDocumentInput(
            local_path=str(pdf_path),
            file_name="tobacco-license.pdf",
            mime_type="application/pdf",
            document_format="pdf",
        ),
        supplier_name="成都示例烟草商行",
        supplier_credit_code="91510100MA0000000X",
        declared_document_type="tobacco_license",
    )
