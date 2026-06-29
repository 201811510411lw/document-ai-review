from dataclasses import dataclass

from app.integrations.srm.document_records import DocumentRecord


DOCUMENT_TYPE_LABELS = {
    "business_license": "营业执照",
    "food_license": "食品经营许可证",
    "food_production_license": "食品生产许可证",
}

DOCUMENT_TYPE_HINTS = (
    ("食品生产许可证", "food_production_license"),
    ("食品生产许可品种明细表", "food_production_license"),
    ("食品生产许可", "food_production_license"),
    ("品种明细表", "food_production_license"),
    ("食品经营许可证", "food_license"),
    ("食品经营许可", "food_license"),
    ("营业执照", "business_license"),
)


@dataclass(frozen=True)
class DocumentTypeEvidence:
    declared_document_type: str
    resolved_document_type: str
    hints: tuple[str, ...]
    conflict: bool

    def as_source_dict(self) -> dict[str, object]:
        return {
            "declared_document_type": self.declared_document_type,
            "resolved_document_type": self.resolved_document_type,
            "hints": list(self.hints),
            "conflict": self.conflict,
        }


def resolve_srm_document_type(record: DocumentRecord) -> DocumentTypeEvidence:
    hinted_type, hints = _hinted_document_type(record)
    resolved = hinted_type or record.declared_document_type
    return DocumentTypeEvidence(
        declared_document_type=record.declared_document_type,
        resolved_document_type=resolved,
        hints=tuple(hints),
        conflict=resolved != record.declared_document_type,
    )


def _hinted_document_type(record: DocumentRecord) -> tuple[str | None, list[str]]:
    evidence_fields = {
        "remark": record.remark,
        "attachmentName": record.file_name,
        "storeId": record.file_store_key,
        "url": record.file_url,
        "num": record.business_num,
        "number": record.business_number,
    }
    hints: list[str] = []
    scores: dict[str, int] = {}
    for field_name, raw_value in evidence_fields.items():
        value = str(raw_value or "")
        if not value:
            continue
        for marker, document_type in DOCUMENT_TYPE_HINTS:
            if marker in value:
                scores[document_type] = scores.get(document_type, 0) + 2
                hints.append(f"{field_name}:{marker}")
                break
        compact = "".join(value.split()).upper()
        if compact.startswith("SC"):
            scores["food_production_license"] = scores.get("food_production_license", 0) + 1
            hints.append(f"{field_name}:SC")
        elif compact.startswith("JY"):
            scores["food_license"] = scores.get("food_license", 0) + 1
            hints.append(f"{field_name}:JY")
    if not scores:
        return None, hints
    return max(scores.items(), key=lambda item: item[1])[0], hints
