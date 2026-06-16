from app.integrations.srm.business_license_entrypoint import review_one_srm_business_license
from app.integrations.srm.business_license_tasks import DEFAULT_BUSINESS_LICENSE_SOURCE_SQL


class StubSqlClient:
    def __init__(self):
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        return [
            {
                "uuid": "cert-business-001",
                "refId": "attach-business-001",
                "typeName": "营业执照",
                "vendorName": "成都示例商贸有限公司",
                "number": "91510100MA0000000X",
                "url": "https://files.example.test/business-license.png",
                "attachmentName": "business-license.png",
            }
        ]


class StubReviewService:
    def __init__(self):
        self.calls = []

    def review(self, review_input, use_case_name=None):
        self.calls.append((review_input, use_case_name))
        return {"status": "stubbed"}


def test_review_one_srm_business_license_fetches_default_sql_and_reviews_task():
    sql_client = StubSqlClient()
    review_service = StubReviewService()

    result = review_one_srm_business_license(
        sql_client=sql_client,
        review_service=review_service,
    )

    assert result == {"status": "stubbed"}
    assert sql_client.executed_sql == [DEFAULT_BUSINESS_LICENSE_SOURCE_SQL]
    review_input, use_case_name = review_service.calls[0]
    assert use_case_name == "business_license"
    assert review_input.supplier_name == "成都示例商贸有限公司"
    assert review_input.file.file_uri == "https://files.example.test/business-license.png"
