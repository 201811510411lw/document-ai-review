import os
from typing import Any

from app.models import ManualReview, ManualReviewStatus, ReviewInputContext
from app.tools.document_text_acquisition import acquire_document_text
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.skill_rule_review import (
    build_qc_document_skill_rule_review_adapter,
    load_skill_text,
    parse_json_object,
)
from app.workflows.qc_document.batch_report_extraction import (
    extract_batch_report_fields,
)
from app.workflows.qc_document.product_report_extraction import (
    ProductReportExtractedFields,
    _is_field_label,
    extract_product_report_fields,
    _valid_to as _product_report_valid_to,
)


qc_document_skill_rule_review_adapter = build_qc_document_skill_rule_review_adapter()
qc_document_remote_downloader = RemoteDocumentDownloader()


def _product_report_vision_fallback(
    review_input: Any,
    downloader: RemoteDocumentDownloader,
) -> dict[str, Any]:
    """文本层缺少核心字段时，用 Qwen Vision 从原件图片补充识别。"""
    file_input = getattr(review_input, "file", None) or getattr(
        review_input, "document", None
    )
    if file_input is None:
        return {}
    file_uri = getattr(file_input, "file_uri", None)
    if not file_uri:
        return {}

    try:
        remote_doc = downloader.download(file_uri)
    except Exception:
        return {}
    if not remote_doc or not remote_doc.content:
        return {}

    # PDF/图片 → base64 data URL
    try:
        from app.tools.qwen_ocr_adapter import (
            _create_chat_completion_content,
            _source_page_data_urls,
        )

        page_data_urls = _source_page_data_urls(
            remote_doc.content, remote_doc.mime_type or "image/png"
        )
    except Exception:
        return {}
    if not page_data_urls:
        return {}

    api_key = os.environ.get("OPENAI_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL")
    model = (
        os.environ.get("FOOD_LICENSE_QWEN_OCR_MODEL")
        or os.environ.get("BUSINESS_LICENSE_QWEN_OCR_MODEL", "")
    )
    if not api_key or not model:
        return {}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url, timeout=90)
    except Exception:
        return {}

    prompt = (
        "你是商品报告 OCR 字段抽取器。请根据图片中的可见文字抽取字段。\n"
        "只输出 JSON 对象，不要输出 Markdown。\n"
        "字段包括：report_no、product_name、vendor_name_extracted、entrusting_party、"
        "manufacturer_name、batch_no、production_date、issue_date、approval_date、"
        "inspection_conclusion。日期统一为 YYYY-MM-DD。\n"
        "必须返回字段后的实际内容，不得返回 Report No.、Sample Name、Supplier Name、"
        "Clientele、名称等字段标题或表头。签发日期通常在检验结论区域的右下角。\n"
        "完全无法确定时输出 null。"
    )

    # 只取第一页（签发日期一般就在第一页）
    try:
        content_text, _ = _create_chat_completion_content(
            client=client,
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": page_data_urls[0]}},
                    ],
                }
            ],
            max_attempts=2,
        )
    except Exception:
        return {}

    fields = parse_json_object(content_text) or {}
    return fields if isinstance(fields, dict) else {}


_PRODUCT_REPORT_VISION_CORE_FIELDS = (
    "report_no",
    "product_name",
    "vendor_name_extracted",
    "entrusting_party",
    "manufacturer_name",
)


def _needs_product_report_vision_fallback(fields: ProductReportExtractedFields) -> bool:
    return (
        any(not getattr(fields, field_name) for field_name in _PRODUCT_REPORT_VISION_CORE_FIELDS)
        or not fields.valid_to
    )


def _merge_product_report_vision_fields(
    extracted_fields: ProductReportExtractedFields,
    vision_fields: dict[str, Any],
) -> tuple[ProductReportExtractedFields, dict[str, str]]:
    merged = extracted_fields.model_dump()
    accepted: dict[str, str] = {}
    for field_name in (
        "report_no",
        "product_name",
        "vendor_name_extracted",
        "entrusting_party",
        "manufacturer_name",
        "batch_no",
        "production_date",
        "issue_date",
        "approval_date",
        "inspection_conclusion",
    ):
        if merged.get(field_name):
            continue
        candidate = str(vision_fields.get(field_name) or "").strip()
        if not candidate or _is_field_label(candidate):
            continue
        merged[field_name] = candidate
        accepted[field_name] = candidate

    vendor_name = merged.get("vendor_name_extracted") or merged.get("entrusting_party")
    if vendor_name:
        merged["vendor_name_extracted"] = vendor_name
        merged["entrusting_party"] = vendor_name
    if merged.get("product_name"):
        merged["sample_name"] = merged["product_name"]
    if merged.get("issue_date"):
        merged["sign_date"] = merged["issue_date"]
    if not merged.get("valid_to"):
        merged["valid_to"] = _product_report_valid_to(
            merged.get("issue_date") or merged.get("approval_date")
        )
    return ProductReportExtractedFields(**merged), accepted


