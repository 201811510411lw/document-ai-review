class StubMySQLCursor:
    def __init__(self, storage):
        self.storage = storage
        self.result = None

    def execute(self, sql, params=None):
        compact = " ".join(sql.split()).lower()
        params = params or ()
        self.storage["executed_sql"].append(sql)
        if compact.startswith("create table"):
            return
        if compact.startswith("insert into review_results"):
            self.storage["review_results"][params[0]] = {
                "task_id": params[0],
                "payload_json": params[1],
                "created_at": params[2],
            }
            return
        if compact.startswith("select payload_json from review_results"):
            self.result = self.storage["review_results"].get(params[0])
            return
        if compact.startswith("insert into business_license_reviews"):
            keys = [
                "task_id",
                "source_record_id",
                "source_attachment_ref_id",
                "source_url",
                "tenant",
                "document_type",
                "business_name",
                "credit_code",
                "business_address",
                "legal_person",
                "valid_from",
                "valid_to",
                "issue_authority",
                "issue_date",
                "review_status",
                "risk_level",
                "needs_manual_review",
                "summary",
                "rule_results_json",
                "extracted_fields_json",
                "normalized_fields_json",
                "extraction_metadata_json",
                "source_evidence_json",
                "created_at",
                "updated_at",
            ]
            self.storage["business_license_reviews"][params[0]] = dict(zip(keys, params))
            return
        if compact.startswith("select * from business_license_reviews"):
            self.result = self.storage["business_license_reviews"].get(params[0])
            return
        if compact.startswith("select count(*) as total from business_license_reviews"):
            rows = _filter_business_license_rows(self.storage, params)
            self.result = {"total": len(rows)}
            return
        if compact.startswith("select count(*) as total, sum(case when date(created_at)"):
            rows = _filter_business_license_rows(self.storage, params)
            self.result = {
                "total": len(rows),
                "today_reviewed": sum(
                    1 for row in rows if str(row.get("created_at", "")).startswith("2026-06-15")
                ),
                "pending_manual_review": sum(
                    1 for row in rows if int(row.get("needs_manual_review") or 0) == 1
                ),
                "high_risk": sum(1 for row in rows if row.get("risk_level") == "HIGH"),
                "reviewed": sum(1 for row in rows if row.get("review_status") == "REVIEWED"),
            }
            return
        if compact.startswith("select task_id, source_record_id"):
            rows = _filter_business_license_rows(self.storage, params[:-2])
            rows = sorted(
                rows,
                key=lambda row: (row.get("created_at") or "", row.get("task_id") or ""),
                reverse=True,
            )
            limit = int(params[-2])
            offset = int(params[-1])
            self.result = rows[offset : offset + limit]
            return
        if compact.startswith("insert into product_report_reviews"):
            keys = [
                "task_id",
                "source_record_id",
                "source_attachment_ref_id",
                "tenant",
                "document_type",
                "product_name",
                "sample_name",
                "vendor_name",
                "vendor_name_extracted",
                "entrusting_party",
                "manufacturer_name",
                "batch_no",
                "production_date",
                "issue_date",
                "sign_date",
                "inspection_conclusion",
                "inspection_result",
                "review_status",
                "risk_level",
                "needs_manual_review",
                "summary",
                "rule_results_json",
                "extraction_metadata_json",
                "source_evidence_json",
                "created_at",
                "updated_at",
            ]
            self.storage["product_report_reviews"][params[0]] = dict(zip(keys, params))
            return
        if compact.startswith("delete from product_report_inspection_items"):
            self.storage["product_report_inspection_items"][params[0]] = []
            return
        if compact.startswith("insert into product_report_inspection_items"):
            task_id = params[0]
            self.storage["product_report_inspection_items"].setdefault(task_id, []).append(
                {
                    "task_id": task_id,
                    "item_index": params[1],
                    "item_name": params[2],
                    "item_result": params[3],
                    "item_payload_json": params[4],
                }
            )
            return
        if compact.startswith("select * from product_report_reviews"):
            self.result = self.storage["product_report_reviews"].get(params[0])
            return
        if compact.startswith("select item_index, item_name, item_result, item_payload_json"):
            self.result = sorted(
                self.storage["product_report_inspection_items"].get(params[0], []),
                key=lambda row: row["item_index"],
            )
            return
        raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.result or []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class StubMySQLConnection:
    def __init__(self, storage):
        self.storage = storage
        self.closed = False
        self.commits = 0

    def cursor(self):
        return StubMySQLCursor(self.storage)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


def install_mysql_repository_stub(monkeypatch):
    storage = {
        "executed_sql": [],
        "review_results": {},
        "business_license_reviews": {},
        "product_report_reviews": {},
        "product_report_inspection_items": {},
        "connections": [],
    }

    def connect(**kwargs):
        storage["connect_kwargs"] = kwargs
        connection = StubMySQLConnection(storage)
        storage["connections"].append(connection)
        return connection

    monkeypatch.setattr("app.repositories.review_result_repository.pymysql.connect", connect)
    return storage


def _filter_business_license_rows(storage, params):
    rows = list(storage["business_license_reviews"].values())
    if not params:
        return rows

    sql = " ".join(storage["executed_sql"][-1].split()).lower()
    param_index = 0
    if "business_name like %s" in sql:
        expected = str(params[param_index]).strip("%")
        rows = [row for row in rows if expected in str(row.get("business_name") or "")]
        param_index += 1
    if "credit_code like %s" in sql:
        expected = str(params[param_index]).strip("%").upper()
        rows = [row for row in rows if expected in str(row.get("credit_code") or "").upper()]
        param_index += 1
    if "risk_level = %s" in sql:
        expected = params[param_index]
        rows = [row for row in rows if row.get("risk_level") == expected]
        param_index += 1
    if "review_status = %s" in sql:
        expected = params[param_index]
        rows = [row for row in rows if row.get("review_status") == expected]
        param_index += 1
    if "needs_manual_review = %s" in sql:
        expected = int(params[param_index])
        rows = [row for row in rows if int(row.get("needs_manual_review") or 0) == expected]
        param_index += 1
    if "created_at >= %s" in sql:
        expected = params[param_index]
        rows = [row for row in rows if str(row.get("created_at") or "") >= expected]
        param_index += 1
    if "created_at <= %s" in sql:
        expected = params[param_index]
        rows = [row for row in rows if str(row.get("created_at") or "") <= expected]
    return rows
