from typing import Any

from app.models import ManualReview, ManualReviewStatus, ReviewInputContext
from app.tools.skill_rule_review import (
    build_qc_document_skill_rule_review_adapter,
    load_skill_text,
)
from app.workflows.qc_document.product_report_extraction import (
    extract_product_report_fields,
)


qc_document_skill_rule_review_adapter = build_qc_document_skill_rule_review_adapter()


def run_qc_document_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    review_input = input_context.input
    document_text = (review_input.ocr_text or "").strip()
    if not document_text:
        file_input = review_input.file or review_input.document
        document_text = ((getattr(file_input, "stub_text", None) or "") if file_input else "").strip()

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
                "document_input": {
                    "input_type": "empty" if not document_text else "ocr_text",
                },
                "document_classification": {
                    "document_type": "unknown",
                    "confidence": 0.0,
                    "reasons": ["declared_document_type 不在首期支持范围内"],
                },
                "extracted_fields": {},
                "extraction_metadata": {},
                "source_evidence": {
                    "supplier_name": review_input.supplier_name,
                    "declared_document_type": review_input.declared_document_type,
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
                "document_input": {
                    "input_type": "empty",
                },
                "document_classification": {
                    "document_type": "unknown",
                    "confidence": 0.0,
                    "reasons": ["未获取到 OCR 文本或 stub_text"],
                },
                "extracted_fields": {},
                "extraction_metadata": {},
                "source_evidence": {
                    "supplier_name": review_input.supplier_name,
                    "declared_document_type": review_input.declared_document_type,
                },
            },
        }

    extracted_fields, extraction_metadata = extract_product_report_fields(document_text)
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
            "document_input": {
                "input_type": "ocr_text",
            },
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