def run_qc_document_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    review_input = input_context.input
    acquisition_result = acquire_document_text(
        review_input,
        downloader=qc_document_remote_downloader,
    )
    document_text = acquisition_result.document_text

    if review_input.declared_document_type == "batch_report":
        return _run_batch_report_workflow(
            input_context=input_context,
            document_text=document_text,
            acquisition_result=acquisition_result,
        )

    if review_input.declared_document_type != "product_report":
        return {
            "input_context": input_context,
            "implementation_status": "implemented",
            "status": "PENDING_MANUAL_REVIEW",
            "risk_level": "MEDIUM",
            "needs_manual_review": True,
            "summary": "当前 qc_document_review 首期仅正式支持 product_report。",
            "manual_review": ManualReview(
                status=ManualReviewStatus.PENDING,
                reasons=["当前首期仅支持 product_report，需要人工复核"],
            ),
            "rule_results": [],
            "capability_names": [],
            "document_type": review_input.declared_document_type or "qc_document",
            "skill_result": {
                "document_input": acquisition_result.document_input,
                "document_classification": {
                    "document_type": "unknown",
                    "confidence": 0.0,
                    "reasons": ["declared_document_type 不在首期支持范围内"],
                },
                "extracted_fields": {},
                "extraction_metadata": acquisition_result.extraction_metadata,
                "source_evidence": {
                    "supplier_name": review_input.supplier_name,
                    "declared_document_type": review_input.declared_document_type,
                    "source": review_input.source,
                    "options": review_input.options,
                },
            },
        }

    if not document_text:
        return {
            "input_context": input_context,
            "implementation_status": "implemented",
            "status": "PENDING_MANUAL_REVIEW",
            "risk_level": "MEDIUM",
            "needs_manual_review": True,
            "summary": "产品报告缺少可审核文本，需要人工复核。",
            "manual_review": ManualReview(
                status=ManualReviewStatus.PENDING,
                reasons=["产品报告文本为空，需要人工复核"],
            ),
            "rule_results": [],
            "capability_names": ["product_report"],
            "document_type": "product_report",
            "skill_result": {
                "document_input": acquisition_result.document_input,
                "document_classification": {
                    "document_type": "unknown",
                    "confidence": 0.0,
                    "reasons": ["未获取到 OCR 文本或 stub_text"],
                },
                "extracted_fields": {},
                "extraction_metadata": acquisition_result.extraction_metadata,
                "source_evidence": {
                    "supplier_name": review_input.supplier_name,
                    "declared_document_type": review_input.declared_document_type,
                },
            },
        }

    extracted_fields, extraction_metadata = extract_product_report_fields(document_text)
    extraction_metadata = {
        **acquisition_result.extraction_metadata,
        **extraction_metadata,
    }

    # PDF 文本层常丢失表格的实际单元格，或把双语表头当作字段值。
    if _needs_product_report_vision_fallback(extracted_fields):
        ocr_fields = _product_report_vision_fallback(review_input, qc_document_remote_downloader)
        if ocr_fields:
            extracted_fields, accepted_fields = _merge_product_report_vision_fields(
                extracted_fields,
                ocr_fields,
            )
            extraction_metadata["vision_fallback"] = {
                "source": "qwen_ocr",
                "accepted_fields": accepted_fields,
            }

    extracted_payload = extracted_fields.model_dump(mode="json")
    skill_name = "qc-document-review"
    rules_result = qc_document_skill_rule_review_adapter.review(
        skill_name=skill_name,
        skill_text=load_skill_text(skill_name),
        review_payload={
            "task_id": input_context.task_id,
            "declared_document_type": "product_report",
            "source_fields": {
                "supplier_name": review_input.supplier_name,
                "supplier_credit_code": review_input.supplier_credit_code,
            },
            "extracted_fields": extracted_payload,
            "extraction_metadata": extraction_metadata,
            "source": review_input.source,
            "options": review_input.options,
        },
    )
    status = rules_result.get("status", "PENDING_MANUAL_REVIEW")
    needs_manual_review = rules_result.get("needs_manual_review", True)
    if rules_result.get("risk_level") == "HIGH":
        status = "FAILED"
        needs_manual_review = False
    manual_review = ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=(
            list(rules_result.get("manual_review_reasons", []))
            if needs_manual_review
            else []
        ),
    )
    return {
        "input_context": input_context,
        "implementation_status": "implemented",
        "status": status,
        "risk_level": rules_result.get("risk_level", "MEDIUM"),
        "needs_manual_review": needs_manual_review,
        "summary": rules_result.get("summary", "产品报告 Skill 规则审核完成。"),
        "manual_review": manual_review,
        "rule_results": rules_result.get("rule_results", []),
        "capability_names": ["product_report"],
        "document_type": "product_report",
        "skill_result": {
            "document_input": acquisition_result.document_input,
            "document_classification": {
                "document_type": "product_report",
                "confidence": 1.0,
                "reasons": ["首期 declared_document_type=product_report，且文本已进入产品报告抽取链路"],
            },
            "extracted_fields": extracted_payload,
            "extraction_metadata": extraction_metadata,
            "source_evidence": {
                "supplier_name": review_input.supplier_name,
                "declared_document_type": review_input.declared_document_type,
                "source": review_input.source,
                "options": review_input.options,
                "skill_rule_review_metadata": {
                    **dict(rules_result.get("metadata") or {}),
                    "skill_name": skill_name,
                },
            },
        },
    }


