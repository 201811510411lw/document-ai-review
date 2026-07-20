# StarRocks Source Tables

These scripts define the StarRocks tables consumed by the document-review
source queries. They do not copy source-system data into StarRocks.

Apply the DDL in this order within the configured `STARROCKS_DATABASE`:

1. `create_starrocks_srm_batch_report_source_tables.sql`
2. `create_starrocks_oa_ecology_source_tables.sql`

The SRM script creates `ods_srm_srm_certification_df`, the shared
`ods_srm_srm_attachment_df`, and the batch-report tables. The OA script creates
the five `ods_oa_ecology_*_df` tables used by tobacco-license review.

Keep the source tables synchronized before enabling review APIs or the daily
review scheduler. The application now queries these StarRocks tables through
the `STARROCKS_*` connection settings; `REVIEW_RESULT_MYSQL_*` remains the
transactional store for review results, manual review, and notification data.
