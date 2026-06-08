from datetime import date
import re

from app.models import ReviewInput, RiskLevel, RuleResult
from app.skills.food_license.models import FoodLicenseNormalizedFields


def evaluate_food_license_rules(
    document_text: str,
    document_type: str,
    fields: FoodLicenseNormalizedFields,
    review_input: ReviewInput,
) -> list[RuleResult]:
    today = date.today()
    document_supported = document_type == "food_license"
    license_exists = bool(document_text) and document_supported
    license_no_present = bool(fields.license_no)
    credit_code_matches = (
        bool(fields.credit_code) and fields.credit_code == review_input.supplier_credit_code
    )
    valid_to = _parse_date(fields.valid_to)
    not_expired = valid_to is not None and valid_to >= today
    business_scope_covered = any("食品" in item for item in fields.business_items)

    return [
        RuleResult(
            rule_code="FOOD_LICENSE_EXISTS",
            rule_name="证照是否存在",
            passed=license_exists,
            risk_level_on_failure=RiskLevel.HIGH,
            message="已识别食品安全证照" if license_exists else "未识别食品安全证照",
        ),
        RuleResult(
            rule_code="FOOD_LICENSE_NO_REQUIRED",
            rule_name="许可证编号是否为空",
            passed=license_no_present,
            risk_level_on_failure=RiskLevel.HIGH,
            message="许可证编号已提取" if license_no_present else "许可证编号为空",
        ),
        RuleResult(
            rule_code="CREDIT_CODE_MATCH",
            rule_name="统一社会信用代码是否一致",
            passed=credit_code_matches,
            risk_level_on_failure=RiskLevel.HIGH,
            message=(
                "证照信用代码与供应商信用代码一致"
                if credit_code_matches
                else "证照信用代码与供应商信用代码不一致"
            ),
        ),
        RuleResult(
            rule_code="FOOD_LICENSE_EXPIRED",
            rule_name="证照是否过期",
            passed=not_expired,
            risk_level_on_failure=RiskLevel.HIGH,
            message="证照在有效期内" if not_expired else "证照已过期或有效期缺失",
        ),
        RuleResult(
            rule_code="BUSINESS_SCOPE_COVERED",
            rule_name="经营项目是否覆盖食品业务",
            passed=business_scope_covered,
            risk_level_on_failure=RiskLevel.MEDIUM,
            message=(
                "经营项目覆盖食品业务"
                if business_scope_covered
                else "经营项目未覆盖食品业务"
            ),
        ),
    ]


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    match = re.search(r"(\d{4})[-年.](\d{1,2})[-月.](\d{1,2})", value)
    if not match:
        return None
    year, month, day = (int(part) for part in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None
