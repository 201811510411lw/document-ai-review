from app.models import (
    ManualReviewStatus,
    ReviewDocumentInput,
    ReviewInput,
    ReviewInputContext,
    ReviewStatus,
)
from app.use_cases.registry import use_case_registry
from app.workflows.tobacco_license import workflow as tobacco_license_workflow
from tests.pdf_helpers import write_minimal_pdf


def test_placeholder_use_cases_return_clear_not_implemented_result():
    for use_case_name, declared_document_type in [
        ("tobacco_license_consistency_review", "tobacco_license_consistency_review"),
        ("contract_review", "contract_review"),
    ]:
        use_case = use_case_registry.get(use_case_name)
        input_context = ReviewInputContext(
            task_id=f"review-task-{use_case_name}",
            input=ReviewInput(
                ocr_text="占位输入",
                supplier_name="成都示例食品有限公司",
                supplier_credit_code="91510100MA00000000",
                declared_document_type=declared_document_type,
            ),
            use_case_name=use_case.name,
            use_case_version=use_case.version,
            ruleset_version=use_case.ruleset_version,
        )

        result = use_case.review(input_context)
        payload = result.model_dump(mode="json")

        assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
        assert result.needs_manual_review is True
        assert result.manual_review.status == ManualReviewStatus.PENDING
        assert payload["skill_result"]["implementation_status"] == "not_implemented"
        assert "尚未执行业务审核" in result.summary


def test_tobacco_license_placeholder_reads_file_through_llm_file_recognition(
    tmp_path,
    monkeypatch,
):
    pdf_path = tmp_path / "tobacco-license.pdf"
    write_minimal_pdf(pdf_path, "embedded text should not be used")
    seen = {}

    class StubFileAdapter:
        def extract_text(self, source):
            seen["content_prefix"] = source.content[:5]
            seen["mime_type"] = source.mime_type
            return {
                "text": "",
                "structured_fields": {"document_type": "tobacco_license"},
                "metadata": {"implementation_status": "stub"},
            }

    monkeypatch.setattr(
        tobacco_license_workflow,
        "tobacco_license_file_adapter",
        StubFileAdapter(),
    )
    use_case = use_case_registry.get("tobacco_license_consistency_review")
    input_context = ReviewInputContext(
        task_id="review-task-tobacco-license",
        input=ReviewInput(
            file=ReviewDocumentInput(
                local_path=str(pdf_path),
                file_name="tobacco-license.pdf",
                mime_type="application/pdf",
                document_format="pdf",
            ),
            supplier_name="成都示例食品有限公司",
            supplier_credit_code="91510100MA00000000",
            declared_document_type="tobacco_license",
        ),
        use_case_name=use_case.name,
        use_case_version=use_case.version,
        ruleset_version=use_case.ruleset_version,
    )

    result = use_case.review(input_context)
    payload = result.model_dump(mode="json")

    assert seen == {"content_prefix": b"%PDF-", "mime_type": "application/pdf"}
    assert payload["skill_result"]["document_input"]["input_type"] == "pdf"
    assert payload["skill_result"]["extraction_metadata"]["llm_file_extractor"] == {
        "implementation_status": "stub"
    }
    assert result.status == ReviewStatus.PENDING_MANUAL_REVIEW
