import json
import os
from typing import Any

import pytest
from pypdf.errors import PdfReadError, PdfStreamError

from app.core.config import load_local_env
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.srm.business_license_tasks import (
    fetch_one_business_license_source_task,
)
from app.services.review_service import ReviewService
from app.tools.license_file_recognition import recognize_license_file
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.vision_adapter import build_business_license_vision_adapter


pytestmark = pytest.mark.manual


_ENV_KEYS = {
    "OPENAI_API_KEY",
    "OPENAI_API_KEY1",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "BUSINESS_LICENSE_VISION_PROVIDER",
    "BUSINESS_LICENSE_VISION_MODEL",
    "SRM_MYSQL_HOST",
    "SRM_MYSQL_PORT",
    "SRM_MYSQL_USER",
    "SRM_MYSQL_PASSWORD",
    "SRM_MYSQL_DATABASE",
}


def test_manual_mysql_pdf_llm_extraction_snapshot():
    _load_test_env()

    task = fetch_one_business_license_source_task(
        MySqlFetchClient(mysql_settings_from_env())
    )
    if task is None:
        pytest.skip("business_license_tasks default SQL returned no rows")

    downloader = RemoteDocumentDownloader()
    adapter = build_business_license_vision_adapter()
    if getattr(adapter, "implementation_status", None) == "fake":
        pytest.fail(
            "BUSINESS_LICENSE_VISION_PROVIDER must be aliyun "
            "for this manual extraction test",
            pytrace=False,
        )

    record = task.record
    remote_document = downloader.download(record.file_url)
    if remote_document.file_type != "pdf":
        pytest.skip(f"source document is not a PDF: {remote_document.file_type}")

    source_snapshot = {
        "record": record.model_dump(mode="json", exclude={"source_payload", "file_url"}),
        "review_input": {
            "supplier_name": task.review_input.supplier_name,
            "supplier_credit_code": task.review_input.supplier_credit_code,
            "declared_document_type": task.review_input.declared_document_type,
            "file": (
                _document_file_snapshot(task.review_input.file)
                if task.review_input.file
                else None
            ),
            "source": {
                "source_system": task.review_input.source.get("source_system"),
                "tenant": task.review_input.source.get("tenant"),
                "record_id": task.review_input.source.get("record_id"),
                "attachment_ref_id": task.review_input.source.get("attachment_ref_id"),
                "document_category": task.review_input.source.get("document_category"),
                "document_type_code": task.review_input.source.get("document_type_code"),
                "file_store_key": task.review_input.source.get("file_store_key"),
            },
        },
        "remote_document": {
            "file_type": remote_document.file_type,
            "mime_type": remote_document.mime_type,
            "status_code": remote_document.status_code,
            "source_url": _truncate(remote_document.source_url, 180),
            "content_bytes": len(remote_document.content),
        },
    }
    if _debug_enabled():
        _print_json({"source": source_snapshot})

    try:
        recognition_result = recognize_license_file(
            task.review_input,
            adapter=adapter,
            downloader=downloader,
            include_legacy_vision_metadata=True,
        )
    except (PdfReadError, PdfStreamError) as error:
        pytest.skip(f"source document is not a readable PDF: {type(error).__name__}")
    review_result = ReviewService().review(
        task.review_input,
        use_case_name="business_license",
    )
    compliance_result = review_result.model_dump(mode="json")

    if _debug_enabled():
        _print_json(
            {
                **source_snapshot,
                "recognition_result": {
                    "document_input": recognition_result.document_input.__dict__,
                    "document_text": recognition_result.document_text,
                    "structured_fields": recognition_result.structured_fields,
                    "extraction_metadata": recognition_result.extraction_metadata,
                },
                "compliance_result": compliance_result,
            }
        )
    else:
        _print_json(
            {
                "record_id": record.record_id,
                "vendor_name": record.vendor_name,
                "business_num": record.business_num,
                "file_name": record.file_name,
                "recognition_result": {
                    "document_input": recognition_result.document_input.__dict__,
                    "compliance_fields": _compliance_fields(
                        recognition_result.structured_fields
                    ),
                },
                "compliance_result": _compact_compliance_result(compliance_result),
            }
        )

    assert recognition_result.extraction_metadata.get("llm_file_extractor")
    assert "needs_manual_review" in compliance_result


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        pytest.skip(f"{name} is required for this manual integration test")
    return value


def _load_test_env() -> None:
    load_local_env()


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _compliance_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: fields.get(key)
        for key in (
            "document_type",
            "subject_name",
            "credit_code",
            "valid_from",
            "valid_to",
            "source_page",
        )
    }


def _compact_compliance_result(result: dict[str, Any]) -> dict[str, Any]:
    failed_rules = [
        _rule_result_snapshot(rule)
        for rule in result["rule_results"]
        if not rule["passed"]
    ]
    return {
        "compliant": not result["needs_manual_review"],
        "risk_level": result["risk_level"],
        "needs_manual_review": result["needs_manual_review"],
        "manual_review_reasons": result["manual_review"]["reasons"],
        "failed_rules": failed_rules,
    }


def _rule_result_snapshot(rule: Any) -> dict[str, Any]:
    return {
        "rule_code": rule["rule_code"],
        "rule_name": rule["rule_name"],
        "passed": rule["passed"],
        "risk_level_on_failure": rule["risk_level_on_failure"],
        "message": rule["message"],
        "details": rule["details"],
    }


def _debug_enabled() -> bool:
    return os.environ.get("DOCUMENT_AI_REVIEW_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _document_file_snapshot(file_input: Any) -> dict[str, Any]:
    payload = file_input.model_dump(mode="json")
    if payload.get("file_uri"):
        payload["file_uri"] = _truncate(payload["file_uri"], 180)
    return payload


def _truncate(value: str | None, limit: int) -> str | None:
    if value is None or len(value) <= limit:
        return value
    return f"{value[:limit]}..."
