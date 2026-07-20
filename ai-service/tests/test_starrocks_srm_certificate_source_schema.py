from pathlib import Path

from app.integrations.srm.business_license_tasks import DEFAULT_BUSINESS_LICENSE_SOURCE_SQL
from app.integrations.srm.food_license_tasks import DEFAULT_FOOD_LICENSE_SOURCE_SQL
from app.integrations.srm.food_production_license_tasks import (
    DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL,
)
from app.integrations.srm.product_report_tasks import DEFAULT_PRODUCT_REPORT_SOURCE_SQL
from app.services.scheduled_review_service import (
    SRM_PRODUCT_SQL_TEMPLATE,
    SRM_SQL_TEMPLATE,
)


def test_certificate_source_queries_use_starrocks_source_tables():
    source_sql = (
        DEFAULT_BUSINESS_LICENSE_SOURCE_SQL,
        DEFAULT_FOOD_LICENSE_SOURCE_SQL,
        DEFAULT_FOOD_PRODUCTION_LICENSE_SOURCE_SQL,
        DEFAULT_PRODUCT_REPORT_SOURCE_SQL,
        SRM_SQL_TEMPLATE,
        SRM_PRODUCT_SQL_TEMPLATE,
    )

    for sql in source_sql:
        assert "ods_srm_srm_certification_df t1" in sql
        assert "ods_srm_srm_attachment_df t2" in sql
        assert "srm.certification" not in sql
        assert "srm.attachment" not in sql


def test_certificate_source_schema_covers_review_query_columns():
    repo_root = Path(__file__).resolve().parents[2]
    ddl = (repo_root / "docs/sql/create_starrocks_srm_batch_report_source_tables.sql").read_text(
        encoding="utf-8"
    )

    for column in (
        "uuid",
        "created",
        "tenant",
        "category",
        "typeName",
        "typeCode",
        "vendorId",
        "vendorName",
        "num",
        "number",
        "remark",
        "expiredBegin",
        "expiredEnd",
        "deleted",
    ):
        assert f"`{column}`" in ddl

    assert "CREATE TABLE IF NOT EXISTS ods_srm_srm_certification_df" in ddl
