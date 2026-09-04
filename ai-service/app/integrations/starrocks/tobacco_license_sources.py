from typing import Any, Mapping, Protocol

from pydantic import BaseModel, Field


OA_TOBACCO_APPLICANT_NODE_ID = 7304
OA_TOBACCO_ROBOT_NODE_ID = 8081


class SqlFetchClient(Protocol):
    def fetch_all(self, sql: str) -> list[dict[str, Any]]:
        ...


class TobaccoLicenseSourceFile(BaseModel):
    form_id: int | None = None
    requestid: int | None = None
    store_name: str | None = None
    store_code: str | None = None
    summary_title: str | None = None
    content_summary: str | None = None
    tobacco_license_docids: str | None = None
    business_license_docids: str | None = None
    document_role: str = "tobacco_license"
    valid_from: str | None = None
    valid_to: str | None = None
    mdms: int | None = None
    mdms1: int | None = None
    workflow_id: int | None = None
    request_name: str | None = None
    created_date: str | None = None
    created_time: str | None = None
    request_status: str | None = None
    docid: int | None = None
    doc_subject: str | None = None
    imagefile_id: int | None = None
    docimage_filename: str | None = None
    real_filename: str | None = None
    file_real_path: str
    is_zip: str | None = None
    is_encrypt: str | None = None
    is_aes_encrypt: int | None = None
    file_size: str | None = None


class OaReviewSubmissionIdentity(BaseModel):
    submission_log_id: int = Field(gt=0)
    submission_version: int = Field(gt=0)


class TobaccoLicenseSourceTaskError(ValueError):
    def __init__(self, code: str, message: str, *, store_identifier: str | None = None):
        self.code = code
        self.store_identifier = store_identifier
        super().__init__(message)


STARROCKS_TOBACCO_SOURCE_TABLES = {
    "form": "ods_oa_ecology_formtable_main_283_df",
    "request": "ods_oa_ecology_workflow_requestbase_df",
    "docdetail": "ods_oa_ecology_docdetail_df",
    "docimagefile": "ods_oa_ecology_docimagefile_df",
    "imagefile": "ods_oa_ecology_imagefile_df",
}

OA_MYSQL_TOBACCO_SOURCE_TABLES = {
    "form": "formtable_main_283",
    "request": "workflow_requestbase",
    "docdetail": "docdetail",
    "docimagefile": "docimagefile",
    "imagefile": "imagefile",
    "requestlog": "workflow_requestlog",
}


def _source_tables(sql_client: SqlFetchClient) -> Mapping[str, str]:
    configured = getattr(sql_client, "source_tables", None)
    return configured or STARROCKS_TOBACCO_SOURCE_TABLES


def build_tobacco_license_source_sql(
    store_identifier: str,
    *,
    limit: int = 50,
    tables: Mapping[str, str] | None = None,
) -> str:
    store_identifier = _required_text(store_identifier, "store_identifier")
    safe_limit = max(1, min(int(limit), 200))
    store_literal = _sql_string_literal(store_identifier)
    identity_predicate = f"""(
    f.mdbm = {store_literal}
    OR f.mdmc = {store_literal}
    OR INSTR(IFNULL(f.qsbt, ''), {store_literal}) > 0
    OR INSTR(IFNULL(f.nrgk, ''), {store_literal}) > 0
    OR INSTR(IFNULL(r.REQUESTNAME, ''), {store_literal}) > 0
  )"""
    return _build_source_sql(
        workflow_id=614,
        identity_predicate=identity_predicate,
        order_by="r.CREATEDATE DESC, r.CREATETIME DESC, f.id DESC, d.ID, dif.IMAGEFILEID",
        limit=safe_limit,
        tables=tables or STARROCKS_TOBACCO_SOURCE_TABLES,
    )


