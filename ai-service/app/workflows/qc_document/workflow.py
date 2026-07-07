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
from app.workflows.qc_document.product_report_extraction import (
    ProductReportExtractedFields,
    extract_product_report_fields,
    _valid_to as _product_report_valid_to,
)


qc_document_skill_rule_review_adapter = build_qc_document_skill_rule_review_adapter()
qc_document_remote_downloader = RemoteDocumentDownloader()


def _product_report_vision_fallback(
    review_input: Any,
    downloader: RemoteDocumentDownloader,
) -> dict[str, Any]:
    """当文本提取没有捞到签发日期时，用 Qwen Vision 直接从 PDF 图片中识别。"""
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
        "字段包括：issue_date（签发日期，格式 YYYY-MM-DD）。\n"
        "注意：签发日期通常在检验结论区域的右下角，即使有印章遮挡也要尽力识别。\n"
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
    if not fields.get("issue_date"):
        return {}
    return fields


def run_qc_document_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    review_input = input_context.input
    acquisition_result = acquire_document_text(
        review_input,
        downloader=qc_document_remote_downloader,
    )
    document_text = acquisition_result.document_text

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

    # ⭐ 视觉兜底：文本提取没捞到到期日时，用 Qwen Vision 从 PDF 图片直接识别签发日期
    if not extracted_fields.valid_to:
        ocr_fields = _product_report_vision_fallback(review_input, qc_document_remote_downloader)
        if ocr_fields.get("issue_date"):
            new_valid_to = _product_report_valid_to(ocr_fields["issue_date"])
            if new_valid_to:
                extracted_fields = ProductReportExtractedFields(
                    **{
                        **extracted_fields.model_dump(),
                        "issue_date": ocr_fields["issue_date"],
                        "sign_date": ocr_fields["issue_date"],
                        "valid_to": new_valid_to,
                    }
                )
                extraction_metadata["vision_fallback"] = {
                    "source": "qwen_ocr",
                    "issue_date": ocr_fields["issue_date"],
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
