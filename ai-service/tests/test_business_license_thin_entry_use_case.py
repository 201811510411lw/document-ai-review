from app.capabilities.business_license.schemas import (
    BusinessLicenseDocumentClassification,
    BusinessLicenseDocumentInputResult,
    BusinessLicenseExtractedFields,
    BusinessLicenseNormalizedFields,
)
from app.models import (
    ManualReview,
    ManualReviewStatus,
    ReviewInput,
    ReviewInputContext,
    ReviewStatus,
    RiskLevel,
    RuleResult,
)
from app.use_cases.business_license import use_case as business_license_use_case_module
from app.use_cases.business_license.use_case import BusinessLicenseUseCase


def test_business_license_use_case_is_thin_entry_over_runtime_contract(monkeypatch):
    calls = []
    rule = RuleResult(
        rule_code="BUSINESS_LICENSE_TYPE_MATCH",
        rule_name="营业执照类型匹配",
        passed=True,
        risk_level_on_failure=RiskLevel.HIGH,
        message="材料已识别为营业执照",
    )

    def stub_workflow(input_context):
        calls.append(input_context)
        return {
            "input_context": input_context,
            "document_input": BusinessLicenseDocumentInputResult(
                input_type="local_file",
                file_name="business-license.png",
                mime_type="image/png",
            ),
            "document_classification": BusinessLicenseDocumentClassification(
                document_type="business_license",
                confidence=1.0,
                reasons=["stub"],
            ),
            "extracted_fields": BusinessLicenseExtractedFields(
                document_type="business_license",
                subject_name="示例科技有限公司",
                credit_code="91310000MA1K000000",
            ),
            "normalized_fields": BusinessLicenseNormalizedFields(
                document_type="business_license",
                subject_name="示例科技有限公司",
                credit_code="91310000MA1K000000",
            ),
            "extraction_metadata": {"structured_extraction": {"source": "stub"}},
            "source_evidence": {
                "source": {"record_id": "cert-business-001"},
                "skill_rule_review_metadata": {"skill_name": "business-license-review"},
            },
            "rule_results": [rule],
            "risk_level": RiskLevel.NONE,
            "needs_manual_review": False,
            "manual_review": ManualReview(status=ManualReviewStatus.NOT_REQUIRED),
            "summary": "营业执照规则校验通过",
            "status": ReviewStatus.REVIEWED,
        }

    monkeypatch.setattr(
        business_license_use_case_module,
        "run_business_license_workflow",
        stub_workflow,
    )
    assert not hasattr(
        business_license_use_case_module,
        "build_business_license_capability_result",
    )
    input_context = ReviewInputContext(
        task_id="review-task-thin-entry",
        input=ReviewInput(
            supplier_name="示例科技有限公司",
            supplier_credit_code="91310000MA1K000000",
            declared_document_type="business_license",
        ),
        use_case_name="business_license",
        use_case_version="v1",
        ruleset_version="business-license-rules-v1",
    )

    result = BusinessLicenseUseCase().review(input_context)

    assert calls == [input_context]
    assert result.task_id == "review-task-thin-entry"
    assert result.use_case_name == "business_license"
    assert result.use_case_version == "v1"
    assert result.ruleset_version == "business-license-rules-v1"
    assert result.capability_names == ["business_license"]
    assert result.document_type == "business_license"
    assert result.status == ReviewStatus.REVIEWED
    assert result.risk_level == RiskLevel.NONE
    assert result.needs_manual_review is False
    assert result.rule_results == [rule]
    assert result.skill_result["document_input"]["file_name"] == "business-license.png"
    assert (
        result.skill_result["normalized_fields"]["subject_name"]
        == "示例科技有限公司"
    )
    assert (
        result.skill_result["source_evidence"]["skill_rule_review_metadata"][
            "skill_name"
        ]
        == "business-license-review"
    )
