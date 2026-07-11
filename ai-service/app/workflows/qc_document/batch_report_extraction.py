import json
import os
import re
from datetime import date
from typing import Any

from pydantic import BaseModel

from app.models import RiskLevel, RuleResult


class BatchReportExtractedFields(BaseModel):
    document_type: str | None = None
    producer_name: str | None = None
    company_name: str | None = None
    product_name: str | None = None
    batch_no: str | None = None
    production_date: str | None = None


def extract_batch_report_fields(
    document_text: str,
) -> tuple[BatchReportExtractedFields, dict[str, Any]]:
    text = _normalize_text(document_text)
    metadata = {"has_text": bool(text)}

    # 优先使用 LLM 提取（更灵活），失败时自动回退正则
    llm_fields = _extract_with_llm(text)
    if llm_fields is not None:
        producer_name = llm_fields.get("producer_name") or llm_fields.get("company_name")
        product_name = llm_fields.get("product_name")
        production_date = llm_fields.get("production_date")
        batch_no = llm_fields.get("batch_no")
        company_name = llm_fields.get("company_name") or producer_name
        metadata["extraction_source"] = "llm"
    else:
        producer_name = _extract_line_value(text, ["厂名", "公司名", "生产商", "生产单位", "生产企业"])
        if not producer_name:
            producer_name = _extract_report_title_producer(text)
        product_name = _extract_line_value(text, ["产品名称", "商品名称", "品名", "样品名称"])
        batch_no = _extract_line_value(text, ["生产批号", "批号", "批次号", "批次"])
        production_date = _extract_date_value(text, ["生产日期", "生产时间", "制造日期"])
        company_name = producer_name
        metadata["extraction_source"] = "regex"

    extracted = BatchReportExtractedFields(
        document_type="batch_report" if text else None,
        producer_name=producer_name,
        company_name=company_name,
        product_name=product_name,
        batch_no=batch_no,
        production_date=production_date,
    )
    metadata["missing_required_fields"] = [
        field
        for field in ("producer_name", "product_name", "production_date")
        if not getattr(extracted, field)
    ]
    return extracted, metadata


def _extract_with_llm(document_text: str) -> dict[str, str | None] | None:
    """使用 LLM 从批次报告文本中抽取结构化字段。失败时返回 None（由调用方回退正则）。"""
    if not document_text or not document_text.strip():
        return None

    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model = (
        os.environ.get("BATCH_REPORT_LLM_EXTRACT_MODEL")
        or os.environ.get("QC_DOCUMENT_SKILL_REVIEW_MODEL")
        or os.environ.get("BUSINESS_LICENSE_SKILL_REVIEW_MODEL")
    )
    if not api_key or not model:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=60)
    except Exception:
        return None

    prompt = (
        "你是商品批次报告 OCR 字段抽取器。根据以下 OCR 文本抽取字段。\n"
        "只输出 JSON 对象，不要输出 Markdown 格式。\n"
        "字段包括：\n"
        "- product_name：产品名称、商品名称或品名\n"
        "- producer_name：厂名、公司名、生产商、生产单位或生产企业\n"
        "- production_date：生产日期，格式 YYYY-MM-DD\n"
        "- batch_no：生产批号、批号、批次号或批次\n"
        "\n"
        "注意事项：\n"
        "- 字段不存在或无法确定时输出 null\n"
        "- 不要编造数据\n"
        "- 日期统一为 YYYY-MM-DD 格式\n"
        "\n"
        f"OCR 文本：\n{document_text[:4000]}"
    )

    try:
        # 重试 2 次，temperature=0 保证稳定性
        import time

        last_error: Exception | None = None
        for _ in range(2):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                content = response.choices[0].message.content
                break
            except Exception as e:
                last_error = e
                time.sleep(1)
        else:
            if last_error is not None:
                raise last_error
            return None
    except Exception:
        return None

    if not content or not content.strip():
        return None

    # 解析 JSON，兼容 markdown 围栏
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
        if match:
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError:
                return None
        else:
            return None

    if not isinstance(parsed, dict):
        return None

    result: dict[str, str | None] = {}
    for key in ("product_name", "producer_name", "company_name", "production_date", "batch_no"):
        val = parsed.get(key)
        result[key] = _clean_llm_value(val)
    if not result.get("product_name") and not result.get("producer_name") and not result.get("production_date"):
        return None  # 啥都没提取到，让调用方回退正则
    return result


def _clean_llm_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in ("", "null", "None", "无", "/", "-"):
        return None
    return text


