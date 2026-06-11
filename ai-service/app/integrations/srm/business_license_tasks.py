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


class BusinessLicenseSourceTaskError(ValueError):
    def __init__(self, code: str, message: str, *, record_id: str | None = None):
        self.code = code
        self.record_id = record_id
        super().__init__(message)


class BusinessLicenseSourceTask(BaseModel):
    record: DocumentRecord
    review_input: ReviewInput


DEFAULT_BUSINESS_LICENSE_SOURCE_SQL = """
select * from ods.ods_hd_srm_certification_di t1
                  left join  ods.ods_hd_srm_attachment_di t2 on t1.uuid=t2.refId
where t1.category='vendor'
  and t2.tenant='8560'  and t2.refType ='certification'
  and removed =false limit 1;
""".strip()


def fetch_one_business_license_source_task(
    sql_client: SqlFetchClient,
    sql: str = DEFAULT_BUSINESS_LICENSE_SOURCE_SQL,
) -> BusinessLicenseSourceTask | None:
    tasks = fetch_business_license_source_tasks(sql_client, sql)
    return tasks[0] if tasks else None


def fetch_business_license_source_tasks(
    sql_client: SqlFetchClient,
    sql: str,
) -> list[BusinessLicenseSourceTask]:
    rows = sql_client.fetch_all(sql)
    tasks: list[BusinessLicenseSourceTask] = []
    seen_keys: set[tuple[str | None, str | None]] = set()

    for row in rows:
        record = map_srm_certification_row(row)
        if record.declared_document_type != "business_license":
            continue
        if not record.file_url:
            raise BusinessLicenseSourceTaskError(
                "BUSINESS_LICENSE_SOURCE_URL_MISSING",
                "营业执照来源记录缺少文件 URL",
                record_id=record.record_id,
            )

        dedupe_key = (record.record_id, record.attachment_ref_id)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        tasks.append(BusinessLicenseSourceTask(record=record, review_input=_to_review_input(record)))

    return tasks


def _to_review_input(record: DocumentRecord) -> ReviewInput:
    return ReviewInput(
        supplier_name=record.vendor_name or "",
        supplier_credit_code=record.business_number or "",
        declared_document_type="business_license",
        file=ReviewDocumentInput(
            file_uri=record.file_url,
            file_name=record.file_name,
        ),
        source={
            "source_system": record.source_system,
            "tenant": record.tenant,
            "record_id": record.record_id,
            "attachment_ref_id": record.attachment_ref_id,
            "document_category": record.document_category,
            "document_type_code": record.document_type_code,
            "file_store_key": record.file_store_key,
            "source_payload": record.source_payload,
        },
    )
