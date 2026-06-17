from app.integrations.srm.business_license_tasks import (
    BusinessLicenseSourceTaskError,
    DEFAULT_BUSINESS_LICENSE_SOURCE_SQL,
    fetch_one_business_license_source_task,
    fetch_business_license_source_tasks,
)


class StubSqlClient:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        return self.rows


def test_fetch_business_license_source_tasks_maps_sql_rows_to_review_inputs():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-business-001",
                "refId": "attach-business-001",
                "typeName": "营业执照",
                "vendorName": "成都示例商贸有限公司",
                "number": "1092453497593159680",
                "num": "91510100MA0000000X",
                "url": "https://files.example.test/business-license.pdf",
                "attachmentName": "business-license.pdf",
            }
        ]
    )

    tasks = fetch_business_license_source_tasks(client, "select * from certification")

    assert client.executed_sql == ["select * from certification"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task.record.record_id == "cert-business-001"
    assert task.record.attachment_ref_id == "attach-business-001"
    assert task.review_input.declared_document_type == "business_license"
    assert task.review_input.supplier_name == "成都示例商贸有限公司"
    assert task.review_input.supplier_credit_code == "91510100MA0000000X"
    assert task.review_input.file.file_uri == "https://files.example.test/business-license.pdf"
    assert task.review_input.file.file_name == "business-license.pdf"
    assert task.review_input.source["record_id"] == "cert-business-001"
    assert task.review_input.source["attachment_ref_id"] == "attach-business-001"


def test_fetch_business_license_source_tasks_returns_empty_list_for_empty_sql_result():
    tasks = fetch_business_license_source_tasks(StubSqlClient([]), "select 1")

    assert tasks == []


def test_fetch_business_license_source_tasks_rejects_missing_url():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-business-001",
                "typeName": "营业执照",
                "vendorName": "成都示例商贸有限公司",
                "number": "91510100MA0000000X",
            }
        ]
    )

    try:
        fetch_business_license_source_tasks(client, "select * from certification")
    except BusinessLicenseSourceTaskError as error:
        assert error.code == "BUSINESS_LICENSE_SOURCE_URL_MISSING"
        assert error.record_id == "cert-business-001"
    else:
        raise AssertionError("missing URL should be rejected explicitly")


def test_fetch_business_license_source_tasks_deduplicates_records_by_record_and_attachment():
    row = {
        "uuid": "cert-business-001",
        "refId": "attach-business-001",
        "typeName": "营业执照",
        "vendorName": "成都示例商贸有限公司",
        "number": "91510100MA0000000X",
        "url": "https://files.example.test/business-license.pdf",
    }

    tasks = fetch_business_license_source_tasks(StubSqlClient([row, dict(row)]), "select 1")

    assert len(tasks) == 1


def test_fetch_one_business_license_source_task_uses_default_srm_sql():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-business-001",
                "refId": "attach-business-001",
                "typeName": "营业执照",
                "vendorName": "成都示例商贸有限公司",
                "number": "91510100MA0000000X",
                "url": "https://files.example.test/business-license.png",
            }
        ]
    )

    task = fetch_one_business_license_source_task(client)

    assert client.executed_sql == [DEFAULT_BUSINESS_LICENSE_SOURCE_SQL]
    assert task is not None
    assert task.review_input.file.file_uri == "https://files.example.test/business-license.png"
    normalized_sql = " ".join(DEFAULT_BUSINESS_LICENSE_SOURCE_SQL.split())
    assert "srm.certification t1" in DEFAULT_BUSINESS_LICENSE_SOURCE_SQL
    assert "srm.attachment t2" in DEFAULT_BUSINESS_LICENSE_SOURCE_SQL
    assert "typeName = '营业执照'" in normalized_sql
    assert "t2.url is not null" in DEFAULT_BUSINESS_LICENSE_SOURCE_SQL.lower()
    assert "t2.url <> ''" in DEFAULT_BUSINESS_LICENSE_SOURCE_SQL.lower()
    assert "limit 1" in DEFAULT_BUSINESS_LICENSE_SOURCE_SQL.lower()


def test_fetch_one_business_license_source_task_returns_none_when_no_rows():
    task = fetch_one_business_license_source_task(StubSqlClient([]))

    assert task is None