def build_tobacco_license_source_by_request_sql(
    requestid: int,
    *,
    workflow_id: int = 614,
    tables: Mapping[str, str] | None = None,
) -> str:
    safe_requestid = _required_positive_int(requestid, "requestid")
    safe_workflow_id = _required_positive_int(workflow_id, "workflow_id")
    return _build_source_sql(
        workflow_id=safe_workflow_id,
        identity_predicate=f"f.requestid = {safe_requestid}",
        order_by="d.ID, dif.IMAGEFILEID",
        tables=tables or STARROCKS_TOBACCO_SOURCE_TABLES,
    )


def build_oa_review_submission_sql(
    requestid: int,
    *,
    workflow_id: int = 614,
    table: str = "workflow_requestlog",
) -> str:
    safe_requestid = _required_positive_int(requestid, "requestid")
    safe_workflow_id = _required_positive_int(workflow_id, "workflow_id")
    return f"""
SELECT
    LOGID AS submission_log_id,
    COUNT(*) OVER () AS submission_version
FROM {table}
WHERE REQUESTID = {safe_requestid}
  AND WORKFLOWID = {safe_workflow_id}
  AND NODEID = {OA_TOBACCO_APPLICANT_NODE_ID}
  AND DESTNODEID = {OA_TOBACCO_ROBOT_NODE_ID}
  AND LOGTYPE = '2'
ORDER BY OPERATEDATE DESC, OPERATETIME DESC, LOGID DESC
LIMIT 1
""".strip()


def _build_source_sql(
    *,
    workflow_id: int,
    identity_predicate: str,
    order_by: str,
    limit: int | None = None,
    tables: Mapping[str, str] = STARROCKS_TOBACCO_SOURCE_TABLES,
) -> str:
    limit_clause = f"\nLIMIT {limit}" if limit is not None else ""
    return f"""
SELECT
    f.id AS form_id,
    f.requestid,
    f.mdmc AS store_name,
    f.mdbm AS store_code,
    f.qsbt AS summary_title,
    f.nrgk AS content_summary,
    f.ycxsxkz AS tobacco_license_docids,
    f.yyzz AS business_license_docids,
    CASE
      WHEN FIND_IN_SET(CONCAT(d.ID, ''), REPLACE(f.yyzz, ' ', '')) > 0
        THEN 'business_license'
      ELSE 'tobacco_license'
    END AS document_role,
    f.yczyxqksrq AS valid_from,
    f.yczyxqjsrq AS valid_to,
    f.mdms,
    f.mdms1,
    r.WORKFLOWID AS workflow_id,
    r.REQUESTNAME AS request_name,
    r.CREATEDATE AS created_date,
    r.CREATETIME AS created_time,
    r.STATUS AS request_status,
    d.ID AS docid,
    d.DOCSUBJECT AS doc_subject,
    dif.IMAGEFILEID AS imagefile_id,
    dif.IMAGEFILENAME AS docimage_filename,
    i.IMAGEFILENAME AS real_filename,
    i.FILEREALPATH AS file_real_path,
    i.ISZIP AS is_zip,
    i.ISENCRYPT AS is_encrypt,
    i.ISAESENCRYPT AS is_aes_encrypt,
    i.FILESIZE AS file_size
FROM {tables["form"]} f
JOIN {tables["request"]} r
  ON r.REQUESTID = f.requestid
LEFT JOIN {tables["docdetail"]} d
  ON (
    FIND_IN_SET(CONCAT(d.ID, ''), REPLACE(f.ycxsxkz, ' ', '')) > 0
    OR FIND_IN_SET(CONCAT(d.ID, ''), REPLACE(f.yyzz, ' ', '')) > 0
  )
LEFT JOIN {tables["docimagefile"]} dif
  ON dif.DOCID = d.ID
LEFT JOIN {tables["imagefile"]} i
  ON i.IMAGEFILEID = dif.IMAGEFILEID
WHERE r.WORKFLOWID = {workflow_id}
  AND f.ycxsxkz IS NOT NULL
  AND TRIM(f.ycxsxkz) <> ''
  AND i.FILEREALPATH IS NOT NULL
  AND TRIM(i.FILEREALPATH) <> ''
  -- The yyzz field can include non-license supporting documents such as commitments.
  -- Exclude only those explicit commitment attachments from the business-license candidates.
  AND NOT (
    FIND_IN_SET(CONCAT(d.ID, ''), REPLACE(f.yyzz, ' ', '')) > 0
    AND (
      INSTR(IFNULL(d.DOCSUBJECT, ''), '承诺函') > 0
      OR INSTR(IFNULL(dif.IMAGEFILENAME, ''), '承诺函') > 0
      OR INSTR(IFNULL(i.IMAGEFILENAME, ''), '承诺函') > 0
    )
  )
  AND {identity_predicate}
ORDER BY {order_by}{limit_clause}
""".strip()


