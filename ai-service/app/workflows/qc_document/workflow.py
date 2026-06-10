from typing import Any

from app.models import ManualReview, ManualReviewStatus, ReviewInputContext
from app.workflows.qc_document.product_report_extraction import (
    extract_product_report_fields,
)
from app.workflows.qc_document.product_report_rules import (
    evaluate_product_report_rules,
)


def run_qc_document_workflow(input_context: ReviewInputContext) -> dict[str, Any]:
    review_input = input_context.input
    document_text = (review_input.ocr_text or "").strip()
    if not document_text:
        file_input = review_input.file or review_input.document
        document_text = ((getattr(file_input, "stub_text", None) or "") if file_input else "").strip()

    if review_input.declared_document_type != "product_report":
        return {
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
    rules_result = evaluate_product_report_rules(
        declared_document_type="product_report",
        source_vendor_name=review_input.supplier_name,
        extracted_fields={
            "vendor_name": extracted_payload.get("vendor_name_extracted")
            or extracted_payload.get("entrusting_party")
            or extracted_payload.get("manufacturer_name"),
            "product_name": extracted_payload.get("product_name")
            or extracted_payload.get("sample_name"),
            "batch_number": extracted_payload.get("batch_no"),
            "production_date": extracted_payload.get("production_date"),
            "conclusion": extracted_payload.get("inspection_conclusion")
            or extracted_payload.get("inspection_result"),
        },
    )
    status = rules_result["status"]
    needs_manual_review = rules_result["needs_manual_review"]
    if rules_result["risk_level"] == "HIGH":
        status = "FAILED"
        needs_manual_review = False
    manual_review = ManualReview(
        status=(
            ManualReviewStatus.PENDING
            if needs_manual_review
            else ManualReviewStatus.NOT_REQUIRED
        ),
        reasons=(
            list(rules_result["manual_review_reasons"])
            if needs_manual_review
            else []
        ),
    )
    return {
        "implementation_status": "implemented",
        "status": status,
        "risk_level": rules_result["risk_level"],
        "needs_manual_review": needs_manual_review,
        "summary": rules_result["summary"],
        "manual_review": manual_review,
        "rule_results": rules_result["rule_results"],
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
            },
        },
    }
