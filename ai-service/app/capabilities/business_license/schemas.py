import re
import unicodedata

from pydantic import BaseModel, Field


class BusinessLicenseDocumentClassification(BaseModel):
    document_type: str
    confidence: float | None = None
    reasons: list[str] = Field(default_factory=list)


class BusinessLicenseExtractedFields(BaseModel):
    document_type: str | None = None
    subject_name: str | None = None
    credit_code: str | None = None
    business_address: str | None = None
    legal_person: str | None = None
    established_date: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    issue_authority: str | None = None
    issue_date: str | None = None
    source_page: int | None = None
    ignored_pages: list[dict] = Field(default_factory=list)
    subject_name_evidence: str | None = None
    credit_code_evidence: str | None = None
    valid_to_evidence: str | None = None


class BusinessLicenseNormalizedFields(BusinessLicenseExtractedFields):
    pass


class BusinessLicenseDocumentInputResult(BaseModel):
    input_type: str
    file_name: str | None = None
    mime_type: str | None = None
    document_format: str | None = None
    source_url: str | None = None


class BusinessLicenseCapabilityResult(BaseModel):
    document_input: BusinessLicenseDocumentInputResult | None = None
    document_classification: BusinessLicenseDocumentClassification | None = None
    extracted_fields: BusinessLicenseExtractedFields | None = None
    normalized_fields: BusinessLicenseNormalizedFields | None = None
    extraction_metadata: dict = Field(default_factory=dict)
    source_evidence: dict = Field(default_factory=dict)


def normalize_business_license_fields(
    extracted: BusinessLicenseExtractedFields | None,
) -> BusinessLicenseNormalizedFields:
    if extracted is None:
        return BusinessLicenseNormalizedFields()
    payload = extracted.model_dump()
    return BusinessLicenseNormalizedFields.model_validate(
        {
            **payload,
            "document_type": _normalize_document_type(payload.get("document_type")),
            "subject_name": _normalize_subject_name(payload.get("subject_name")),
            "credit_code": _normalize_credit_code(payload.get("credit_code")),
            "valid_to": _normalize_valid_to(payload.get("valid_to")),
        }
    )


def normalize_business_license_source_fields(source_fields: dict) -> dict:
    return {
        **source_fields,
        "supplier_name": _normalize_subject_name(source_fields.get("supplier_name")),
        "supplier_credit_code": _normalize_credit_code(
            source_fields.get("supplier_credit_code")
        ),
    }


def _normalize_document_type(value: str | None) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    lower = text.lower()
    if lower in {"business_license", "营业执照"}:
        return "business_license"
    return lower


def _normalize_subject_name(value: str | None) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return _strip_common_punctuation(text)


def _normalize_credit_code(value: str | None) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return re.sub(r"\s+", "", text).upper()


def _normalize_valid_to(value: str | None) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    if text in {"长期", "永久", "无固定期限", "长期有效"}:
        return "长期"
    return text


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    normalized = unicodedata.normalize("NFKC", str(value))
    return "".join(normalized.split()).strip()


def _strip_common_punctuation(value: str) -> str:
    punctuation = set("()（）[]【】,，.。;；:：-—_·'\"“”‘’")
    return "".join(character for character in value if character not in punctuation)
