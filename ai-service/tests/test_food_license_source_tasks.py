from app.integrations.srm.food_license_tasks import (
    DEFAULT_FOOD_LICENSE_SOURCE_SQL,
    FoodLicenseSourceTaskError,
    fetch_food_license_source_tasks,
    fetch_one_food_license_source_task,
)


class StubSqlClient:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        return self.rows


def test_fetch_food_license_source_tasks_maps_sql_rows_to_review_inputs():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-001",
                "refId": "attach-food-001",
                "typeName": "食品经营许可证",
                "vendorName": "成都示例食品有限公司",
                "number": "JY15101000000000",
                "num": "91510100MA00000000",
                "url": "https://files.example.test/food-license.pdf",
                "attachmentName": "food-license.pdf",
            }
        ]
    )

    tasks = fetch_food_license_source_tasks(client, "select * from certification")

    assert client.executed_sql == ["select * from certification"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task.record.record_id == "cert-food-001"
    assert task.record.attachment_ref_id == "attach-food-001"
    assert task.review_input.declared_document_type == "food_license"
    assert task.review_input.supplier_name == "成都示例食品有限公司"
    assert task.review_input.supplier_credit_code == "91510100MA00000000"
    assert task.review_input.file.file_uri == "https://files.example.test/food-license.pdf"
    assert task.review_input.file.file_name == "food-license.pdf"
    assert task.review_input.source["record_id"] == "cert-food-001"
    assert task.review_input.source["attachment_ref_id"] == "attach-food-001"


def test_fetch_food_license_source_tasks_does_not_treat_serial_num_as_credit_code():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-serial",
                "refId": "attach-food-serial",
                "typeName": "食品经营许可证",
                "vendorName": "成都市聚和盛供应链管理有限公司",
                "number": "781473739871449088",
                "num": "1001010427202311270017",
                "url": "https://files.example.test/food-license.jpg",
                "attachmentName": "食品经营许可证1.jpg",
            }
        ]
    )

    tasks = fetch_food_license_source_tasks(client, "select * from certification")

    assert len(tasks) == 1
    assert tasks[0].review_input.supplier_credit_code == ""
    assert tasks[0].record.business_num == "1001010427202311270017"


def test_fetch_food_license_source_tasks_routes_rows_marked_as_food_production_license():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-wrong-type",
                "refId": "attach-food-wrong-type",
                "typeName": "食品经营许可证",
                "remark": "食品生产许可证",
                "vendorName": "江苏香之派食品有限公司",
                "number": "781923075088699392",
                "num": "SC10432130000012",
                "url": "https://files.example.test/食品生产许可证.jpg",
                "attachmentName": "食品生产许可证.jpg",
                "storeId": "vss-web/食品生产许可证.jpg",
            }
        ]
    )

    tasks = fetch_food_license_source_tasks(client, "select * from certification")

    assert len(tasks) == 1
    assert tasks[0].record.declared_document_type == "food_license"
    assert tasks[0].review_input.declared_document_type == "food_production_license"
    assert tasks[0].review_input.supplier_credit_code == ""
    assert tasks[0].review_input.source["document_type_evidence"] == {
        "declared_document_type": "food_license",
        "resolved_document_type": "food_production_license",
        "hints": [
            "remark:食品生产许可证",
            "attachmentName:食品生产许可证",
            "storeId:食品生产许可证",
            "url:食品生产许可证",
            "num:SC",
        ],
        "conflict": True,
    }


def test_fetch_food_license_source_tasks_routes_food_production_detail_attachment():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-production-detail",
                "refId": "attach-food-production-detail",
                "typeName": "食品经营许可证",
                "vendorName": "浙江优拉食品有限公司",
                "number": "SC10833040205187",
                "url": "https://files.example.test/2-3食品生产许可品种明细表.jpg",
                "attachmentName": "2-3食品生产许可品种明细表.jpg",
            }
        ]
    )

    tasks = fetch_food_license_source_tasks(client, "select * from certification")

    assert len(tasks) == 1
    assert tasks[0].review_input.declared_document_type == "food_production_license"
    assert tasks[0].review_input.source["document_type_evidence"] == {
        "declared_document_type": "food_license",
        "resolved_document_type": "food_production_license",
        "hints": [
            "attachmentName:食品生产许可品种明细表",
            "url:食品生产许可品种明细表",
            "number:SC",
        ],
        "conflict": True,
    }


def test_fetch_food_license_source_tasks_rejects_missing_url():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-001",
                "typeName": "食品经营许可证",
                "vendorName": "成都示例食品有限公司",
                "number": "JY15101000000000",
                "num": "91510100MA00000000",
            }
        ]
    )

    try:
        fetch_food_license_source_tasks(client, "select * from certification")
    except FoodLicenseSourceTaskError as error:
        assert error.code == "FOOD_LICENSE_SOURCE_URL_MISSING"
        assert error.record_id == "cert-food-001"
    else:
        raise AssertionError("missing URL should be rejected explicitly")


def test_fetch_food_license_source_tasks_deduplicates_records_by_record_and_attachment():
    row = {
        "uuid": "cert-food-001",
        "refId": "attach-food-001",
        "typeName": "食品经营许可证",
        "vendorName": "成都示例食品有限公司",
        "number": "JY15101000000000",
        "num": "91510100MA00000000",
        "url": "https://files.example.test/food-license.pdf",
    }

    tasks = fetch_food_license_source_tasks(StubSqlClient([row, dict(row)]), "select 1")

    assert len(tasks) == 1


def test_fetch_one_food_license_source_task_uses_default_srm_sql():
    client = StubSqlClient(
        [
            {
                "uuid": "cert-food-001",
                "refId": "attach-food-001",
                "typeName": "食品经营许可证",
                "vendorName": "成都示例食品有限公司",
                "number": "JY15101000000000",
                "num": "91510100MA00000000",
                "url": "https://files.example.test/food-license.png",
            }
        ]
    )

    task = fetch_one_food_license_source_task(client)

    assert client.executed_sql == [DEFAULT_FOOD_LICENSE_SOURCE_SQL]
    assert task is not None
    assert task.review_input.file.file_uri == "https://files.example.test/food-license.png"
    normalized_sql = " ".join(DEFAULT_FOOD_LICENSE_SOURCE_SQL.split())
    assert "ods_srm_srm_certification_df t1" in DEFAULT_FOOD_LICENSE_SOURCE_SQL
    assert "ods_srm_srm_attachment_df t2" in DEFAULT_FOOD_LICENSE_SOURCE_SQL
    assert "t1.typeName = '食品经营许可证'" in normalized_sql
    assert "t2.url is not null" in DEFAULT_FOOD_LICENSE_SOURCE_SQL.lower()
    assert "t2.url <> ''" in DEFAULT_FOOD_LICENSE_SOURCE_SQL.lower()
    assert "order by rand()" in DEFAULT_FOOD_LICENSE_SOURCE_SQL.lower()
    assert "limit 1" in DEFAULT_FOOD_LICENSE_SOURCE_SQL.lower()


def test_fetch_one_food_license_source_task_returns_none_when_no_rows():
    task = fetch_one_food_license_source_task(StubSqlClient([]))

    assert task is None
