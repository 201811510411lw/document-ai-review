from datetime import date

from app.models import ReviewDocumentInput, ReviewInput
from app.repositories import SQLiteReviewResultRepository
from app.services.review_service import ReviewService
from app.workflows.food_license import nodes as food_license_nodes
from tests.test_food_license_document_input_boundaries import write_minimal_pdf


FOOD_LICENSE_TEXT = (
    "食品经营许可证\n"
    "经营者名称：成都示例食品有限公司\n"
    "统一社会信用代码：91510100MA00000000\n"
    "许可证编号：JY15101000000000\n"
    "经营项目：预包装食品销售、散装食品销售\n"
    "有效期至：2028年06月05日"
)


def test_ocr_text_flow_returns_basic_rule_results_and_no_risk():
    result = ReviewService().review_food_license(
        ReviewInput(
            ocr_text=FOOD_LICENSE_TEXT,
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")

    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is False
    assert payload["manual_review"]["status"] == "NOT_REQUIRED"
    assert [rule_result["rule_code"] for rule_result in payload["rule_results"]] == [
        "FOOD_LICENSE_RULE_ENGINE_STUB",
        "FOOD_LICENSE_TYPE_MATCH",
        "FOOD_LICENSE_SUBJECT_NAME_MATCH",
        "FOOD_LICENSE_CREDIT_CODE_MATCH",
        "FOOD_LICENSE_VALIDITY_PERIOD",
    ]
    assert all(rule_result["passed"] is True for rule_result in payload["rule_results"])


def test_stub_text_flow_flags_subject_name_mismatch_for_manual_review():
    result = ReviewService().review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                file_name="food-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
                stub_text=FOOD_LICENSE_TEXT,
            ),
            supplier_name="成都另一家食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")
    subject_rule = _rule(payload, "FOOD_LICENSE_SUBJECT_NAME_MATCH")

    assert payload["risk_level"] == "MEDIUM"
    assert payload["needs_manual_review"] is True
    assert payload["manual_review"]["status"] == "PENDING"
    assert payload["manual_review"]["reasons"] == ["确定性规则结果需要人工复核"]
    assert subject_rule["passed"] is False
    assert subject_rule["risk_level_on_failure"] == "MEDIUM"


def test_local_path_pdf_flow_flags_credit_code_mismatch_and_saves_sqlite(tmp_path):
    pdf_path = tmp_path / "food-license.pdf"
    write_minimal_pdf(pdf_path, FOOD_LICENSE_TEXT)
    repository = SQLiteReviewResultRepository(tmp_path / "reviews.sqlite3")

    result = ReviewService(repository=repository).review_food_license(
        ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="food-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA99999999",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")
    credit_rule = _rule(payload, "FOOD_LICENSE_CREDIT_CODE_MATCH")
    loaded = repository.get_by_task_id(result.task_id)

    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extraction_metadata"]["pdf_loader"] == {
        "implementation_status": "implemented",
        "needs_ocr": False,
        "source": "local_path",
    }
    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert credit_rule["passed"] is False
    assert credit_rule["risk_level_on_failure"] == "HIGH"
    assert loaded is not None
    assert loaded.model_dump(mode="json") == payload


def test_expired_license_is_high_risk(monkeypatch):
    monkeypatch.setattr(
        food_license_nodes,
        "_current_rule_date",
        lambda: date(2026, 6, 9),
    )

    result = ReviewService().review_food_license(
        ReviewInput(
            ocr_text=FOOD_LICENSE_TEXT.replace(
                "有效期至：2028年06月05日",
                "有效期至：2026年06月08日",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")
    validity_rule = _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")

    assert payload["risk_level"] == "HIGH"
    assert payload["needs_manual_review"] is True
    assert validity_rule["passed"] is False
    assert validity_rule["risk_level_on_failure"] == "HIGH"
    assert validity_rule["details"]["days_until_expiry"] < 0


def test_license_expiring_within_thirty_days_is_medium_risk(monkeypatch):
    monkeypatch.setattr(
        food_license_nodes,
        "_current_rule_date",
        lambda: date(2026, 6, 9),
    )

    result = ReviewService().review_food_license(
        ReviewInput(
            ocr_text=FOOD_LICENSE_TEXT.replace(
                "有效期至：2028年06月05日",
                "有效期至：2026年07月09日",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")
    validity_rule = _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")

    assert payload["risk_level"] == "MEDIUM"
    assert payload["needs_manual_review"] is True
    assert validity_rule["passed"] is False
    assert validity_rule["risk_level_on_failure"] == "MEDIUM"
    assert validity_rule["details"]["days_until_expiry"] <= 30


def test_missing_fields_enter_manual_review_without_llm_compliance_decision():
    result = ReviewService().review_food_license(
        ReviewInput(
            ocr_text="食品经营许可证\n许可证编号：JY15101000000000",
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="food_license",
        )
    )
    payload = result.model_dump(mode="json")

    assert payload["risk_level"] == "NONE"
    assert payload["needs_manual_review"] is True
    assert payload["manual_review"]["status"] == "PENDING"
    assert payload["manual_review"]["reasons"] == ["规则执行异常或不完整，需要人工复核"]
    assert _rule(payload, "FOOD_LICENSE_SUBJECT_NAME_MATCH")["details"]["status"] == "error"
    assert _rule(payload, "FOOD_LICENSE_CREDIT_CODE_MATCH")["details"]["status"] == "error"
    assert _rule(payload, "FOOD_LICENSE_VALIDITY_PERIOD")["details"]["status"] == "error"


def _rule(payload, rule_code):
    return next(
        rule_result
        for rule_result in payload["rule_results"]
        if rule_result["rule_code"] == rule_code
    )
