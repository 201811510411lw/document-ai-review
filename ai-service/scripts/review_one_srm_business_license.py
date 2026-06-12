import json
import os
from typing import Any

from app.core.config import load_local_env
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.srm.business_license_entrypoint import (
    review_one_srm_business_license,
)
from app.services.review_service import ReviewService


def main() -> None:
    load_local_env()
    result = review_one_srm_business_license(
        sql_client=MySqlFetchClient(mysql_settings_from_env()),
        review_service=ReviewService(),
    )
    if result is None:
        print(json.dumps({"status": "NO_SOURCE_TASK"}, ensure_ascii=False))
        return
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json")
    else:
        payload = result
    output = payload if _debug_enabled() else _summary_payload(payload)
    print(json.dumps(output, ensure_ascii=False, indent=2))


def _debug_enabled() -> bool:
    return os.environ.get("DOCUMENT_AI_REVIEW_DEBUG", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


def _summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    skill_result = dict(payload.get("skill_result") or {})
    extracted_fields = dict(skill_result.get("extracted_fields") or {})
    document_input = dict(skill_result.get("document_input") or {})
    review_metadata = dict(
        (dict(skill_result.get("source_evidence") or {})).get(
            "skill_rule_review_metadata"
        )
        or {}
    )
    failed_rules = [
        {
            "rule_code": item.get("rule_code"),
            "rule_name": item.get("rule_name"),
            "message": item.get("message"),
            "details": item.get("details", {}),
        }
        for item in payload.get("rule_results", [])
        if not item.get("passed")
    ]
    return {
        "task_id": payload.get("task_id"),
        "document_type": payload.get("document_type"),
        "status": review_metadata.get("status_label")
        or _status_label(payload.get("status")),
        "risk_level": review_metadata.get("risk_level_label")
        or _risk_level_label(payload.get("risk_level")),
        "needs_manual_review": payload.get("needs_manual_review"),
        "summary": payload.get("summary"),
        "manual_review_reasons": (
            dict(payload.get("manual_review") or {}).get("reasons") or []
        ),
        "failed_rules": failed_rules,
        "extracted_fields": {
            "subject_name": extracted_fields.get("subject_name"),
            "credit_code": extracted_fields.get("credit_code"),
            "valid_from": extracted_fields.get("valid_from"),
            "valid_to": extracted_fields.get("valid_to"),
            "valid_to_evidence": extracted_fields.get("valid_to_evidence"),
        },
        "document_input": {
            "file_name": document_input.get("file_name"),
            "source_url": document_input.get("source_url"),
        },
    }


def _status_label(status: Any) -> str | None:
    labels = {
        "CREATED": "已创建",
        "RUNNING": "审核中",
        "REVIEWED": "已审核",
        "PENDING_MANUAL_REVIEW": "待人工复核",
        "MANUAL_REVIEWED": "人工已复核",
        "FAILED": "审核失败",
        "NO_SOURCE_TASK": "无待审核任务",
    }
    return labels.get(str(status), status) if status is not None else None


def _risk_level_label(risk_level: Any) -> str | None:
    labels = {
        "HIGH": "高风险",
        "MEDIUM": "中风险",
        "LOW": "低风险",
        "NONE": "无风险",
    }
    return labels.get(str(risk_level), risk_level) if risk_level is not None else None


if __name__ == "__main__":
    main()
