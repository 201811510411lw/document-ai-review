from pathlib import Path
import re
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
select
	t1.*,
	t2.refId as attachmentRefId,
	t2.refType,
	t2.attachmentName,
	t2.storeId,
	t2.removed,
	t2.url
from
	srm.certification t1
left join srm.attachment t2 on
	t1.uuid = t2.refId
where
	t1.category = 'vendor'
	and t2.tenant = '8560'
	and t2.refType = 'certification'
	and t2.url is not null
	and t2.url <> ''
	and typeName  = '营业执照'
	order by rand()
	limit 1
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
        supplier_name=_business_license_subject_name(record),
        supplier_credit_code=record.business_num or record.business_number or "",
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


def _business_license_subject_name(record: DocumentRecord) -> str:
    return (
        _subject_name_from_remark(record.remark)
        or _subject_name_from_file_name(record.file_name)
        or record.vendor_name
        or ""
    )


def _subject_name_from_remark(remark: str | None) -> str | None:
    text = (remark or "").strip()
    if not text:
        return None
    match = re.search(r"(?:生产商|经销商)\s*\d*\s*(?P<name>[^,，;；]+)", text)
    if not match:
        return None
    return _clean_subject_name(match.group("name"))


def _subject_name_from_file_name(file_name: str | None) -> str | None:
    stem = Path((file_name or "").strip()).stem
    if not stem:
        return None
    for marker in ("营业执照副本", "营业执照", "执照副本", "执照"):
        stem = stem.replace(marker, "")
    return _clean_subject_name(stem)


def _clean_subject_name(value: str | None) -> str | None:
    text = (value or "").strip(" -_()（）[]【】")
    if not re.search(r"[\u4e00-\u9fff]", text):
        return None
    if not re.search(r"(公司|厂|店|社|部|中心|商行|个体工商户)$", text):
        return None
    return text or None
