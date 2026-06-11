import json

from app.core.config import load_local_env
from app.integrations.mysql_client import MySqlFetchClient, mysql_settings_from_env
from app.integrations.srm.business_license_entrypoint import (
    review_one_srm_business_license,
)
from app.services.review_service import ReviewService


def main() -> None:
    load_local_env()
    result = review_one_srm_business_license(
        sql_client=MySqlFetchClient(mysql_settings_from_env()),
        review_service=ReviewService(),
    )
    if result is None:
        print(json.dumps({"status": "NO_SOURCE_TASK"}, ensure_ascii=False))
        return
    if hasattr(result, "model_dump"):
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
