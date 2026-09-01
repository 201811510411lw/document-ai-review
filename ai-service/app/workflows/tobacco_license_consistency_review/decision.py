from typing import Any, Literal

from app.models import ReviewResult, ReviewStatus


OaReviewDecision = Literal["pass", "reject", "manual_review", "exception"]

FIELD_MISMATCH_REJECTION_THRESHOLD = 3
_HARD_REJECTION_DIFFERENCES = {
    ("BUSINESS_TOBACCO_TOBACCO_VALIDITY", "expired"),
}

_FIELD_RULES: dict[str, tuple[str, str]] = {
    "BUSINESS_LICENSE_TYPE_FOR_CONSISTENCY": (
        "business_license.document_type",
        "营业执照类型",
    ),
    "TOBACCO_LICENSE_TYPE_FOR_CONSISTENCY": (
        "tobacco_license.document_type",
        "烟草证类型",
    ),
    "TOBACCO_LICENSE_NO_FOR_CONSISTENCY": (
        "tobacco_license.license_no",
        "烟草证许可证号",
    ),
    "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH": ("subject_name", "主体名称"),
    "BUSINESS_TOBACCO_ADDRESS_MATCH": ("business_address", "经营地址"),
    "BUSINESS_TOBACCO_PERSON_MATCH": ("legal_person", "法定代表人/负责人"),
    "BUSINESS_TOBACCO_TOBACCO_VALIDITY": (
        "tobacco_license.valid_to",
        "烟草证有效期",
    ),
    "STORE_IN_STORE_HOLDER_NAME_MATCH": ("subject_name", "持证主体名称"),
    "STORE_IN_STORE_HOLDER_PERSON_MATCH": ("legal_person", "持证主体负责人"),
}


def oa_review_decision(result: ReviewResult) -> OaReviewDecision:
    if result.status in {ReviewStatus.CREATED, ReviewStatus.RUNNING}:
        return "exception"
    if result.manual_review and result.manual_review.status.value == "COMPLETED":
        if result.manual_review.action == "approved":
            return "pass"
        if result.manual_review.action == "rejected":
            return "reject"
        if result.manual_review.action == "request_more_info":
            return "manual_review"
    if result.status == ReviewStatus.FAILED:
        return "exception"

    rpa_info = (
        result.skill_result.get("rpa_verification")
        if isinstance(result.skill_result, dict)
        else None
    )
    rpa_status = str((rpa_info or {}).get("status") or "")
    if rpa_status == "ERROR":
        return "exception"
    if rpa_status in {"FAILED", "SUSPECTED", "NOT_FOUND"}:
        return "reject"

    failed = [rule for rule in result.rule_results if not rule.passed]
    if not failed:
        return "pass"
    technical_failure = any(
        rule.rule_code.endswith("_CHILD_REVIEW_READY")
        and rule.details.get("technical_error")
        for rule in failed
    )
    if technical_failure:
        return "exception"
    if any(
        (rule.rule_code, rule.details.get("difference"))
        in _HARD_REJECTION_DIFFERENCES
        for rule in failed
    ):
        return "reject"
    if len(oa_field_differences(result)) >= FIELD_MISMATCH_REJECTION_THRESHOLD:
        return "reject"
    # 少量业务差异随回调提交给 OA 下一节点复核，当前机器人节点不直接驳回。
    return "pass"


def oa_field_differences(result: ReviewResult) -> list[dict[str, Any]]:
    differences: list[dict[str, Any]] = []
    for rule in result.rule_results:
        metadata = _FIELD_RULES.get(rule.rule_code)
        if rule.passed or metadata is None:
            continue
        field, field_label = metadata
        details = dict(rule.details or {})
        differences.append(
            {
                "field": field,
                "field_label": field_label,
                "expected": details.get("expected"),
                "actual": details.get("actual"),
                "difference": details.get("difference"),
                "rule_code": rule.rule_code,
                "rule_name": rule.rule_name,
                "message": rule.message,
            }
        )
    return differences
