from app.integrations.starrocks.tobacco_license_sources import (
    build_pending_stores_sql,
    build_tobacco_license_source_sql,
    fetch_pending_stores,
    fetch_latest_tobacco_license_source_files,
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
