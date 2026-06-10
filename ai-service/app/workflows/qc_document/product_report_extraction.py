import re
from pydantic import BaseModel, Field


class ProductReportExtractedFields(BaseModel):
    document_type: str | None = None
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
    inspection_items: list[dict[str, str]] = Field(default_factory=list)


REQUIRED_FIELDS = [
    "document_type",
    "product_name",
    "vendor_name_extracted",
    "inspection_conclusion",
    "batch_no",
    "issue_date",
]


def extract_product_report_fields(
    document_text: str,
) -> tuple[ProductReportExtractedFields, dict[str, object]]:
    text = _normalize_text(document_text)
    product_name = _extract_line_value(text, ["产品名称", "样品名称"])
    vendor_name = _extract_line_value(text, ["受检单位", "委托单位", "送检单位"])
    manufacturer_name = _extract_line_value(text, ["生产单位", "生产企业", "生产商"])
    batch_no = _extract_line_value(text, ["批次号", "批号", "批次"])
    production_date = _extract_date_value(text, ["生产日期"])
    issue_date = _extract_date_value(text, ["签发日期", "签署日期", "报告日期"])
    conclusion = _extract_line_value(text, ["检验结论", "检验结果", "结论"])
    inspection_items = _extract_inspection_items(text)

    extracted = ProductReportExtractedFields(
        document_type="product_report" if text.strip() else None,
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
            value = match.group(1).strip()
            if value:
                return value
    return None


def _extract_date_value(document_text: str, labels: list[str]) -> str | None:
    value = _extract_line_value(document_text, labels)
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


def _extract_inspection_items(document_text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for line in document_text.splitlines():
        match = re.match(r"^\s*\d+[.、]\s*(.+?)\s+(.+?)\s*$", line)
        if not match:
            continue
        name, result = match.groups()
        if name and result:
            items.append({"name": name.strip(), "result": result.strip()})
    return items


def _missing_required_fields(
    extracted: ProductReportExtractedFields,
) -> list[str]:
    missing = []
    for field_name in REQUIRED_FIELDS:
        if getattr(extracted, field_name) in (None, "", []):
            missing.append(field_name)
    return missing