def build_pending_stores_sql(
    *,
    page: int = 1,
    page_size: int = 20,
    tables: Mapping[str, str] | None = None,
) -> str:
    safe_page = max(1, int(page))
    safe_page_size = max(1, min(int(page_size), 100))
    offset = (safe_page - 1) * safe_page_size
    return f"""
SELECT
    store_code,
    store_name,
    requestid,
    request_name,
    summary_title,
    content_summary,
    submit_time
FROM (
    SELECT
        f.mdbm AS store_code,
        f.mdmc AS store_name,
        f.requestid,
        r.REQUESTNAME AS request_name,
        f.qsbt AS summary_title,
        f.nrgk AS content_summary,
        CAST(CONCAT(r.CREATEDATE, ' ', r.CREATETIME) AS CHAR) AS submit_time,
        ROW_NUMBER() OVER (
            PARTITION BY COALESCE(NULLIF(f.mdbm, ''), f.mdmc)
            ORDER BY r.CREATEDATE DESC, r.CREATETIME DESC, f.id DESC
        ) AS latest_row_num
    FROM {((tables or STARROCKS_TOBACCO_SOURCE_TABLES)["form"])} f
    JOIN {((tables or STARROCKS_TOBACCO_SOURCE_TABLES)["request"])} r
      ON r.REQUESTID = f.requestid
    WHERE r.WORKFLOWID = 614
      AND f.ycxsxkz IS NOT NULL
      AND TRIM(f.ycxsxkz) <> ''
      AND r.CREATEDATE IS NOT NULL
) pending
WHERE latest_row_num = 1
ORDER BY submit_time DESC
LIMIT {offset}, {safe_page_size}
""".strip()


