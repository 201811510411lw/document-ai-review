from app.integrations.starrocks.tobacco_license_sources import (
    OA_MYSQL_TOBACCO_SOURCE_TABLES,
    build_oa_review_submission_sql,
    build_pending_stores_sql,
    build_tobacco_license_source_by_request_sql,
    build_tobacco_license_source_sql,
    fetch_pending_stores,
    fetch_latest_tobacco_license_source_files,
    fetch_latest_oa_review_submission,
    fetch_tobacco_license_source_files_by_request,
)


class StubSqlClient:
    def __init__(self, rows):
        self.rows = rows
        self.executed_sql = []

    def fetch_all(self, sql):
        self.executed_sql.append(sql)
        return self.rows


def test_build_tobacco_license_source_sql_filters_store_and_attachment_chain():
    sql = build_tobacco_license_source_sql("B65230024")

    assert "ods_oa_ecology_formtable_main_283_df" in sql
    assert "ods_oa_ecology_workflow_requestbase_df" in sql
    assert "ods_oa_ecology_docdetail_df" in sql
    assert "ods_oa_ecology_docimagefile_df" in sql
    assert "ods_oa_ecology_imagefile_df" in sql
    assert "r.WORKFLOWID = 614" in sql
    assert "FIND_IN_SET" in sql
    assert "f.yyzz AS business_license_docids" in sql
    assert "'business_license'" in sql
    assert "d.DOCSUBJECT" in sql
    assert "dif.IMAGEFILENAME" in sql
    assert "i.IMAGEFILENAME" in sql
    assert "'承诺函'" in sql
    assert "f.mdbm = 'B65230024'" in sql
    assert "ORDER BY r.CREATEDATE DESC" in sql


def test_fetch_latest_tobacco_license_source_files_maps_latest_form_rows_only():
    latest_row = {
        "form_id": 3497,
        "requestid": 2801287,
        "store_name": "B65230024",
        "store_code": "B65230024",
        "summary_title": "",
        "content_summary": "已获得烟草证",
        "tobacco_license_docids": "824576",
        "business_license_docids": "824577",
        "document_role": "tobacco_license",
        "valid_from": "2026-06-25",
        "valid_to": "2029-06-01",
        "workflow_id": 614,
        "request_name": "香烟销售权限申请/香烟商品建档申请-徐飞-2026-07-09",
        "created_date": "2026-07-09",
        "created_time": "15:20:50",
        "request_status": "招商审批",
        "docid": 824576,
        "doc_subject": "y",
        "imagefile_id": 1409517,
        "docimage_filename": "y.jpg",
        "real_filename": "y.jpg",
        "file_real_path": "/data/oaec/202607/J/file.zip",
        "is_zip": "1",
        "is_encrypt": "0",
        "is_aes_encrypt": 0,
        "file_size": "253894",
    }
    client = StubSqlClient(
        [
            latest_row,
            {**latest_row, "imagefile_id": 1409518, "real_filename": "y-back.jpg"},
            {**latest_row, "form_id": 3496, "requestid": 2801000},
        ]
    )

    files = fetch_latest_tobacco_license_source_files(client, "B65230024")

    assert len(files) == 2
    assert files[0].store_code == "B65230024"
    assert files[0].docid == 824576
    assert files[0].business_license_docids == "824577"
    assert files[0].document_role == "tobacco_license"
    assert files[0].imagefile_id == 1409517
    assert files[0].file_real_path == "/data/oaec/202607/J/file.zip"
    assert len(client.executed_sql) == 1


def test_fetch_latest_tobacco_license_source_files_returns_empty_list():
    files = fetch_latest_tobacco_license_source_files(StubSqlClient([]), "unknown")

    assert files == []


def test_build_source_by_request_sql_uses_exact_workflow_and_request_identity():
    sql = build_tobacco_license_source_by_request_sql(2801287)

    assert "r.WORKFLOWID = 614" in sql
    assert "f.requestid = 2801287" in sql
    assert "f.mdbm =" not in sql
    assert "INSTR(IFNULL(f.qsbt, '')" not in sql
    assert "INSTR(IFNULL(f.nrgk, '')" not in sql
    assert "INSTR(IFNULL(r.REQUESTNAME, '')" not in sql
    assert "ORDER BY d.ID, dif.IMAGEFILEID" in sql
    assert "'承诺函'" in sql


