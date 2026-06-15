from datetime import date
from typing import Any

from app.capabilities.tobacco_license.schemas import (
    TobaccoLicenseDocumentClassification,
    TobaccoLicenseDocumentInputResult,
    TobaccoLicenseExtractedFields,
    TobaccoLicenseNormalizedFields,
)
from app.models import ManualReview, ManualReviewStatus, ReviewInputContext, RiskLevel, RuleResult
from app.tools.license_file_recognition import recognize_license_file
from app.tools.vision_adapter import FakeVisionAdapter


tobacco_license_file_adapter = FakeVisionAdapter(
    structured_json_env="TOBACCO_LICENSE_FAKE_LLM_FILE_JSON",
    text_env="TOBACCO_LICENSE_FAKE_LLM_FILE_TEXT",
    model="fake-tobacco-license-file-recognition",
)


def run_tobacco_license_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    review_input = input_context.input
    recognition_result = recognize_license_file(
        review_input,
        adapter=tobacco_license_file_adapter,
    )
    structured_fields = recognition_result.structured_fields or {}
    classification = TobaccoLicenseDocumentClassification(
        document_type=structured_fields.get("document_type") or "unknown",
        confidence=1.0 if structured_fields.get("document_type") == "tobacco_license" else 0.0,
        reasons=["大模型文件识别返回结构化证照类型"] if structured_fields else ["未返回结构化烟草证字段"],
    )
    extracted_fields = TobaccoLicenseExtractedFields.model_validate(structured_fields)
    normalized_fields = TobaccoLicenseNormalizedFields.model_validate(
        extracted_fields.model_dump(mode="json")
    )
    rule_results = _review_rules(classification, normalized_fields)
    failed = [rule for rule in rule_results if not rule.passed]
    risk_level = _risk_level(failed)
    needs_manual_review = bool(failed)
    manual_review = ManualReview(
        status=ManualReviewStatus.PENDING if needs_manual_review else ManualReviewStatus.NOT_REQUIRED,
        reasons=[_manual_reason(rule) for rule in failed],
    )
    return {
        "implementation_status": "implemented",
        "document_text": recognition_result.document_text,
        "document_input": TobaccoLicenseDocumentInputResult(
            **recognition_result.document_input.__dict__
        ),
        "document_classification": classification,
        "extracted_fields": extracted_fields,
        "normalized_fields": normalized_fields,
        "extraction_metadata": {
            **recognition_result.extraction_metadata,
            "structured_extraction": {
                "source": "llm_file_extractor",
                "schema": "TobaccoLicenseExtractedFields",
                **({} if structured_fields else {"status": "missing_structured_fields"}),
            },
        },
        "source_evidence": {
            "supplier_name": review_input.supplier_name,
            "supplier_credit_code": review_input.supplier_credit_code,
            "declared_document_type": review_input.declared_document_type,
            "source": review_input.source,
            "options": review_input.options,
        },
        "rule_results": rule_results,
        "risk_level": risk_level,
        "needs_manual_review": needs_manual_review,
        "summary": (
            "烟草证规则校验通过"
            if not failed
            else "烟草证存在需要人工复核的规则问题"
        ),
        "manual_review": manual_review,
    }


def _review_rules(
    classification: TobaccoLicenseDocumentClassification,
    fields: TobaccoLicenseNormalizedFields,
) -> list[RuleResult]:
    return [
        RuleResult(
            rule_code="TOBACCO_LICENSE_TYPE_MATCH",
            rule_name="烟草证类型匹配",
            passed=classification.document_type == "tobacco_license",
            risk_level_on_failure=RiskLevel.HIGH,
            message="材料已识别为烟草专卖零售许可证",
            details={"expected": "tobacco_license", "actual": classification.document_type},
        ),
        _required_rule("TOBACCO_LICENSE_SUBJECT_NAME_PRESENT", "企业名称/字号名称存在", "subject_name", fields.subject_name),
        _required_rule("TOBACCO_LICENSE_ADDRESS_PRESENT", "经营场所存在", "business_address", fields.business_address),
        _required_rule("TOBACCO_LICENSE_PERSON_PRESENT", "负责人/经营者存在", "legal_person", fields.legal_person),
        _required_rule("TOBACCO_LICENSE_NO_PRESENT", "许可证号存在", "license_no", fields.license_no),
        _validity_rule(fields.valid_to),
    ]


def _required_rule(code: str, name: str, field: str, value: str | None) -> RuleResult:
    return RuleResult(
        rule_code=code,
        rule_name=name,
        passed=bool(value),
        risk_level_on_failure=RiskLevel.MEDIUM,
        message=name,
        details={"field": field, "actual": value},
    )


def _validity_rule(valid_to: str | None) -> RuleResult:
    if not valid_to:
        return RuleResult(
            rule_code="TOBACCO_LICENSE_VALIDITY_PERIOD",
            rule_name="烟草证有效期",
            passed=True,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="未识别截止日期，按长期有效处理",
            details={"field": "valid_to", "actual": valid_to, "assumed_long_term": True},
        )
    try:
        days = (date.fromisoformat(valid_to) - date.today()).days
    except ValueError:
        return RuleResult(
            rule_code="TOBACCO_LICENSE_VALIDITY_PERIOD",
            rule_name="烟草证有效期",
            passed=False,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message="有效期无法判断",
            details={"field": "valid_to", "actual": valid_to},
        )
    return RuleResult(
        rule_code="TOBACCO_LICENSE_VALIDITY_PERIOD",
        rule_name="烟草证有效期",
        passed=days > 30,
        risk_level_on_failure=RiskLevel.HIGH if days < 0 else RiskLevel.MEDIUM,
        message="烟草证有效期未过期" if days > 30 else "烟草证已过期或临期",
        details={"field": "valid_to", "actual": valid_to, "days_until_expiry": days},
    )


def _risk_level(failed: list[RuleResult]) -> RiskLevel:
    if any(rule.risk_level_on_failure == RiskLevel.HIGH for rule in failed):
        return RiskLevel.HIGH
    if any(rule.risk_level_on_failure == RiskLevel.MEDIUM for rule in failed):
        return RiskLevel.MEDIUM
    return RiskLevel.NONE


def _manual_reason(rule: RuleResult) -> str:
    if rule.rule_code == "TOBACCO_LICENSE_TYPE_MATCH":
        return "无法确认文件是烟草专卖零售许可证"
    if rule.rule_code == "TOBACCO_LICENSE_VALIDITY_PERIOD":
        return "烟草证有效期需要人工复核"
    return f"{rule.details.get('field')} 缺失"
