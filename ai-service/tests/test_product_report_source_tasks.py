from app.integrations.srm.product_report_tasks import (
    DEFAULT_PRODUCT_REPORT_SOURCE_SQL,
    ProductReportSourceTaskError,
    fetch_one_product_report_source_task,
    fetch_product_report_source_tasks,
)


class StubSqlClient:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        return self.rows


def test_fetch_product_report_source_tasks_maps_sku_rows_to_review_inputs():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-product-report-001",
                "refId": "cert-product-report-001",
                "tenant": "8560",
                "category": "sku",
                "typeName": "产品报告",
                "vendorId": "VENDOR-001",
                "vendorName": "广东乃一口食品有限公司",
                "number": "797120694064660482",
                "num": "1001010562202606290001",
                "attachment_uuid": "attach-product-report-001",
                "url": "https://files.example.test/product-report.pdf",
                "attachmentName": "鲜切蛋糕(蓝莓风味)_广东乃一口食品有限公司_TS10970001.pdf",
                "storeId": "oss-key-product-report",
                "deleted": 0,
                "removed": 0,
            }
        ]
    )

    tasks = fetch_product_report_source_tasks(client, "select * from certification")

    assert client.executed_sql == ["select * from certification"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task.record.record_id == "cert-product-report-001"
    assert task.record.document_category == "sku"
    assert task.review_input.declared_document_type == "product_report"
    assert task.review_input.supplier_name == "广东乃一口食品有限公司"
    assert task.review_input.supplier_credit_code == ""
    assert task.review_input.file.file_uri == "https://files.example.test/product-report.pdf"
    assert task.review_input.file.file_name == (
        "鲜切蛋糕(蓝莓风味)_广东乃一口食品有限公司_TS10970001.pdf"
    )
    assert task.review_input.source["source_system"] == "srm"
    assert task.review_input.source["tenant"] == "8560"
    assert task.review_input.source["record_id"] == "cert-product-report-001"
    assert task.review_input.source["attachment_uuid"] == "attach-product-report-001"
    assert task.review_input.source["attachment_ref_id"] == "cert-product-report-001"
    assert task.review_input.source["document_category"] == "sku"
    assert task.review_input.source["sku_number"] == "1001010562202606290001"
    assert task.review_input.source["business_number"] == "797120694064660482"
    assert task.review_input.source["vendor_id"] == "VENDOR-001"
    assert task.review_input.source["file_store_key"] == "oss-key-product-report"


def test_fetch_product_report_source_tasks_rejects_missing_url():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-product-report-001",
                "category": "sku",
                "typeName": "产品报告",
                "vendorName": "广东乃一口食品有限公司",
            }
        ]
    )

    try:
        fetch_product_report_source_tasks(client, "select * from certification")
    except ProductReportSourceTaskError as error:
        assert error.code == "PRODUCT_REPORT_SOURCE_URL_MISSING"
        assert error.record_id == "cert-product-report-001"
    else:
        raise AssertionError("missing URL should be rejected explicitly")


def test_fetch_product_report_source_tasks_skips_deleted_and_non_sku_rows():
    rows = [
        {
            "uuid": "cert-deleted",
            "category": "sku",
            "typeName": "产品报告",
            "vendorName": "广东乃一口食品有限公司",
            "url": "https://files.example.test/deleted.pdf",
            "deleted": 1,
            "removed": 0,
        },
        {
            "uuid": "cert-removed",
            "category": "sku",
            "typeName": "产品报告",
            "vendorName": "广东乃一口食品有限公司",
            "url": "https://files.example.test/removed.pdf",
            "deleted": 0,
            "removed": 1,
        },
        {
            "uuid": "cert-vendor",
            "category": "vendor",
            "typeName": "产品报告",
            "vendorName": "广东乃一口食品有限公司",
            "url": "https://files.example.test/vendor.pdf",
            "deleted": 0,
            "removed": 0,
        },
    ]

    tasks = fetch_product_report_source_tasks(StubSqlClient(rows), "select 1")

    assert tasks == []


def test_fetch_product_report_source_tasks_deduplicates_records_by_record_and_attachment():
    row = {
        "uuid": "cert-product-report-001",
        "refId": "cert-product-report-001",
        "category": "sku",
        "typeName": "产品报告",
        "vendorName": "广东乃一口食品有限公司",
        "url": "https://files.example.test/product-report.pdf",
        "deleted": 0,
        "removed": 0,
    }

    tasks = fetch_product_report_source_tasks(StubSqlClient([row, dict(row)]), "select 1")

    assert len(tasks) == 1


def test_fetch_one_product_report_source_task_uses_default_srm_sql():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-product-report-001",
                "refId": "cert-product-report-001",
                "category": "sku",
                "typeName": "产品报告",
                "vendorName": "广东乃一口食品有限公司",
                "url": "https://files.example.test/product-report.pdf",
                "deleted": 0,
                "removed": 0,
            }
        ]
    )

    task = fetch_one_product_report_source_task(client)

    assert client.executed_sql == [DEFAULT_PRODUCT_REPORT_SOURCE_SQL]
    assert task is not None
    normalized_sql = " ".join(DEFAULT_PRODUCT_REPORT_SOURCE_SQL.split())
    assert "ods_srm_srm_certification_df t1" in DEFAULT_PRODUCT_REPORT_SOURCE_SQL
    assert "ods_srm_srm_attachment_df t2" in DEFAULT_PRODUCT_REPORT_SOURCE_SQL
    assert "t2.tenant = '8560'" in normalized_sql
    assert "t1.category = 'sku'" in normalized_sql
    assert "t1.typeName = '产品报告'" in normalized_sql
    assert "t1.deleted = 0" in normalized_sql
    assert "t2.removed = 0" in normalized_sql
    assert "t2.url is not null" in DEFAULT_PRODUCT_REPORT_SOURCE_SQL.lower()
    assert "t2.url <> ''" in DEFAULT_PRODUCT_REPORT_SOURCE_SQL.lower()
    assert "order by rand()" in DEFAULT_PRODUCT_REPORT_SOURCE_SQL.lower()
    assert "limit 1" in DEFAULT_PRODUCT_REPORT_SOURCE_SQL.lower()


def test_fetch_one_product_report_source_task_returns_none_when_no_rows():
    task = fetch_one_product_report_source_task(StubSqlClient([]))

    assert task is None