def fetch_pending_stores(
    sql_client: SqlFetchClient,
    *,
    sql: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[dict[str, object]]:
    rows = sql_client.fetch_all(
        sql
        or build_pending_stores_sql(
            page=page,
            page_size=page_size,
            tables=_source_tables(sql_client),
        )
    )
    return [
        {
            "store_code": str(row.get("store_code") or ""),
            "store_name": str(row.get("store_name") or ""),
            "requestid": row.get("requestid"),
            "submit_date": str(row.get("submit_time") or "")[:10],
            "request_name": str(row.get("request_name") or ""),
            "summary_title": str(row.get("summary_title") or ""),
            "content_summary": str(row.get("content_summary") or ""),
        }
        for row in rows
        if row.get("store_code") or row.get("store_name")
    ]


def fetch_latest_tobacco_license_source_files(
    sql_client: SqlFetchClient,
    store_identifier: str,
    *,
    sql: str | None = None,
) -> list[TobaccoLicenseSourceFile]:
    rows = sql_client.fetch_all(
        sql
        or build_tobacco_license_source_sql(
            store_identifier,
            tables=_source_tables(sql_client),
        )
    )
    files = [_to_source_file(row) for row in rows]
    files = [source_file for source_file in files if source_file.file_real_path.strip()]
    if not files:
        return []

    first = files[0]
    return [
        source_file
        for source_file in files
        if source_file.form_id == first.form_id
        and source_file.requestid == first.requestid
    ]


def fetch_tobacco_license_source_files_by_request(
    sql_client: SqlFetchClient,
    requestid: int,
    *,
    workflow_id: int = 614,
    sql: str | None = None,
) -> list[TobaccoLicenseSourceFile]:
    safe_requestid = _required_positive_int(requestid, "requestid")
    safe_workflow_id = _required_positive_int(workflow_id, "workflow_id")
    rows = sql_client.fetch_all(
        sql
        or build_tobacco_license_source_by_request_sql(
            safe_requestid,
            workflow_id=safe_workflow_id,
            tables=_source_tables(sql_client),
        )
    )
    return [
        source_file
        for source_file in (_to_source_file(row) for row in rows)
        if source_file.file_real_path.strip()
        and source_file.requestid == safe_requestid
        and source_file.workflow_id == safe_workflow_id
    ]


def fetch_latest_oa_review_submission(
    sql_client: SqlFetchClient,
    requestid: int,
    *,
    workflow_id: int = 614,
) -> OaReviewSubmissionIdentity | None:
    tables = _source_tables(sql_client)
    rows = sql_client.fetch_all(
        build_oa_review_submission_sql(
            requestid,
            workflow_id=workflow_id,
            table=tables.get("requestlog", "workflow_requestlog"),
        )
    )
    if not rows:
        return None
    return OaReviewSubmissionIdentity.model_validate(rows[0])


def _to_source_file(row: dict[str, Any]) -> TobaccoLicenseSourceFile:
    return TobaccoLicenseSourceFile(
        form_id=_int_or_none(row.get("form_id")),
        requestid=_int_or_none(row.get("requestid")),
        store_name=_text_or_none(row.get("store_name")),
        store_code=_text_or_none(row.get("store_code")),
        summary_title=_text_or_none(row.get("summary_title")),
        content_summary=_text_or_none(row.get("content_summary")),
        tobacco_license_docids=_text_or_none(row.get("tobacco_license_docids")),
        business_license_docids=_text_or_none(row.get("business_license_docids")),
        document_role=_text_or_none(row.get("document_role")) or "tobacco_license",
        valid_from=_text_or_none(row.get("valid_from")),
        valid_to=_text_or_none(row.get("valid_to")),
        mdms=_int_or_none(row.get("mdms")),
        mdms1=_int_or_none(row.get("mdms1")),
        workflow_id=_int_or_none(row.get("workflow_id")),
        request_name=_text_or_none(row.get("request_name")),
        created_date=_text_or_none(row.get("created_date")),
        created_time=_text_or_none(row.get("created_time")),
        request_status=_text_or_none(row.get("request_status")),
        docid=_int_or_none(row.get("docid")),
        doc_subject=_text_or_none(row.get("doc_subject")),
        imagefile_id=_int_or_none(row.get("imagefile_id")),
        docimage_filename=_text_or_none(row.get("docimage_filename")),
        real_filename=_text_or_none(row.get("real_filename")),
        file_real_path=_required_text(row.get("file_real_path"), "file_real_path"),
        is_zip=_text_or_none(row.get("is_zip")),
        is_encrypt=_text_or_none(row.get("is_encrypt")),
        is_aes_encrypt=_int_or_none(row.get("is_aes_encrypt")),
        file_size=_text_or_none(row.get("file_size")),
    )


def _sql_string_literal(value: str) -> str:
    text = _required_text(value, "value")
    return "'" + text.replace("\\", "\\\\").replace("'", "''") + "'"


def _required_text(value: Any, field_name: str) -> str:
    text = _text_or_none(value)
    if text is None:
        raise TobaccoLicenseSourceTaskError(
            "TOBACCO_LICENSE_SOURCE_FIELD_EMPTY",
            f"{field_name} 不能为空",
        )
    return text


def _text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _required_positive_int(value: Any, field_name: str) -> int:
    parsed = _int_or_none(value)
    if parsed is None or parsed <= 0:
        raise TobaccoLicenseSourceTaskError(
            "TOBACCO_LICENSE_SOURCE_FIELD_INVALID",
            f"{field_name} 必须为正整数",
        )
    return parsed
