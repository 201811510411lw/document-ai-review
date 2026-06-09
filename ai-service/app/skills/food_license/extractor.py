import re
from collections.abc import Mapping
from typing import Any, Protocol

from app.skills.food_license.models import FoodLicenseExtractedFields


class MissingFieldsLlmAdapter(Protocol):
    def complete_missing_fields(
        self,
        *,
        document_text: str,
        extracted_fields: FoodLicenseExtractedFields,
        missing_fields: list[str],
    ) -> Mapping[str, Any]:
        ...


REQUIRED_FIELDS_FOR_REGEX_COMPLETENESS = [
    "subject_name",
    "credit_code",
    "license_no",
    "business_items",
    "valid_to",
]


def extract_food_license_fields(
    document_text: str,
    llm_adapter: MissingFieldsLlmAdapter | None = None,
) -> tuple[FoodLicenseExtractedFields, dict[str, Any]]:
    fields = _regex_extract(document_text or "")
    missing_fields = _missing_required_fields(fields)
    metadata: dict[str, Any] = {
        "extraction_mode": "regex",
        "llm_used": False,
        "missing_fields": missing_fields,
    }

    if not missing_fields or llm_adapter is None:
        return fields, metadata

    metadata["llm_used"] = True
    try:
        supplement = llm_adapter.complete_missing_fields(
            document_text=document_text,
            extracted_fields=fields,
            missing_fields=missing_fields,
        )
    except Exception as error:
        metadata["llm_error"] = type(error).__name__
        metadata["llm_reason"] = "fallback_to_regex"
        return fields, metadata

    metadata["extraction_mode"] = "regex_with_llm_supplement"
    return _merge_missing_fields(fields, supplement), metadata


def _regex_extract(document_text: str) -> FoodLicenseExtractedFields:
    compact_text = _normalize_text(document_text)
    valid_from, valid_to = _extract_valid_period(compact_text)
    return FoodLicenseExtractedFields(
        subject_name=_extract_line_value(
            compact_text,
            ["经营者名称", "企业名称", "主体名称", "名称"],
        ),
        credit_code=_extract_line_value(
            compact_text,
            ["统一社会信用代码", "社会信用代码"],
        ),
        license_no=_extract_line_value(
            compact_text,
            ["许可证编号", "编号"],
        ),
        business_address=_extract_line_value(
            compact_text,
            ["经营场所", "住所", "经营地址"],
        ),
        legal_person=_extract_line_value(
            compact_text,
            ["法定代表人", "负责人"],
        ),
        business_items=_extract_business_items(compact_text),
        valid_from=valid_from,
        valid_to=valid_to,
    )


def _normalize_text(document_text: str) -> str:
    return document_text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_line_value(document_text: str, labels: list[str]) -> str | None:
    for label in labels:
        match = re.search(
            rf"(?:^|\n)\s*{re.escape(label)}\s*[:：]?\s*([^\n]+)",
            document_text,
        )
        if match:
            value = _clean_value(match.group(1))
            if value:
                return value
    return None


def _extract_business_items(document_text: str) -> list[str]:
    raw_value = _extract_line_value(document_text, ["经营项目", "经营范围"])
    if not raw_value:
        return []
    items = [
        item.strip()
        for item in re.split(r"[、,，;；\n]+", raw_value)
        if item.strip()
    ]
    return items


def _extract_valid_period(document_text: str) -> tuple[str | None, str | None]:
    period_value = _extract_line_value(
        document_text,
        ["有效期限", "有效期", "有效期至", "有效期限至", "有效期截止日期"],
    )
    if period_value:
        dates = [_normalize_date(match) for match in _find_date_tokens(period_value)]
        dates = [date for date in dates if date is not None]
        if len(dates) >= 2:
            return dates[0], dates[1]
        if len(dates) == 1:
            return None, dates[0]

    valid_to_value = _extract_line_value(
        document_text,
        ["有效期至", "有效期限至", "有效期截止日期"],
    )
    if valid_to_value:
        return None, _normalize_date(valid_to_value)
    return None, None


def _find_date_tokens(value: str) -> list[str]:
    return re.findall(r"\d{4}\s*(?:年|-|\.)\s*\d{1,2}\s*(?:月|-|\.)\s*\d{1,2}\s*日?", value)


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(
        r"(\d{4})\s*(?:年|-|\.)\s*(\d{1,2})\s*(?:月|-|\.)\s*(\d{1,2})",
        value,
    )
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _clean_value(value: str) -> str:
    return value.strip().strip("：:").strip()


def _missing_required_fields(fields: FoodLicenseExtractedFields) -> list[str]:
    missing = []
    for field_name in REQUIRED_FIELDS_FOR_REGEX_COMPLETENESS:
        value = getattr(fields, field_name)
        if value in (None, "", []):
            missing.append(field_name)
    return missing


def _merge_missing_fields(
    fields: FoodLicenseExtractedFields,
    supplement: Mapping[str, Any],
) -> FoodLicenseExtractedFields:
    merged = fields.model_dump()
    for field_name, value in supplement.items():
        if field_name not in merged:
            continue
        if merged[field_name] in (None, "", []) and value not in (None, "", []):
            if field_name in {"valid_from", "valid_to", "issue_date"}:
                merged[field_name] = _normalize_date(str(value)) or str(value)
            elif field_name == "business_items" and isinstance(value, str):
                merged[field_name] = [
                    item.strip()
                    for item in re.split(r"[、,，;；\n]+", value)
                    if item.strip()
                ]
            else:
                merged[field_name] = value
    return FoodLicenseExtractedFields.model_validate(merged)