def review_batch_report_rules(
    *,
    declared_document_type: str | None,
    extracted_fields: dict[str, Any],
    source_fields: dict[str, Any],
    has_document_text: bool,
) -> dict[str, Any]:
    producer = extracted_fields.get("producer_name") or extracted_fields.get("company_name")
    product = extracted_fields.get("product_name")
    production_date = extracted_fields.get("production_date")
    batch_no = extracted_fields.get("batch_no")
    source_supplier = source_fields.get("supplier_name") or source_fields.get("vendor_name")
    source_product = source_fields.get("sku_name")
    source_production_date = _date_text(source_fields.get("production_date"))

    rules = [
        _rule(
            "BATCH_REPORT_TEXT_PRESENT",
            "批次报告文本可审核",
            has_document_text,
            RiskLevel.MEDIUM,
            {"has_document_text": has_document_text},
        ),
        _rule(
            "BATCH_REPORT_TYPE_MATCH",
            "批次报告类型匹配",
            declared_document_type == "batch_report",
            RiskLevel.HIGH,
            {"expected": "batch_report", "actual": declared_document_type},
        ),
        _rule(
            "BATCH_REPORT_PRODUCT_NAME_MATCH",
            "商品名称匹配",
            bool(product) and _name_matches(product, source_product),
            RiskLevel.MEDIUM,
            {"field": "product_name", "expected": source_product, "actual": product},
        ),
        _rule(
            "BATCH_REPORT_PRODUCER_NAME_MATCH",
            "生产者名称匹配",
            bool(producer) and _name_matches(producer, source_supplier),
            RiskLevel.MEDIUM,
            {"field": "producer_name", "expected": source_supplier, "actual": producer},
        ),
        _rule(
            "BATCH_REPORT_PRODUCTION_DATE_MATCH",
            "生产日期或生产批号匹配",
            _production_matches_source(
                production_date=production_date,
                batch_no=batch_no,
                source_production_date=source_production_date,
            ),
            RiskLevel.MEDIUM,
            {
                "field": "production_date",
                "expected": source_production_date,
                "actual": production_date,
                "batch_no": batch_no,
            },
        ),
    ]
    failed = [rule for rule in rules if not rule.passed]
    risk = (
        RiskLevel.HIGH
        if any(rule.risk_level_on_failure == RiskLevel.HIGH for rule in failed)
        else RiskLevel.MEDIUM
        if any(rule.risk_level_on_failure == RiskLevel.MEDIUM for rule in failed)
        else RiskLevel.NONE
    )
    return {
        "status": "PENDING_MANUAL_REVIEW" if failed else "REVIEWED",
        "risk_level": risk,
        "needs_manual_review": bool(failed),
        "summary": "商品批次报告规则校验通过" if not failed else "商品批次报告存在需要人工复核的规则问题",
        "manual_review_reasons": [_reason(rule) for rule in failed],
        "rule_results": rules,
    }


def _normalize_text(document_text: str) -> str:
    return (document_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _extract_line_value(document_text: str, labels: list[str]) -> str | None:
    lines = document_text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        for label in labels:
            if stripped == label and index + 1 < len(lines):
                value = _clean_value(lines[index + 1])
                if value:
                    return value
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


def _extract_report_title_producer(document_text: str) -> str | None:
    for line in document_text.splitlines()[:8]:
        stripped = line.strip()
        if stripped.endswith("产品检验报告"):
            producer = stripped[: -len("产品检验报告")].strip()
            if producer:
                return producer
    return None


def _extract_date_value(document_text: str, labels: list[str]) -> str | None:
    value = _extract_line_value(document_text, labels)
    if not value:
        return None
    match = re.search(
        r"(\d{4})\s*(?:年|-|\.|/)?\s*(\d{1,2})\s*(?:月|-|\.|/)?\s*(\d{1,2})",
        value,
    )
    if not match:
        return None
    year, month, day = match.groups()
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return None


def _production_matches_source(
    *,
    production_date: str | None,
    batch_no: str | None,
    source_production_date: str | None,
) -> bool:
    if not source_production_date:
        return False
    if production_date == source_production_date:
        return True
    digits = re.sub(r"\D", "", batch_no or "")
    expected = source_production_date.replace("-", "")
    return bool(expected and expected in digits)


def _name_matches(actual: Any, expected: Any) -> bool:
    actual_text = _compact_name(actual)
    expected_text = _compact_name(expected)
    if not actual_text or not expected_text:
        return False
    if actual_text == expected_text or actual_text in expected_text or expected_text in actual_text:
        return True
    actual_tokens = _name_tokens(actual_text)
    expected_tokens = _name_tokens(expected_text)
    return bool(actual_tokens and expected_tokens and actual_tokens & expected_tokens)


def _compact_name(value: Any) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"[\s　，,。.:：;；（）()【】\[\]_-]+", "", text).lower()


def _name_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for length in (4, 5, 6):
        tokens.update(value[index : index + length] for index in range(0, len(value) - length + 1))
    return {token for token in tokens if token}


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:10] if text else None


def _clean_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip("：:")
    if cleaned in {"", "/", "-", "无"}:
        return None
    return cleaned


def _rule(code: str, name: str, passed: bool, risk: RiskLevel, details: dict[str, Any]) -> RuleResult:
    return RuleResult(
        rule_code=code,
        rule_name=name,
        passed=passed,
        risk_level_on_failure=risk,
        message=name,
        details=details,
    )


def _reason(rule: RuleResult) -> str:
    if rule.rule_code == "BATCH_REPORT_TEXT_PRESENT":
        return "批次报告附件未获取到可审核文本，需要人工复核。"
    if rule.rule_code == "BATCH_REPORT_PRODUCT_NAME_MATCH":
        return "批次报告商品名称缺失或与来源商品不一致。"
    if rule.rule_code == "BATCH_REPORT_PRODUCER_NAME_MATCH":
        return "批次报告厂名/公司名缺失或与来源供应商不一致。"
    if rule.rule_code == "BATCH_REPORT_PRODUCTION_DATE_MATCH":
        return "批次报告生产日期或生产批号缺失，或与来源批次明细不一致。"
    return rule.message
