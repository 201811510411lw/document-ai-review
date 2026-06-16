from typing import Any

from app.integrations.srm.business_license_tasks import (
    DEFAULT_BUSINESS_LICENSE_SOURCE_SQL,
    SqlFetchClient,
    fetch_one_business_license_source_task,
)
from app.services.review_service import ReviewService


def review_one_srm_business_license(
    *,
    sql_client: SqlFetchClient,
    review_service: ReviewService,
    sql: str = DEFAULT_BUSINESS_LICENSE_SOURCE_SQL,
) -> Any | None:
    task = fetch_one_business_license_source_task(sql_client, sql)
    if task is None:
        return None
    return review_service.review(
        task.review_input,
        use_case_name="business_license",
    )