def _run_batch_report_workflow(
    *,
    input_context: ReviewInputContext,
    document_text: str,
    acquisition_result: Any,
) -> dict[str, Any]:
    review_input = input_context.input
    extracted_fields, extraction_metadata = extract_batch_report_fields(document_text)
    extraction_metadata = {
        **acquisition_result.extraction_metadata,
        **extraction_metadata,
    }
    extracted_payload = extracted_fields.model_dump(mode="json")
    source_fields = {
        "supplier_name": review_input.supplier_name,
        "supplier_credit_code": review_input.supplier_credit_code,
        "vendor_name": review_input.source.get("vendor_name"),
        "sku_name": review_input.source.get("sku_name"),
        "production_date": review_input.source.get("production_date"),
        "expired_time": review_input.source.get("expired_time"),
    }
    # 走 LLM Skill 规则审核（与 product_report 使用同一 adapter）
    skill_name = "qc-document-review"
    rules_result = qc_document_skill_rule_review_adapter.review(
        skill_name=skill_name,
        skill_text=load_skill_text(skill_name),
        review_payload={
            "task_id": input_context.task_id,
            "declared_document_type": "batch_report",
            "source_fields": source_fields,
            "extracted_fields": {
                **extracted_payload,
                "has_document_text": bool(document_text),
            },
            "extraction_metadata": extraction_metadata,
            "source": review_input.source,
            "options": review_input.options,
        },
    )
    status = rules_result.get("status", "PENDING_MANUAL_REVIEW")
    needs_manual_review = rules_result.get("needs_manual_review", True)
    if rules_result.get("risk_level") == "HIGH":
        status = "FAILED"
        needs_manual_review = False
    manual_review = ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=(
            list(rules_result.get("manual_review_reasons", []))
            if needs_manual_review
            else []
        ),
    )
    return {
        "input_context": input_context,
        "implementation_status": "implemented",
        "status": status,
        "risk_level": rules_result.get("risk_level", "MEDIUM"),
        "needs_manual_review": needs_manual_review,
        "summary": rules_result.get("summary", "商品批次报告 Skill 规则审核完成。"),
        "manual_review": manual_review,
        "rule_results": rules_result.get("rule_results", []),
        "capability_names": ["batch_report"],
        "document_type": "batch_report",
        "skill_result": {
            "document_input": acquisition_result.document_input,
            "document_classification": {
                "document_type": "batch_report",
                "confidence": 1.0,
                "reasons": ["declared_document_type=batch_report，进入商品批次报告抽取链路"],
            },
            "extracted_fields": extracted_payload,
            "extraction_metadata": extraction_metadata,
            "source_evidence": {
                "supplier_name": review_input.supplier_name,
                "declared_document_type": review_input.declared_document_type,
                "source_fields": source_fields,
                "source": review_input.source,
                "options": review_input.options,
                "skill_rule_review_metadata": {
                    **dict(rules_result.get("metadata") or {}),
                    "skill_name": skill_name,
                },
            },
        },
    }
