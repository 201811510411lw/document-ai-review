from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class UnsupportedSrmDocumentTypeError(ValueError):
    def __init__(self, type_name: Any):
        self.type_name = type_name
        super().__init__(f"unsupported SRM document typeName: {type_name!r}")


class DocumentRecord(BaseModel):
    source_system: str = "srm"
    tenant: str | None = None
    record_id: str | None = None
    attachment_ref_id: str | None = None
    document_category: str | None = None
    declared_document_type: str
    document_type_code: str | None = None
    business_number: str | None = None
    business_num: str | None = None
    vendor_id: str | None = None
    vendor_name: str | None = None
    source_expired_begin: str | None = None
    source_expired_end: str | None = None
    file_name: str | None = None
    file_store_key: str | None = None
    file_url: str | None = None
    business_deleted: bool = False
    attachment_deleted: bool = False
    source_payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_deleted(self) -> bool:
        return self.business_deleted or self.attachment_deleted


DOCUMENT_TYPE_BY_SRM_TYPE_NAME = {
    "营业执照": "business_license",
    "食品经营许可证": "food_license",
    "食品生产许可证": "food_production_license",
    "产品报告": "product_report",
}


def map_srm_certification_row(row: dict[str, Any]) -> DocumentRecord:
    declared_document_type = _map_document_type(row.get("typeName"))
    return DocumentRecord(
        tenant=_first_present(row, "tenant", "t1.tenant", "t2.tenant"),
        record_id=_first_present(row, "uuid", "t1.uuid"),
        attachment_ref_id=_first_present(row, "refId", "refid", "t2.refId", "t2.refid"),
        document_category=_first_present(row, "category", "t1.category"),
        declared_document_type=declared_document_type,
        document_type_code=_first_present(row, "typeCode", "t1.typeCode"),
        business_number=_first_present(row, "number", "t1.number"),
        business_num=_first_present(row, "num", "t1.num"),
        vendor_id=_first_present(row, "vendorId", "t1.vendorId"),
        vendor_name=_first_present(row, "vendorName", "t1.vendorName"),
        source_expired_begin=_to_source_string(
            _first_present(row, "expiredBegin", "t1.expiredBegin")
        ),
        source_expired_end=_to_source_string(
            _first_present(row, "expiredEnd", "t1.expiredEnd")
        ),
        file_name=_first_present(
            row,
            "attachmentName",
            "attachmentname",
            "t2.attachmentName",
            "t2.attachmentname",
        ),
        file_store_key=_first_present(row, "storeId", "storeid", "t2.storeId", "t2.storeid"),
        file_url=_first_present(row, "url", "t2.url"),
        business_deleted=_to_bool(_first_present(row, "deleted", "t1.deleted")),
        attachment_deleted=_to_bool(_first_present(row, "removed", "t2.removed")),
        source_payload=dict(row),
    )


def _map_document_type(type_name: Any) -> str:
    document_type = DOCUMENT_TYPE_BY_SRM_TYPE_NAME.get(type_name)
    if document_type is None:
        raise UnsupportedSrmDocumentTypeError(type_name)
    return document_type


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
    return bool(value)


def _to_source_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
