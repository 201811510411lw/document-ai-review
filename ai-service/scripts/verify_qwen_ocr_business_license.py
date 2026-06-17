import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import load_local_env
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.srm.business_license_tasks import (
    DEFAULT_BUSINESS_LICENSE_SOURCE_SQL,
    fetch_one_business_license_source_task,
)
from app.models import ReviewDocumentInput, ReviewInput
from app.tools.license_file_recognition import recognize_license_file
from app.tools.remote_document import RemoteDocumentDownloader
from app.tools.vision_adapter import build_business_license_vision_adapter


def main() -> None:
    load_local_env()
    adapter = build_business_license_vision_adapter()
    downloader = RemoteDocumentDownloader()
    review_input = _review_input_from_env_or_srm()
    result = recognize_license_file(
        review_input,
        adapter=adapter,
        downloader=downloader,
        include_legacy_vision_metadata=True,
    )
    payload = {
        "document_input": result.document_input.__dict__,
        "expected": {
            "supplier_name": review_input.supplier_name,
            "supplier_credit_code": review_input.supplier_credit_code,
        },
        "extracted_fields": _key_fields(result.structured_fields),
        "metadata": _metadata_summary(result.extraction_metadata),
    }
    if _debug_enabled():
        payload["raw_text_preview"] = result.document_text[:1000]
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _review_input_from_env_or_srm() -> ReviewInput:
    local_file = os.environ.get("QWEN_OCR_LOCAL_FILE", "").strip()
    if local_file:
        path = Path(local_file).expanduser()
        return ReviewInput(
            supplier_name=os.environ.get("QWEN_OCR_EXPECTED_SUBJECT_NAME", ""),
            supplier_credit_code=os.environ.get("QWEN_OCR_EXPECTED_CREDIT_CODE", ""),
            declared_document_type="business_license",
            file=ReviewDocumentInput(
                local_path=str(path),
                file_name=path.name,
                mime_type=_mime_type(path),
            ),
            source={"source_system": "local"},
        )

    task = fetch_one_business_license_source_task(
        MySqlFetchClient(mysql_settings_from_env()),
        sql=_source_sql(),
    )
    if task is None:
        raise SystemExit("NO_SOURCE_TASK")
    return task.review_input


def _source_sql() -> str:
    custom_sql = os.environ.get("QWEN_OCR_SOURCE_SQL", "").strip()
    if custom_sql:
        return custom_sql
    vendor_name = os.environ.get("QWEN_OCR_VENDOR_NAME", "").strip()
    vendor_name_like = os.environ.get("QWEN_OCR_VENDOR_NAME_LIKE", "").strip()
    offset = int(os.environ.get("QWEN_OCR_SOURCE_OFFSET", "0"))
    if not vendor_name and not vendor_name_like and offset <= 0:
        return DEFAULT_BUSINESS_LICENSE_SOURCE_SQL
    base_sql = DEFAULT_BUSINESS_LICENSE_SOURCE_SQL.rsplit("limit", 1)[0].strip()
    if vendor_name:
        base_sql = f"{base_sql}\nand t1.vendorName = '{_sql_literal(vendor_name)}'"
    if vendor_name_like:
        base_sql = f"{base_sql}\nand t1.vendorName like '%{_sql_like_literal(vendor_name_like)}%'"
    return f"{base_sql}\nlimit 1 offset {offset}"


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _sql_like_literal(value: str) -> str:
    return _sql_literal(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _key_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {
        key: fields.get(key)
        for key in (
            "document_type",
            "subject_name",
            "credit_code",
            "business_address",
            "legal_person",
            "established_date",
            "valid_from",
            "valid_to",
            "issue_authority",
            "issue_date",
            "source_page",
            "ignored_pages",
            "subject_name_evidence",
            "credit_code_evidence",
            "valid_to_evidence",
        )
    }


def _metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    extractor = dict(metadata.get("llm_file_extractor") or {})
    summary = {
        "provider": extractor.get("provider"),
        "model": extractor.get("model"),
        "implementation_status": extractor.get("implementation_status"),
        "error_code": extractor.get("error_code"),
        "error_type": extractor.get("error_type"),
        "pages": extractor.get("pages"),
        "processed_pages": extractor.get("processed_pages"),
        "stopped_after_first_license": extractor.get("stopped_after_first_license"),
        "attempts": extractor.get("attempts"),
        "selected_page": extractor.get("selected_page"),
        "ignored_pages": extractor.get("ignored_pages"),
        "local_prefilter": extractor.get("local_prefilter"),
        "mismatched_fields": extractor.get("mismatched_fields"),
        "final_provider": extractor.get("final_provider"),
        "fallback_used": extractor.get("fallback_used"),
        "fallback_trigger": extractor.get("fallback_trigger"),
        "primary_validation": extractor.get("primary_validation"),
        "fallback_validation": extractor.get("fallback_validation"),
        "primary_summary": extractor.get("primary_summary"),
    }
    if _debug_enabled():
        summary["page_summaries"] = extractor.get("page_summaries")
        summary["llm_parse"] = extractor.get("llm_parse")
        summary["rule_fields"] = extractor.get("rule_fields")
        summary["ocr_page_summaries"] = extractor.get("ocr_page_summaries")
    return summary


def _mime_type(path: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }.get(path.suffix.lower(), "application/octet-stream")


def _debug_enabled() -> bool:
    return os.environ.get("DOCUMENT_AI_REVIEW_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


if __name__ == "__main__":
    main()
