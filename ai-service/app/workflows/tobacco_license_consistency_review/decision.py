from typing import Literal

from app.models import ReviewResult, ReviewStatus, RuleResult


OaReviewDecision = Literal["pass", "reject", "manual_review", "exception"]


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
    deterministic_failures = [rule for rule in failed if _is_deterministic_rejection(rule)]
    technical_failure = any(
        rule.rule_code.endswith("_CHILD_REVIEW_READY")
        and rule.details.get("technical_error")
        for rule in failed
    )
    if deterministic_failures and not technical_failure:
        return "reject"
    return "manual_review"


def _is_deterministic_rejection(rule: RuleResult) -> bool:
    if rule.rule_code in {
        "BUSINESS_TOBACCO_SUBJECT_NAME_MATCH",
        "BUSINESS_TOBACCO_ADDRESS_MATCH",
        "BUSINESS_TOBACCO_PERSON_MATCH",
    }:
        # A missing required value is a deterministic negative for the OA flow;
        # only infrastructure/source acquisition failures remain exceptions.
        return not bool(rule.details.get("expected")) or not bool(rule.details.get("actual")) or (
            rule.details.get("expected") != rule.details.get("actual")
        )
    if rule.rule_code.endswith("_TYPE_FOR_CONSISTENCY"):
        return rule.details.get("actual") != rule.details.get("expected")
    if rule.rule_code == "TOBACCO_LICENSE_NO_FOR_CONSISTENCY":
        return rule.details.get("difference") == "actual_missing"
    return rule.rule_code == "BUSINESS_TOBACCO_TOBACCO_VALIDITY" and rule.details.get(
        "difference"
    ) in {"expired", "actual_missing", "invalid_date"}
