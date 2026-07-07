from typing import Any, Protocol

from pydantic import BaseModel

from app.integrations.srm.document_records import (
    DocumentRecord,
    map_srm_certification_row,
)
from app.models import ReviewDocumentInput, ReviewInput


class SqlFetchClient(Protocol):
    def fetch_all(self, sql: str) -> list[dict[str, Any]]:
        ...


class ProductReportSourceTaskError(ValueError):
    def __init__(self, code: str, message: str, *, record_id: str | None = None):
        self.code = code
        self.record_id = record_id
        super().__init__(message)


class ProductReportSourceTask(BaseModel):
    record: DocumentRecord
    review_input: ReviewInput


DEFAULT_PRODUCT_REPORT_SOURCE_SQL = """
select
	t1.uuid,
	t1.tenant,
	t1.category,
	t1.typeName,
	t1.typeCode,
	t1.vendorId,
	t1.vendorName,
	t1.num,
	t1.number,
	t1.state,
	t1.deleted,
	t2.removed,
	t2.uuid as attachment_uuid,
	t2.refId as refId,
	t2.attachmentName,
	t2.storeId,
	t2.url,
	t1.created,
	t1.lastModified,
	t1.expiredBegin,
	t1.expiredEnd
from
	srm.certification t1
left join srm.attachment t2 on
	t1.uuid = t2.refId
where
	t2.tenant = '8560'
	and t1.category = 'sku'
	and t1.typeName = '产品报告'
	and t1.deleted = 0
	and t2.removed = 0
	and t2.url is not null
	and t2.url <> ''
order by rand()
limit 1
""".strip()


def fetch_one_product_report_source_task(
    sql_client: SqlFetchClient,
    sql: str = DEFAULT_PRODUCT_REPORT_SOURCE_SQL,
) -> ProductReportSourceTask | None:
    tasks = fetch_product_report_source_tasks(sql_client, sql)
    return tasks[0] if tasks else None


def fetch_product_report_source_tasks(
    sql_client: SqlFetchClient,
    sql: str,
) -> list[ProductReportSourceTask]:
    rows = sql_client.fetch_all(sql)
    tasks: list[ProductReportSourceTask] = []
    seen_keys: set[tuple[str | None, str | None]] = set()

    for row in rows:
        record = map_srm_certification_row(row)
        if record.declared_document_type != "product_report":
            continue
        if record.document_category not in ("sku", "vendor", "manufacturer"):
            continue
        if record.is_deleted:
            continue
        if not record.file_url:
            raise ProductReportSourceTaskError(
                "PRODUCT_REPORT_SOURCE_URL_MISSING",
                "产品报告来源记录缺少文件 URL",
                record_id=record.record_id,
            )

        attachment_uuid = _optional_string(row.get("attachment_uuid"))
        dedupe_key = (record.record_id, attachment_uuid or record.attachment_ref_id)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        tasks.append(
            ProductReportSourceTask(
                record=record,
                review_input=_to_review_input(record, attachment_uuid=attachment_uuid),
            )
        )

    return tasks


def _to_review_input(
    record: DocumentRecord,
    *,
    attachment_uuid: str | None,
) -> ReviewInput:
    return ReviewInput(
        supplier_name=record.vendor_name or "",
        supplier_credit_code="",
        declared_document_type="product_report",
        file=ReviewDocumentInput(
            file_uri=record.file_url,
            file_name=record.file_name,
        ),
        source={
            "source_system": record.source_system,
            "tenant": record.tenant,
            "record_id": record.record_id,
            "attachment_uuid": attachment_uuid,
            "attachment_ref_id": record.attachment_ref_id,
            "document_category": record.document_category,
            "document_type_code": record.document_type_code,
            "vendor_id": record.vendor_id,
            "sku_number": record.business_num,
            "business_number": record.business_number,
            "file_store_key": record.file_store_key,
            "source_payload": record.source_payload,
        },
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
