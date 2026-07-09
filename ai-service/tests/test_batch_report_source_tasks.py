from datetime import date

import pytest

from app.integrations.starrocks.batch_report_tasks import (
    build_batch_report_source_sql,
    fetch_batch_report_source_tasks,
    fetch_one_batch_report_source_task,
    BatchReportSourceTaskError,
)


class StubSqlClient:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        return self.rows


def test_build_batch_report_source_sql_uses_review_date_window():
    sql = build_batch_report_source_sql(date(2026, 5, 5))

    assert "t1.created >= '2026-05-05 00:00:00'" in sql
    assert "t1.created < '2026-05-06 00:00:00'" in sql
    assert "t3.refType = 'orderDeliveryBatch'" in sql
    assert "(t3.removed = 0 or t3.removed is null)" in sql
    assert "order by rand()" in sql.lower()


def test_fetch_batch_report_source_tasks_maps_starrocks_row_to_review_input():
    client = StubSqlClient(
        [
            {
                "order_uuid": "order-001",
                "order_number": "10102605050385",
                "order_tenant": "8560",
                "order_state": "finish",
                "order_type": "自营进",
                "order_biz_type": "0",
                "order_created": "2026-05-05 16:43:01",
                "vendor_id": "VENDOR-001",
                "vendor_name": "广州市秀雅秀贸易有限公司（常温）",
                "batch_uuid": "batch-001",
                "orderline_uuid": "line-001",
                "sku_code": "10080788",
                "barcode": "6959011900929",
                "sku_name": "游世佳族金唱片面包",
                "production_time": "2026-05-08 00:00:00",
                "expired_time": "2026-08-06 00:00:00",
                "attachment_uuid": "attach-001",
                "attachment_ref_id": "batch-001",
                "attachment_ref_type": "orderDeliveryBatch",
                "attachment_name": "金唱片面包20260508.pdf",
                "attachment_store_id": "oss-key",
                "attachment_url": "https://files.example.test/batch-report.pdf",
            }
        ]
    )

    tasks = fetch_batch_report_source_tasks(client, "select 1")

    assert len(tasks) == 1
    review_input = tasks[0].review_input
    assert review_input.declared_document_type == "batch_report"
    assert review_input.supplier_name == "广州市秀雅秀贸易有限公司（常温）"
    assert review_input.file.file_uri == "https://files.example.test/batch-report.pdf"
    assert review_input.file.file_name == "金唱片面包20260508.pdf"
    assert review_input.source["record_id"] == "batch-001"
    assert review_input.source["order_number"] == "10102605050385"
    assert review_input.source["sku_name"] == "游世佳族金唱片面包"
    assert review_input.source["production_date"] == "2026-05-08"
    assert review_input.source["attachment_uuid"] == "attach-001"


def test_fetch_one_batch_report_source_task_uses_default_review_date():
    client = StubSqlClient([])

    task = fetch_one_batch_report_source_task(client)

    assert task is None
    assert "2026-05-05 00:00:00" in client.executed_sql[0]


def test_fetch_batch_report_source_tasks_rejects_missing_url():
    client = StubSqlClient([{"batch_uuid": "batch-001"}])

    with pytest.raises(BatchReportSourceTaskError) as error:
        fetch_batch_report_source_tasks(client, "select 1")

    assert error.value.code == "BATCH_REPORT_SOURCE_URL_MISSING"
    assert error.value.record_id == "batch-001"
