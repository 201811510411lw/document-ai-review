from typing import Any, Protocol

from pydantic import BaseModel


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
    valid_from: str | None = None
    valid_to: str | None = None
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


class TobaccoLicenseSourceTaskError(ValueError):
    def __init__(self, code: str, message: str, *, store_identifier: str | None = None):
        self.code = code
        self.store_identifier = store_identifier
        super().__init__(message)


def build_tobacco_license_source_sql(store_identifier: str, *, limit: int = 50) -> str:
    store_identifier = _required_text(store_identifier, "store_identifier")
    safe_limit = max(1, min(int(limit), 200))
    store_literal = _sql_string_literal(store_identifier)
    return f"""
SELECT
    f.id AS form_id,
    f.requestid,
    f.mdmc AS store_name,
    f.mdbm AS store_code,
    f.qsbt AS summary_title,
    f.nrgk AS content_summary,
    f.ycxsxkz AS tobacco_license_docids,
    f.yczyxqksrq AS valid_from,
    f.yczyxqjsrq AS valid_to,
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
FROM ods_oa_ecology_formtable_main_283_df f
JOIN ods_oa_ecology_workflow_requestbase_df r
  ON r.REQUESTID = f.requestid
LEFT JOIN ods_oa_ecology_docdetail_df d
  ON FIND_IN_SET(CAST(d.ID AS VARCHAR), REPLACE(f.ycxsxkz, ' ', '')) > 0
LEFT JOIN ods_oa_ecology_docimagefile_df dif
  ON dif.DOCID = d.ID
LEFT JOIN ods_oa_ecology_imagefile_df i
  ON i.IMAGEFILEID = dif.IMAGEFILEID
WHERE r.WORKFLOWID = 614
  AND f.ycxsxkz IS NOT NULL
  AND TRIM(f.ycxsxkz) <> ''
  AND i.FILEREALPATH IS NOT NULL
  AND TRIM(i.FILEREALPATH) <> ''
  AND (
    f.mdbm = {store_literal}
    OR f.mdmc = {store_literal}
    OR INSTR(IFNULL(f.qsbt, ''), {store_literal}) > 0
    OR INSTR(IFNULL(f.nrgk, ''), {store_literal}) > 0
    OR INSTR(IFNULL(r.REQUESTNAME, ''), {store_literal}) > 0
  )
ORDER BY r.CREATEDATE DESC, r.CREATETIME DESC, f.id DESC, d.ID, dif.IMAGEFILEID
LIMIT {safe_limit}
""".strip()


def fetch_latest_tobacco_license_source_files(
    sql_client: SqlFetchClient,
    store_identifier: str,
    *,
    sql: str | None = None,
) -> list[TobaccoLicenseSourceFile]:
    rows = sql_client.fetch_all(sql or build_tobacco_license_source_sql(store_identifier))
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


def _to_source_file(row: dict[str, Any]) -> TobaccoLicenseSourceFile:
    return TobaccoLicenseSourceFile(
        form_id=_int_or_none(row.get("form_id")),
        requestid=_int_or_none(row.get("requestid")),
        store_name=_text_or_none(row.get("store_name")),
        store_code=_text_or_none(row.get("store_code")),
        summary_title=_text_or_none(row.get("summary_title")),
        content_summary=_text_or_none(row.get("content_summary")),
        tobacco_license_docids=_text_or_none(row.get("tobacco_license_docids")),
        valid_from=_text_or_none(row.get("valid_from")),
        valid_to=_text_or_none(row.get("valid_to")),
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
