from app.integrations.srm.food_production_license_tasks import (
    DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL,
    FoodProductionLicenseSourceTaskError,
    fetch_food_production_license_source_tasks,
    fetch_one_food_production_license_source_task,
)


class StubSqlClient:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        return self.rows


def test_fetch_food_production_license_source_tasks_maps_sql_rows_to_review_inputs():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-production-001",
                "refId": "attach-food-production-001",
                "typeName": "食品生产许可证",
                "vendorName": "成都示例食品生产有限公司",
                "number": "SC10151010000000",
                "num": "91510100MA00000000",
                "url": "https://files.example.test/food-production-license.pdf",
                "attachmentName": "food-production-license.pdf",
            }
        ]
    )

    tasks = fetch_food_production_license_source_tasks(client, "select * from certification")

    assert client.executed_sql == ["select * from certification"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task.record.record_id == "cert-food-production-001"
    assert task.record.attachment_ref_id == "attach-food-production-001"
    assert task.review_input.declared_document_type == "food_production_license"
    assert task.review_input.supplier_name == "成都示例食品生产有限公司"
    assert task.review_input.supplier_credit_code == "91510100MA00000000"
    assert (
        task.review_input.file.file_uri
        == "https://files.example.test/food-production-license.pdf"
    )
    assert task.review_input.file.file_name == "food-production-license.pdf"
    assert task.review_input.source["record_id"] == "cert-food-production-001"
    assert task.review_input.source["attachment_ref_id"] == "attach-food-production-001"


def test_fetch_food_production_license_source_tasks_does_not_treat_sc_number_as_credit_code():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-production-001",
                "refId": "attach-food-production-001",
                "typeName": "食品生产许可证",
                "vendorName": "长沙波浪食品有限公司",
                "number": "SC12443010505553",
                "url": "https://files.example.test/food-production-license.pdf",
            }
        ]
    )

    tasks = fetch_food_production_license_source_tasks(client, "select * from certification")

    assert len(tasks) == 1
    assert tasks[0].review_input.supplier_credit_code == ""
    assert tasks[0].record.business_number == "SC12443010505553"


def test_fetch_food_production_license_source_tasks_rejects_missing_url():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-production-001",
                "typeName": "食品生产许可证",
                "vendorName": "成都示例食品生产有限公司",
                "number": "SC10151010000000",
                "num": "91510100MA00000000",
            }
        ]
    )

    try:
        fetch_food_production_license_source_tasks(client, "select * from certification")
    except FoodProductionLicenseSourceTaskError as error:
        assert error.code == "FOOD_PRODUCTION_LICENSE_SOURCE_URL_MISSING"
        assert error.record_id == "cert-food-production-001"
    else:
        raise AssertionError("missing URL should be rejected explicitly")


def test_fetch_food_production_license_source_tasks_deduplicates_records():
    row = {
        "uuid": "cert-food-production-001",
        "refId": "attach-food-production-001",
        "typeName": "食品生产许可证",
        "vendorName": "成都示例食品生产有限公司",
        "number": "SC10151010000000",
        "num": "91510100MA00000000",
        "url": "https://files.example.test/food-production-license.pdf",
    }

    tasks = fetch_food_production_license_source_tasks(
        StubSqlClient([row, dict(row)]),
        "select 1",
    )

    assert len(tasks) == 1


def test_fetch_one_food_production_license_source_task_uses_default_srm_sql():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-production-001",
                "refId": "attach-food-production-001",
                "typeName": "食品生产许可证",
                "vendorName": "成都示例食品生产有限公司",
                "number": "SC10151010000000",
                "num": "91510100MA00000000",
                "url": "https://files.example.test/food-production-license.png",
            }
        ]
    )

    task = fetch_one_food_production_license_source_task(client)

    assert client.executed_sql == [DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL]
    assert task is not None
    assert (
        task.review_input.file.file_uri
        == "https://files.example.test/food-production-license.png"
    )
    normalized_sql = " ".join(DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL.split())
    assert "srm.certification t1" in DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL
    assert "srm.attachment t2" in DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL
    assert "t1.typeName = '食品生产许可证'" in normalized_sql
    assert "t2.url is not null" in DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL.lower()
    assert "t2.url <> ''" in DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL.lower()
    assert "limit 1" in DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL.lower()


def test_fetch_one_food_production_license_source_task_returns_none_when_no_rows():
    task = fetch_one_food_production_license_source_task(StubSqlClient([]))

    assert task is None
