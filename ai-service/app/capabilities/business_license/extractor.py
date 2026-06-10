import re
from typing import Any

from app.capabilities.business_license.schemas import BusinessLicenseExtractedFields


REQUIRED_FIELDS = ["subject_name", "credit_code", "valid_to"]


def extract_business_license_fields(
    document_text: str,
) -> tuple[BusinessLicenseExtractedFields, dict[str, Any]]:
    text = _normalize_text(document_text)
    is_business_license = "营业执照" in text
    valid_from, valid_to, validity_parse_error = _extract_validity_period(text)

    extracted = BusinessLicenseExtractedFields(
        document_type="business_license" if is_business_license else "unknown",
        subject_name=_extract_line_value(text, ["名称", "企业名称", "市场主体名称"]),
        credit_code=_extract_line_value(text, ["统一社会信用代码", "注册号"]),
        business_address=_extract_line_value(text, ["住所", "经营场所", "营业场所"]),
        legal_person=_extract_line_value(text, ["法定代表人", "经营者", "负责人"]),
        established_date=_extract_date_value(text, ["成立日期", "注册日期"]),
        valid_from=valid_from,
        valid_to=valid_to,
        issue_authority=_extract_line_value(text, ["登记机关", "发照机关"]),
        issue_date=_extract_date_value(text, ["发证日期", "核准日期"]),
    )
    return extracted, {
        "missing_required_fields": _missing_required_fields(extracted),
        "date_parse_errors": ["validity_period"] if validity_parse_error else [],
    }


def _normalize_text(document_text: str) -> str:
    return (document_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_line_value(document_text: str, labels: list[str]) -> str | None:
    for label in labels:
        match = re.search(
            rf"(?:^|\n)\s*{re.escape(label)}\s*[:：]?\s*([^\n]+)",
            document_text,
        )
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _extract_date_value(document_text: str, labels: list[str]) -> str | None:
    value = _extract_line_value(document_text, labels)
    if not value:
        return None
    return _parse_date(value)


def _extract_validity_period(document_text: str) -> tuple[str | None, str | None, bool]:
    value = _extract_line_value(document_text, ["营业期限", "经营期限", "有效期"])
    if not value:
        return None, None, False
    if "长期" in value:
        return _parse_date(value), "长期", False
    dates = _parse_dates(value)
    if len(dates) >= 2:
        return dates[0], dates[1], False
    if len(dates) == 1:
        return None, dates[0], False
    return None, None, True


def _parse_dates(value: str) -> list[str]:
    dates = []
    for match in re.finditer(
        r"(\d{4})\s*(?:年|-|\.)\s*(\d{1,2})\s*(?:月|-|\.)\s*(\d{1,2})",
        value,
    ):
        year, month, day = match.groups()
        dates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    return dates


def _parse_date(value: str) -> str | None:
    dates = _parse_dates(value)
    return dates[0] if dates else None


def _missing_required_fields(
    extracted: BusinessLicenseExtractedFields,
) -> list[str]:
    missing = []
    for field_name in REQUIRED_FIELDS:
        if getattr(extracted, field_name) in (None, "", []):
            missing.append(field_name)
    return missing
