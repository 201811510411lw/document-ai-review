from app.models import ReviewInput
from app.repositories.review_result_repository import SQLiteReviewResultRepository
from app.services.review_service import ReviewService


def test_business_license_review_projection_is_saved_and_loaded(tmp_path):
    repository = SQLiteReviewResultRepository(tmp_path / "reviews.db")
    result = ReviewService(repository=repository).review(
        ReviewInput(
            ocr_text="""
            营业执照
            统一社会信用代码：91510100MA0000000X
            名称：成都示例商贸有限公司
            住所：成都市高新区天府大道 1 号
            法定代表人：张三
            营业期限：2020年01月02日至2030年01月01日
            """,
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
