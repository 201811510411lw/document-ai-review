import re
import unicodedata
from typing import Any

from app.tools.aliyun_ocr_adapter import AliyunCloudMarketOcrAdapter
from app.tools.qwen_ocr_adapter import QwenOcrBusinessLicenseAdapter


class QwenOcrWithAliyunFallbackBusinessLicenseAdapter:
    implementation_status = "configured"

    def __init__(
        self,
        *,
        primary_adapter: Any | None = None,
        fallback_adapter: Any | None = None,
    ) -> None:
        self.primary_adapter = primary_adapter or QwenOcrBusinessLicenseAdapter()
        self.fallback_adapter = fallback_adapter or AliyunCloudMarketOcrAdapter()

    def extract_text(self, source: Any) -> dict[str, Any]:
        primary_result = self.primary_adapter.extract_text(source)
        validation = validate_business_license_ocr_result(
            primary_result,
            expected_subject_name=_get_value(source, "expected_subject_name"),
            expected_credit_code=_get_value(source, "expected_credit_code"),
        )
        if validation["passed"]:
            return _with_fallback_metadata(
                primary_result,
                final_provider="qwen_ocr",
                primary_validation=validation,
                fallback_used=False,
            )

        fallback_result = self.fallback_adapter.extract_text(source)
        fallback_validation = validate_business_license_ocr_result(
            fallback_result,
            expected_subject_name=_get_value(source, "expected_subject_name"),
            expected_credit_code=_get_value(source, "expected_credit_code"),
        )
        if (
            fallback_validation["passed"]
            or _business_license_result_score(fallback_result)
            > _business_license_result_score(primary_result)
        ):
            return _with_fallback_metadata(
                fallback_result,
                final_provider=str(
                    (fallback_result.get("metadata") or {}).get(
                        "provider",
                        "aliyun_cloud_market_ocr",
                    )
                ),
                primary_validation=validation,
                fallback_validation=fallback_validation,
                fallback_used=True,
                fallback_trigger=validation["failure_reasons"][0],
                primary_result=primary_result,
            )

        # A failed fallback must not erase fields recognized by the primary OCR.
        return _with_fallback_metadata(
            primary_result,
            final_provider="qwen_ocr",
            primary_validation=validation,
            fallback_validation=fallback_validation,
            fallback_used=False,
            fallback_trigger=validation["failure_reasons"][0],
            fallback_attempted=True,
            fallback_discarded=True,
            fallback_error_code=(fallback_result.get("metadata") or {}).get("error_code"),
        )


def validate_business_license_ocr_result(
    result: dict[str, Any],
    *,
    expected_subject_name: str | None,
    expected_credit_code: str | None,
) -> dict[str, Any]:
    metadata = dict(result.get("metadata") or {})
    fields = dict(result.get("structured_fields") or {})
    failure_reasons: list[str] = []

    if metadata.get("error_code"):
        failure_reasons.append(str(metadata["error_code"]))

    document_type = str(fields.get("document_type") or "").strip().lower()
    if document_type not in {"business_license", "营业执照"}:
        failure_reasons.append("document_type_invalid")

    actual_credit = _normalize_credit_code(fields.get("credit_code"))
    expected_credit = _normalize_credit_code(expected_credit_code)
    if not actual_credit:
        failure_reasons.append("credit_code_missing")
    elif len(actual_credit) not in {15, 18}:
        failure_reasons.append("credit_code_format_invalid")
    elif expected_credit and actual_credit != expected_credit:
        failure_reasons.append("credit_code_mismatch")

    actual_subject = _normalize_subject_name(fields.get("subject_name"))
    expected_subject = _normalize_subject_name(expected_subject_name)
    if not actual_subject:
        failure_reasons.append("subject_name_missing")
    elif expected_subject and actual_subject != expected_subject:
        failure_reasons.append("subject_name_mismatch")

    if actual_subject and not _normalize_text(fields.get("subject_name_evidence")):
        failure_reasons.append("subject_name_evidence_missing")

    if actual_credit and not _normalize_text(fields.get("credit_code_evidence")):
        failure_reasons.append("credit_code_evidence_missing")

    if not _has_secondary_business_license_fields(fields):
        failure_reasons.append("secondary_fields_missing")

    return {
        "passed": not failure_reasons,
        "failure_reasons": failure_reasons,
    }


def _with_fallback_metadata(
    result: dict[str, Any],
    *,
    final_provider: str,
    primary_validation: dict[str, Any],
    fallback_used: bool,
    fallback_validation: dict[str, Any] | None = None,
    fallback_trigger: str | None = None,
    primary_result: dict[str, Any] | None = None,
    fallback_attempted: bool | None = None,
    fallback_discarded: bool = False,
    fallback_error_code: str | None = None,
) -> dict[str, Any]:
    metadata = dict(result.get("metadata") or {})
    metadata["provider"] = "qwen_ocr_with_aliyun_fallback"
    metadata["final_provider"] = final_provider
    metadata["primary_provider"] = "qwen_ocr"
    metadata["fallback_provider"] = "aliyun_cloud_market_ocr"
    metadata["fallback_used"] = fallback_used
    metadata["fallback_attempted"] = (
        fallback_used if fallback_attempted is None else fallback_attempted
    )
    metadata["fallback_discarded"] = fallback_discarded
    if fallback_error_code:
        metadata["fallback_error_code"] = fallback_error_code
    metadata["primary_validation"] = primary_validation
    if fallback_validation is not None:
        metadata["fallback_validation"] = fallback_validation
    if fallback_trigger:
        metadata["fallback_trigger"] = fallback_trigger
    if primary_result is not None:
        primary_metadata = dict(primary_result.get("metadata") or {})
        metadata["primary_summary"] = {
            "error_code": primary_metadata.get("error_code"),
            "structured_extraction": primary_metadata.get("structured_extraction"),
            "selected_page": primary_metadata.get("selected_page"),
            "mismatched_fields": primary_metadata.get("mismatched_fields"),
        }
    return {**result, "metadata": metadata}


def _normalize_subject_name(value: Any) -> str:
    text = _normalize_text(value)
    punctuation = set("()（）[]【】,，.。;；:：-—_·'\"“”‘’")
    return "".join(character for character in text if character not in punctuation)


def _normalize_credit_code(value: Any) -> str:
    text = _normalize_text(value).upper()
    return "".join(re.findall(r"[0-9A-Z]", text))


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return "".join(normalized.split()).strip()


def _has_secondary_business_license_fields(fields: dict[str, Any]) -> bool:
    return bool(
        fields.get("legal_person")
        or fields.get("business_address")
        or fields.get("valid_to")
        or fields.get("valid_from")
        or fields.get("established_date")
        or fields.get("issue_authority")
        or fields.get("issue_date")
    )


def _business_license_result_score(result: dict[str, Any]) -> int:
    metadata = dict(result.get("metadata") or {})
    if metadata.get("error_code"):
        return -100
    fields = dict(result.get("structured_fields") or {})
    score = 0
    if str(fields.get("document_type") or "").strip().lower() in {
        "business_license",
        "营业执照",
    }:
        score += 2
    for field in ("subject_name", "credit_code"):
        if _normalize_text(fields.get(field)):
            score += 2
    for field in ("business_address", "legal_person", "valid_from", "valid_to"):
        if _normalize_text(fields.get(field)):
            score += 1
    for field in ("subject_name_evidence", "credit_code_evidence"):
        if _normalize_text(fields.get(field)):
            score += 1
    return score


def _get_value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
