import re
from datetime import date, timedelta

from pydantic import BaseModel, Field


class ProductReportExtractedFields(BaseModel):
    document_type: str | None = None
    report_no: str | None = None
    product_name: str | None = None
    sample_name: str | None = None
    vendor_name_extracted: str | None = None
    entrusting_party: str | None = None
    manufacturer_name: str | None = None
    inspection_conclusion: str | None = None
    inspection_result: str | None = None
    batch_no: str | None = None
    production_date: str | None = None
    issue_date: str | None = None
    sign_date: str | None = None
    approval_date: str | None = None
    valid_to: str | None = None
    inspection_items: list[dict[str, str]] = Field(default_factory=list)


REQUIRED_FIELDS = [
    "document_type",
    "report_no",
    "product_name",
    "vendor_name_extracted",
    "inspection_conclusion",
]


def extract_product_report_fields(
    document_text: str,
) -> tuple[ProductReportExtractedFields, dict[str, object]]:
    text = _normalize_text(document_text)
    report_no = _extract_line_value(text, ["报告编号", "报告号", "检验报告编号"])
    product_name = _extract_line_value(text, ["产品名称", "样品名称"])
    vendor_name = _extract_line_value(text, ["受检单位", "委托单位", "送检单位"])
    manufacturer_name = _extract_line_value(text, ["生产单位", "生产企业", "生产商"])
    batch_no = _extract_line_value(text, ["批次号", "批号", "批次"])
    production_date = _extract_date_value(text, ["生产日期"])
    issue_date = _extract_date_value(text, ["签发日期", "签署日期", "报告日期"])
    approval_date = _extract_date_value(text, ["批准日期", "批准时间"])
    valid_to = _valid_to(issue_date or approval_date)
    conclusion = _extract_conclusion(text)
    inspection_items = _extract_inspection_items(text)

    extracted = ProductReportExtractedFields(
        document_type="product_report" if text.strip() else None,
        report_no=report_no,
        product_name=product_name,
        sample_name=product_name,
        vendor_name_extracted=vendor_name,
        entrusting_party=vendor_name,
        manufacturer_name=manufacturer_name,
        inspection_conclusion=conclusion,
        inspection_result=conclusion,
        batch_no=batch_no,
        production_date=production_date,
        issue_date=issue_date,
        sign_date=issue_date,
        approval_date=approval_date,
        valid_to=valid_to,
        inspection_items=inspection_items,
    )
    metadata = {
        "missing_required_fields": _missing_required_fields(extracted),
        "inspection_items_count": len(inspection_items),
    }
    return extracted, metadata


def _normalize_text(document_text: str) -> str:
    return (document_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


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


def _extract_date_value(document_text: str, labels: list[str]) -> str | None:
    value = _extract_line_value(document_text, labels)
    if not value:
        return None
    match = re.search(r"(\d{4})\s*(?:年|-|\.|/)\s*(\d{1,2})\s*(?:月|-|\.|/)\s*(\d{1,2})", value)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip("：:")
    if cleaned in {"", "/", "-", "无"}:
        return None
    return cleaned


def _extract_inspection_items(document_text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    in_result_section = False
    seen_result_section = False
    for line in document_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("检测结果"):
            in_result_section = True
            seen_result_section = True
            continue
        if stripped.startswith(("备注", "声明", "***")):
            in_result_section = False
            continue
        if seen_result_section and not in_result_section:
            continue
        if not in_result_section and not re.match(r"^\d+[.、]\s*", stripped):
            continue
        if stripped.startswith("序号"):
            continue
        match = re.match(r"^\s*\d+[.、]?\s*(.+?)\s+(.+?)\s*$", stripped)
        if not match:
            continue
        name, remainder = match.groups()
        if not name or _is_non_inspection_item(name):
            continue
        result = _inspection_result_from_remainder(remainder)
        if result:
            items.append({"name": name.strip(), "result": result})
    return items


def _is_non_inspection_item(name: str) -> bool:
    return any(
        token in name
        for token in (
            "报告无批准人",
            "未经本公司",
            "样品信息由客户",
            "不得擅自使用",
            "如果对检测结果有异议",
            "扫描报告首页",
            "按照二级采样方案",
            "按照三级采样方案",
        )
    )


def _inspection_result_from_remainder(remainder: str) -> str | None:
    value = remainder.strip()
    if not value:
        return None
    value = re.sub(
        r"^(?:/|CFU/g|/25g|g/100g|g/kg|mg/kg|mg/g)\s+",
        "",
        value,
        flags=re.I,
    )
    if " / " in value:
        value = value.split(" / ", 1)[0]
    else:
        value = re.split(r"\s+符合\s+", value, maxsplit=1)[0]
    return _clean_value(value)


def _extract_conclusion(document_text: str) -> str | None:
    direct = _extract_line_value(document_text, ["检验结论", "检验结果", "结论"])
    if direct:
        return direct
    match = re.search(
        r"(经检测，(?:所检项目|有标准指标的项目)符合.+?(?:要求。(?:\s*无标准指标的项\s*目仅提供检测数据。)?))",
        document_text,
        flags=re.S,
    )
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _valid_to(issue_or_approval_date: str | None) -> str | None:
    if not issue_or_approval_date:
        return None
    try:
        return (date.fromisoformat(issue_or_approval_date) + timedelta(days=180)).isoformat()
    except ValueError:
        return None


def _missing_required_fields(
    extracted: ProductReportExtractedFields,
) -> list[str]:
    missing = []
    for field_name in REQUIRED_FIELDS:
        if getattr(extracted, field_name) in (None, "", []):
            missing.append(field_name)
    if not (extracted.batch_no or extracted.production_date):
        missing.append("batch_no_or_production_date")
    if not (extracted.issue_date or extracted.approval_date or extracted.sign_date):
        missing.append("issue_or_approval_date")
    return missing
