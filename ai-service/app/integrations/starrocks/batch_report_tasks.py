from datetime import date, datetime, timedelta
from typing import Any, Protocol

from pydantic import BaseModel

from app.models import ReviewDocumentInput, ReviewInput


class SqlFetchClient(Protocol):
    def fetch_all(self, sql: str) -> list[dict[str, Any]]:
        ...


DEFAULT_BATCH_REPORT_REVIEW_DATE = date(2026, 5, 5)


class BatchReportSourceTaskError(ValueError):
    def __init__(self, code: str, message: str, *, record_id: str | None = None):
        self.code = code
        self.record_id = record_id
        super().__init__(message)


class BatchReportSourceTask(BaseModel):
    row: dict[str, Any]
    review_input: ReviewInput


def _batch_report_columns() -> str:
    return """
    t1.uuid as order_uuid,
    t1.number as order_number,
    t1.tenant as order_tenant,
    t1.state as order_state,
    t1.type as order_type,
    t1.bizType as order_biz_type,
    t1.created as order_created,
    t1.confirmDate as order_confirm_date,
    t1.arrivalDate as order_arrival_date,
    t1.vendorId as vendor_id,
    t1.vendorName as vendor_name,
    t2.uuid as batch_uuid,
    t2.orderLineUuid as orderline_uuid,
    t2.skuCode as sku_code,
    t2.barcode as barcode,
    t2.skuName as sku_name,
    t2.productionTime as production_time,
    t2.expiredTime as expired_time,
    t3.uuid as attachment_uuid,
    t3.refId as attachment_ref_id,
    t3.refType as attachment_ref_type,
    t3.attachmentName as attachment_name,
    t3.storeId as attachment_store_id,
    t3.url as attachment_url
""".strip()


def _batch_report_from_clause() -> str:
    return """
from srm_orders t1
join srm_orderdeliverybatch t2 on t1.uuid = t2.orderId
join srm_attachment t3 on t2.uuid = t3.refId
""".strip()


def _batch_report_where_clause() -> str:
    return """
where t1.tenant = '8560'
  and t1.state = 'finish'
  and t3.refType = 'orderDeliveryBatch'
  and (t3.removed = 0 or t3.removed is null)
  and t3.url is not null
  and t3.url <> ''
""".strip()


def build_batch_report_source_sql(
    review_date: date = DEFAULT_BATCH_REPORT_REVIEW_DATE,
) -> str:
    start = review_date.isoformat()
    end = (review_date + timedelta(days=1)).isoformat()
    return f"""select {_batch_report_columns()}
{_batch_report_from_clause()}
{_batch_report_where_clause()}
  and t1.created >= '{start} 00:00:00'
  and t1.created < '{end} 00:00:00'
order by rand()
limit 1
""".strip()


def build_batch_report_sync_sql(since_iso: str) -> str:
    """构建每日同步用的批次报告查询 SQL（批量，不含 rand() limit 1）"""
    return f"""select {_batch_report_columns()}
{_batch_report_from_clause()}
{_batch_report_where_clause()}
  and t1.created >= '{since_iso}'
order by t1.created
""".strip()


def fetch_one_batch_report_source_task(
    sql_client: SqlFetchClient,
    *,
    review_date: date = DEFAULT_BATCH_REPORT_REVIEW_DATE,
    sql: str | None = None,
) -> BatchReportSourceTask | None:
    tasks = fetch_batch_report_source_tasks(
        sql_client,
        sql or build_batch_report_source_sql(review_date),
    )
    return tasks[0] if tasks else None


def fetch_batch_report_source_tasks(
    sql_client: SqlFetchClient,
    sql: str,
) -> list[BatchReportSourceTask]:
    rows = sql_client.fetch_all(sql)
    tasks: list[BatchReportSourceTask] = []
    seen_keys: set[tuple[str | None, str | None]] = set()

    for row in rows:
        batch_uuid = _optional_string(row.get("batch_uuid"))
        attachment_uuid = _optional_string(row.get("attachment_uuid"))
        if not _optional_string(row.get("attachment_url")):
            raise BatchReportSourceTaskError(
                "BATCH_REPORT_SOURCE_URL_MISSING",
                "商品批次报告来源记录缺少文件 URL",
                record_id=batch_uuid,
            )
        dedupe_key = (batch_uuid, attachment_uuid)
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        tasks.append(
            BatchReportSourceTask(
                row=dict(row),
                review_input=_to_review_input(row),
            )
        )

    return tasks


def _to_review_input(row: dict[str, Any]) -> ReviewInput:
    production_date = _date_text(row.get("production_time"))
    return ReviewInput(
        supplier_name=_optional_string(row.get("vendor_name")) or "",
        supplier_credit_code="",
        declared_document_type="batch_report",
        file=ReviewDocumentInput(
            file_uri=_optional_string(row.get("attachment_url")),
            file_name=_optional_string(row.get("attachment_name")),
        ),
        source={
            "source_system": "starrocks",
            "source_origin": "srm",
            "tenant": _optional_string(row.get("order_tenant")),
            "record_id": _optional_string(row.get("batch_uuid")),
            "order_uuid": _optional_string(row.get("order_uuid")),
            "order_number": _optional_string(row.get("order_number")),
            "order_state": _optional_string(row.get("order_state")),
            "order_type": _optional_string(row.get("order_type")),
            "order_biz_type": _optional_string(row.get("order_biz_type")),
            "order_created": _text_or_none(row.get("order_created")),
            "vendor_id": _optional_string(row.get("vendor_id")),
            "vendor_name": _optional_string(row.get("vendor_name")),
            "batch_uuid": _optional_string(row.get("batch_uuid")),
            "orderline_uuid": _optional_string(row.get("orderline_uuid")),
            "sku_code": _optional_string(row.get("sku_code")),
            "barcode": _optional_string(row.get("barcode")),
            "sku_name": _optional_string(row.get("sku_name")),
            "production_date": production_date,
            "production_time": _text_or_none(row.get("production_time")),
            "expired_time": _text_or_none(row.get("expired_time")),
            "attachment_uuid": _optional_string(row.get("attachment_uuid")),
            "attachment_ref_id": _optional_string(row.get("attachment_ref_id")),
            "attachment_ref_type": _optional_string(row.get("attachment_ref_type")),
            "attachment_name": _optional_string(row.get("attachment_name")),
            "attachment_store_id": _optional_string(row.get("attachment_store_id")),
            "source_payload": {key: _text_or_none(value) for key, value in row.items()},
        },
    )


def _date_text(value: Any) -> str | None:
    text = _text_or_none(value)
    return text[:10] if text else None


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_string(value: Any) -> str | None:
    return _text_or_none(value)
