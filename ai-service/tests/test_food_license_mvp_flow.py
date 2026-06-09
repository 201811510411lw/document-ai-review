from app.models import ReviewDocumentInput, ReviewInput
from app.repositories import SQLiteReviewResultRepository
from app.services.review_service import ReviewService


def test_food_license_mvp_review_flow_can_save_pdf_stub_result(tmp_path):
    repository = SQLiteReviewResultRepository(tmp_path / "reviews.sqlite3")
    service = ReviewService(repository=repository)

    result = service.review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                file_uri="s3://private-bucket/licenses/example.pdf",
                file_name="example.pdf",
                mime_type="application/pdf",
                document_format="pdf",
                stub_text=(
                    "食品经营许可证\n"
                    "经营者名称：成都示例食品有限公司\n"
                    "统一社会信用代码：91510100MA00000000\n"
                    "许可证编号：JY15101000000000\n"
                    "经营项目：预包装食品销售、散装食品销售\n"
                    "有效期至：2028年06月05日"
                ),
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")

    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["document_classification"]["document_type"] == "food_license"
    assert payload["skill_result"]["extracted_fields"]["license_no"] == "JY15101000000000"
    assert [rule_result["rule_code"] for rule_result in payload["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result["passed"] is True for rule_result in payload["rule_results"])
    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    loaded = repository.get_by_task_id(result.task_id)
    assert loaded is not None
    assert loaded.model_dump(mode="json") == result.model_dump(mode="json")
