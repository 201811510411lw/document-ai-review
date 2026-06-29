from typing import Any, Protocol

from pydantic import BaseModel

from app.integrations.srm.document_records import (
    DocumentRecord,
    map_srm_certification_row,
)
from app.integrations.srm.document_type_evidence import resolve_srm_document_type
from app.models import ReviewDocumentInput, ReviewInput


class SqlFetchClient(Protocol):
    def fetch_all(self, sql: str) -> list[dict[str, Any]]:
        ...


class FoodProductionLicenseSourceTaskError(ValueError):
    def __init__(self, code: str, message: str, *, record_id: str | None = None):
        self.code = code
        self.record_id = record_id
        super().__init__(message)


class FoodProductionLicenseSourceTask(BaseModel):
    record: DocumentRecord
    review_input: ReviewInput


DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL = """
select
	*
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
	and t1.typeName = '食品生产许可证'
	order by rand()
	limit 1
""".strip()


def fetch_one_food_production_license_source_task(
    sql_client: SqlFetchClient,
    sql: str = DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL,
) -> FoodProductionLicenseSourceTask | None:
    tasks = fetch_food_production_license_source_tasks(sql_client, sql)
    return tasks[0] if tasks else None


def fetch_food_production_license_source_tasks(
    sql_client: SqlFetchClient,
    sql: str,
) -> list[FoodProductionLicenseSourceTask]:
    rows = sql_client.fetch_all(sql)
    tasks: list[FoodProductionLicenseSourceTask] = []
    seen_keys: set[tuple[str | None, str | None]] = set()

    for row in rows:
        record = map_srm_certification_row(row)
        if record.declared_document_type != "food_production_license":
            continue
        if not record.file_url:
            raise FoodProductionLicenseSourceTaskError(
                "FOOD_PRODUCTION_LICENSE_SOURCE_URL_MISSING",
                "食品生产许可证来源记录缺少文件 URL",
                record_id=record.record_id,
            )

        dedupe_key = (record.record_id, record.attachment_ref_id)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        tasks.append(
            FoodProductionLicenseSourceTask(
                record=record,
                review_input=_to_review_input(record),
            )
        )

    return tasks


def _to_review_input(record: DocumentRecord) -> ReviewInput:
    document_type_evidence = resolve_srm_document_type(record)
    return ReviewInput(
        supplier_name=record.vendor_name or "",
        supplier_credit_code=_credit_code_or_empty(record.business_num),
        declared_document_type=document_type_evidence.resolved_document_type,
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
            "document_type_evidence": document_type_evidence.as_source_dict(),
            "source_payload": record.source_payload,
        },
    )


def _credit_code_or_empty(value: str | None) -> str:
    text = "" if value is None else "".join(str(value).split()).upper()
    return text if len(text) in {15, 18} else ""