def test_build_source_by_request_sql_supports_oa_mysql_table_names():
    sql = build_tobacco_license_source_by_request_sql(
        2801287,
        tables=OA_MYSQL_TOBACCO_SOURCE_TABLES,
    )

    assert "FROM formtable_main_283 f" in sql
    assert "JOIN workflow_requestbase r" in sql
    assert "LEFT JOIN docdetail d" in sql
    assert "LEFT JOIN docimagefile dif" in sql
    assert "LEFT JOIN imagefile i" in sql
    assert "ods_oa_ecology_" not in sql


def test_build_oa_review_submission_sql_uses_exact_submit_event_identity():
    sql = build_oa_review_submission_sql(2855868, workflow_id=614)

    assert "FROM workflow_requestlog" in sql
    assert "REQUESTID = 2855868" in sql
    assert "WORKFLOWID = 614" in sql
    assert "NODEID = 7304" in sql
    assert "DESTNODEID = 8081" in sql
    assert "LOGTYPE = '2'" in sql
    assert "COUNT(*) OVER () AS submission_version" in sql
    assert "ORDER BY OPERATEDATE DESC, OPERATETIME DESC, LOGID DESC" in sql


def test_fetch_latest_oa_review_submission_maps_latest_log():
    client = StubSqlClient([
        {"submission_log_id": 23814310, "submission_version": 3},
    ])

    identity = fetch_latest_oa_review_submission(client, 2855868, workflow_id=614)

    assert identity is not None
    assert identity.submission_log_id == 23814310
    assert identity.submission_version == 3


def test_fetch_latest_oa_review_submission_returns_none_without_log():
    assert fetch_latest_oa_review_submission(
        StubSqlClient([]),
        2855868,
        workflow_id=614,
    ) is None


def test_fetch_source_files_by_request_does_not_select_another_request():
    expected = {
        "form_id": 3497,
        "requestid": 2801287,
        "store_code": "B65230024",
        "workflow_id": 614,
        "document_role": "tobacco_license",
        "file_real_path": "/data/oaec/license.jpg",
    }
    client = StubSqlClient([
        expected,
        {**expected, "requestid": 2801288, "file_real_path": "/data/oaec/other.jpg"},
    ])

    files = fetch_tobacco_license_source_files_by_request(client, 2801287)

    assert [item.requestid for item in files] == [2801287]
    assert "f.requestid = 2801287" in client.executed_sql[0]


def test_fetch_source_files_by_request_returns_empty_without_fallback():
    client = StubSqlClient([])

    assert fetch_tobacco_license_source_files_by_request(client, 2801287) == []
    assert len(client.executed_sql) == 1


def test_pending_stores_include_latest_oa_title_and_content():
    sql = build_pending_stores_sql(page=2, page_size=20)
    assert "ROW_NUMBER() OVER" in sql
    assert ") AS latest_row_num" in sql
    assert "WHERE latest_row_num = 1" in sql
    assert ") AS row_number" not in sql
    assert "r.REQUESTNAME AS request_name" in sql
    assert "f.nrgk AS content_summary" in sql
    assert "LIMIT 20, 20" in sql

    stores = fetch_pending_stores(StubSqlClient([{
        "store_code": "B65230024",
        "store_name": "成都示例门店",
        "requestid": 2801287,
        "request_name": "烟草商品建档申请 - 成都示例门店",
        "summary_title": "烟草销售申请",
        "content_summary": "提交营业执照和烟草专卖零售许可证。",
        "submit_time": "2026-07-16 10:00:00",
    }]))

    assert stores == [{
        "store_code": "B65230024",
        "store_name": "成都示例门店",
        "requestid": 2801287,
        "submit_date": "2026-07-16",
        "request_name": "烟草商品建档申请 - 成都示例门店",
        "summary_title": "烟草销售申请",
        "content_summary": "提交营业执照和烟草专卖零售许可证。",
    }]
