from app.models import ReviewInput
from app.models import ReviewDocumentInput
from app.repositories.review_result_repository import MySQLReviewResultRepository
from app.services.review_service import ReviewService
from tests.business_license_helpers import (
    business_license_json,
    business_license_repository,
)
from tests.mysql_repository_stub import install_mysql_repository_stub
from tests.pdf_helpers import write_minimal_pdf


def test_business_license_review_projection_is_saved_and_loaded(tmp_path, monkeypatch):
    install_mysql_repository_stub(monkeypatch)
    pdf_path = tmp_path / "business-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    monkeypatch.setenv(
        "BUSINESS_LICENSE_FAKE_VISION_JSON",
        business_license_json(),
    )
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)
    repository = _repository()
    result = ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="business-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例商贸有限公司",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_license",
            source={
                "tenant": "8560",
                "record_id": "cert-business-001",
                "attachment_ref_id": "attach-business-001",
            },
        ),
        use_case_name="business_license",
    )

    loaded = repository.get_by_task_id(result.task_id)
    snapshot = repository.get_business_license_snapshot(result.task_id)

    assert loaded == result
    assert snapshot["task_id"] == result.task_id
    assert snapshot["source_record_id"] == "cert-business-001"
    assert snapshot["source_attachment_ref_id"] == "attach-business-001"
    assert snapshot["tenant"] == "8560"
    assert snapshot["business_name"] == "成都示例商贸有限公司"
    assert snapshot["credit_code"] == "91510100MA0000000X"
    assert snapshot["review_status"] == "REVIEWED"
    assert snapshot["risk_level"] == "NONE"
    assert snapshot["needs_manual_review"] is False
    assert snapshot["extracted_fields"]["subject_name"] == "成都示例商贸有限公司"
    assert snapshot["source_evidence"]["source"]["record_id"] == "cert-business-001"
    assert snapshot["rule_results"][0]["rule_code"] == "BUSINESS_LICENSE_TYPE_MATCH"


def test_business_license_projection_saves_file_and_vision_metadata(
    tmp_path,
    monkeypatch,
):
    install_mysql_repository_stub(monkeypatch)
    image_path = tmp_path / "business-license.png"
    image_path.write_bytes(b"fake-image-bytes")
    monkeypatch.setenv(
        "BUSINESS_LICENSE_FAKE_VISION_JSON",
        business_license_json(),
    )
    monkeypatch.delenv("BUSINESS_LICENSE_FAKE_VISION_TEXT", raising=False)
    repository = _repository()

    result = ReviewService(repository=repository).review(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(image_path),
                file_name="business-license.png",
                mime_type="image/png",
                document_format="image",
                file_uri="https://files.example.test/business-license.png",
            ),
            supplier_name="成都示例商贸有限公司",
            supplier_credit_code="91510100MA0000000X",
            declared_document_type="business_license",
            source={"record_id": "cert-business-001"},
        ),
        use_case_name="business_license",
    )

    snapshot = repository.get_business_license_snapshot(result.task_id)

    assert snapshot["source_url"] == "https://files.example.test/business-license.png"
    assert snapshot["business_name"] == "成都示例商贸有限公司"
    assert snapshot["extraction_metadata"]["vision_extractor"]["implementation_status"] == "fake"


def _business_license_json() -> str:
    return business_license_json()


def _repository() -> MySQLReviewResultRepository:
    return business_license_repository()
