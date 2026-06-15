from json import dumps, loads
from typing import Any

import pymysql

from app.integrations.mysql_client import MySqlSettings, mysql_settings_from_env
from app.models import ReviewResult


BUSINESS_LICENSE_REVIEW_ROW_COLUMNS = """
    task_id,
    source_record_id,
    source_attachment_ref_id,
    source_url,
    tenant,
    document_type,
    business_name,
    credit_code,
    business_address,
    legal_person,
    valid_from,
    valid_to,
    issue_authority,
    issue_date,
    review_status,
    risk_level,
    needs_manual_review,
    summary,
    created_at,
    updated_at
"""


class MySQLReviewResultRepository:
    def __init__(self, settings: MySqlSettings) -> None:
        self.settings = settings
        self._schema_ready = False

    def save(self, review_result: ReviewResult) -> None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO review_results (task_id, payload_json, created_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        payload_json = VALUES(payload_json),
                        created_at = VALUES(created_at)
                    """,
                    (
                        review_result.task_id,
                        review_result.model_dump_json(),
                        review_result.created_at.isoformat(),
                    ),
                )
                self._save_business_license_projection(cursor, review_result)
                self._save_product_report_projection(cursor, review_result)
            connection.commit()

    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload_json FROM review_results WHERE task_id = %s",
                    (task_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        return ReviewResult.model_validate_json(row["payload_json"])

    def get_business_license_snapshot(self, task_id: str) -> dict | None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM business_license_reviews
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        snapshot = dict(row)
        snapshot["needs_manual_review"] = bool(snapshot["needs_manual_review"])
        snapshot["rule_results"] = loads(snapshot["rule_results_json"])
        snapshot["extracted_fields"] = loads(snapshot["extracted_fields_json"])
        snapshot["normalized_fields"] = loads(snapshot["normalized_fields_json"])
        snapshot["extraction_metadata"] = loads(snapshot["extraction_metadata_json"])
        snapshot["source_evidence"] = loads(snapshot["source_evidence_json"])
        return snapshot

    def list_business_license_reviews(
        self,
        *,
        business_name: str | None = None,
        credit_code: str | None = None,
        risk_level: str | None = None,
        review_status: str | None = None,
        needs_manual_review: bool | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        self._ensure_schema_once()
        where_sql, params = _business_license_review_filters(
            business_name=business_name,
            credit_code=credit_code,
            risk_level=risk_level,
            review_status=review_status,
            needs_manual_review=needs_manual_review,
            created_from=created_from,
            created_to=created_to,
        )
        safe_page_size = min(max(1, page_size), 100)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS total
                    FROM business_license_reviews
                    {where_sql}
                    """,
                    tuple(params),
                )
                total = int((cursor.fetchone() or {}).get("total") or 0)
                total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
                safe_page = min(max(1, page), total_pages)
                offset = (safe_page - 1) * safe_page_size
                cursor.execute(
                    f"""
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN DATE(created_at) = CURDATE() THEN 1 ELSE 0 END) AS today_reviewed,
                        SUM(CASE WHEN needs_manual_review = 1 THEN 1 ELSE 0 END) AS pending_manual_review,
                        SUM(CASE WHEN risk_level = 'HIGH' THEN 1 ELSE 0 END) AS high_risk,
                        SUM(CASE WHEN review_status = 'REVIEWED' THEN 1 ELSE 0 END) AS reviewed
                    FROM business_license_reviews
                    {where_sql}
                    """,
                    tuple(params),
                )
                metrics_row = cursor.fetchone() or {}
                cursor.execute(
                    f"""
                    SELECT {BUSINESS_LICENSE_REVIEW_ROW_COLUMNS}
                    FROM business_license_reviews
                    {where_sql}
                    ORDER BY created_at DESC, task_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params + [safe_page_size, offset]),
                )
                rows = cursor.fetchall()
        return {
            "items": [_business_license_review_row(row) for row in rows],
            "metrics": _business_license_review_metrics(metrics_row),
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_product_report_snapshot(self, task_id: str) -> dict | None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM product_report_reviews
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                cursor.execute(
                    """
                    SELECT item_index, item_name, item_result, item_payload_json
                    FROM product_report_inspection_items
                    WHERE task_id = %s
                    ORDER BY item_index ASC
                    """,
                    (task_id,),
                )
                item_rows = cursor.fetchall()
        snapshot = dict(row)
        snapshot["needs_manual_review"] = bool(snapshot["needs_manual_review"])
        snapshot["rule_results"] = loads(snapshot["rule_results_json"])
        snapshot["extraction_metadata"] = loads(snapshot["extraction_metadata_json"])
        snapshot["source_evidence"] = loads(snapshot["source_evidence_json"])
        snapshot["inspection_items"] = [
            (
                loads(item_row["item_payload_json"])
                if item_row["item_payload_json"]
                else {
                    "name": item_row["item_name"],
                    "result": item_row["item_result"],
                }
            )
            for item_row in item_rows
        ]
        return snapshot

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_results (
                        task_id VARCHAR(128) PRIMARY KEY,
                        payload_json JSON NOT NULL,
                        created_at VARCHAR(64)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS business_license_reviews (
                        task_id VARCHAR(128) PRIMARY KEY,
                        source_record_id VARCHAR(255),
                        source_attachment_ref_id VARCHAR(255),
                        source_url TEXT,
                        tenant VARCHAR(128),
                        document_type VARCHAR(64) NOT NULL,
                        business_name VARCHAR(512),
                        credit_code VARCHAR(64),
                        business_address TEXT,
                        legal_person VARCHAR(255),
                        valid_from VARCHAR(64),
                        valid_to VARCHAR(64),
                        issue_authority VARCHAR(512),
                        issue_date VARCHAR(64),
                        review_status VARCHAR(64) NOT NULL,
                        risk_level VARCHAR(64) NOT NULL,
                        needs_manual_review TINYINT NOT NULL,
                        summary TEXT NOT NULL,
                        rule_results_json JSON NOT NULL,
                        extracted_fields_json JSON NOT NULL,
                        normalized_fields_json JSON NOT NULL,
                        extraction_metadata_json JSON NOT NULL,
                        source_evidence_json JSON NOT NULL,
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_business_license_source_record_id (source_record_id),
                        INDEX idx_business_license_credit_code (credit_code),
                        INDEX idx_business_license_status_risk (review_status, risk_level),
                        INDEX idx_business_license_created_at (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS product_report_reviews (
                        task_id VARCHAR(128) PRIMARY KEY,
                        source_record_id VARCHAR(255),
                        source_attachment_ref_id VARCHAR(255),
                        tenant VARCHAR(128),
                        document_type VARCHAR(64) NOT NULL,
                        product_name VARCHAR(512),
                        sample_name VARCHAR(512),
                        vendor_name VARCHAR(512),
                        vendor_name_extracted VARCHAR(512),
                        entrusting_party VARCHAR(512),
                        manufacturer_name VARCHAR(512),
                        batch_no VARCHAR(255),
                        production_date VARCHAR(64),
                        issue_date VARCHAR(64),
                        sign_date VARCHAR(64),
                        inspection_conclusion TEXT,
                        inspection_result TEXT,
                        review_status VARCHAR(64) NOT NULL,
                        risk_level VARCHAR(64) NOT NULL,
                        needs_manual_review TINYINT NOT NULL,
                        summary TEXT NOT NULL,
                        rule_results_json JSON NOT NULL,
                        extraction_metadata_json JSON NOT NULL,
                        source_evidence_json JSON NOT NULL,
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_product_report_source_record_id (source_record_id),
                        INDEX idx_product_report_status_risk (review_status, risk_level),
                        INDEX idx_product_report_created_at (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS product_report_inspection_items (
                        task_id VARCHAR(128) NOT NULL,
                        item_index INT NOT NULL,
                        item_name VARCHAR(512),
                        item_result TEXT,
                        item_payload_json JSON NOT NULL,
                        PRIMARY KEY (task_id, item_index)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            connection.commit()

    def _ensure_schema_once(self) -> None:
        if self._schema_ready:
            return
        self._ensure_schema()
        self._schema_ready = True

    def _connect(self):
        return pymysql.connect(
            host=self.settings.host,
            port=self.settings.port,
            user=self.settings.user,
            password=self.settings.password,
            database=self.settings.database,
            charset=self.settings.charset,
            connect_timeout=self.settings.connect_timeout,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def _save_business_license_projection(self, cursor, review_result: ReviewResult) -> None:
        if review_result.document_type != "business_license":
            return

        projection = _business_license_projection(review_result)
        cursor.execute(
            """
            INSERT INTO business_license_reviews (
                task_id,
                source_record_id,
                source_attachment_ref_id,
                source_url,
                tenant,
                document_type,
                business_name,
                credit_code,
                business_address,
                legal_person,
                valid_from,
                valid_to,
                issue_authority,
                issue_date,
                review_status,
                risk_level,
                needs_manual_review,
                summary,
                rule_results_json,
                extracted_fields_json,
                normalized_fields_json,
                extraction_metadata_json,
                source_evidence_json,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_record_id = VALUES(source_record_id),
                source_attachment_ref_id = VALUES(source_attachment_ref_id),
                source_url = VALUES(source_url),
                tenant = VALUES(tenant),
                document_type = VALUES(document_type),
                business_name = VALUES(business_name),
                credit_code = VALUES(credit_code),
                business_address = VALUES(business_address),
                legal_person = VALUES(legal_person),
                valid_from = VALUES(valid_from),
                valid_to = VALUES(valid_to),
                issue_authority = VALUES(issue_authority),
                issue_date = VALUES(issue_date),
                review_status = VALUES(review_status),
                risk_level = VALUES(risk_level),
                needs_manual_review = VALUES(needs_manual_review),
                summary = VALUES(summary),
                rule_results_json = VALUES(rule_results_json),
                extracted_fields_json = VALUES(extracted_fields_json),
                normalized_fields_json = VALUES(normalized_fields_json),
                extraction_metadata_json = VALUES(extraction_metadata_json),
                source_evidence_json = VALUES(source_evidence_json),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            _business_license_projection_values(projection),
        )

    def _save_product_report_projection(self, cursor, review_result: ReviewResult) -> None:
        if review_result.document_type != "product_report":
            return

        projection = _product_report_projection(review_result)
        cursor.execute(
            """
            INSERT INTO product_report_reviews (
                task_id,
                source_record_id,
                source_attachment_ref_id,
                tenant,
                document_type,
                product_name,
                sample_name,
                vendor_name,
                vendor_name_extracted,
                entrusting_party,
                manufacturer_name,
                batch_no,
                production_date,
                issue_date,
                sign_date,
                inspection_conclusion,
                inspection_result,
                review_status,
                risk_level,
                needs_manual_review,
                summary,
                rule_results_json,
                extraction_metadata_json,
                source_evidence_json,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_record_id = VALUES(source_record_id),
                source_attachment_ref_id = VALUES(source_attachment_ref_id),
                tenant = VALUES(tenant),
                document_type = VALUES(document_type),
                product_name = VALUES(product_name),
                sample_name = VALUES(sample_name),
                vendor_name = VALUES(vendor_name),
                vendor_name_extracted = VALUES(vendor_name_extracted),
                entrusting_party = VALUES(entrusting_party),
                manufacturer_name = VALUES(manufacturer_name),
                batch_no = VALUES(batch_no),
                production_date = VALUES(production_date),
                issue_date = VALUES(issue_date),
                sign_date = VALUES(sign_date),
                inspection_conclusion = VALUES(inspection_conclusion),
                inspection_result = VALUES(inspection_result),
                review_status = VALUES(review_status),
                risk_level = VALUES(risk_level),
                needs_manual_review = VALUES(needs_manual_review),
                summary = VALUES(summary),
                rule_results_json = VALUES(rule_results_json),
                extraction_metadata_json = VALUES(extraction_metadata_json),
                source_evidence_json = VALUES(source_evidence_json),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            _product_report_projection_values(projection),
        )
        cursor.execute(
            "DELETE FROM product_report_inspection_items WHERE task_id = %s",
            (review_result.task_id,),
        )
        for index, item in enumerate(projection["inspection_items"]):
            payload = dict(item) if isinstance(item, dict) else {"value": item}
            cursor.execute(
                """
                INSERT INTO product_report_inspection_items (
                    task_id,
                    item_index,
                    item_name,
                    item_result,
                    item_payload_json
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    review_result.task_id,
                    index,
                    payload.get("name"),
                    payload.get("result"),
                    dumps(payload, ensure_ascii=False),
                ),
            )


def build_review_result_repository_from_env() -> MySQLReviewResultRepository:
    return MySQLReviewResultRepository(mysql_settings_from_env("REVIEW_RESULT_MYSQL"))


def _business_license_review_filters(
    *,
    business_name: str | None,
    credit_code: str | None,
    risk_level: str | None,
    review_status: str | None,
    needs_manual_review: bool | None,
    created_from: str | None,
    created_to: str | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if business_name:
        clauses.append("business_name LIKE %s")
        params.append(f"%{business_name}%")
    if credit_code:
        clauses.append("credit_code LIKE %s")
        params.append(f"%{credit_code.upper()}%")
    if risk_level:
        clauses.append("risk_level = %s")
        params.append(risk_level)
    if review_status:
        clauses.append("review_status = %s")
        params.append(review_status)
    if needs_manual_review is not None:
        clauses.append("needs_manual_review = %s")
        params.append(1 if needs_manual_review else 0)
    if created_from:
        clauses.append("created_at >= %s")
        params.append(_created_from_boundary(created_from))
    if created_to:
        clauses.append("created_at <= %s")
        params.append(_created_to_boundary(created_to))
    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def _created_from_boundary(value: str) -> str:
    if _is_date_only(value):
        return f"{value}T00:00:00"
    return value


def _created_to_boundary(value: str) -> str:
    if _is_date_only(value):
        return f"{value}T23:59:59.999999"
    return value


def _is_date_only(value: str) -> bool:
    if len(value) != 10:
        return False
    year, month, day = value.split("-")
    return year.isdigit() and month.isdigit() and day.isdigit()


def _business_license_review_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["needs_manual_review"] = bool(item["needs_manual_review"])
    item["review_status_label"] = _review_status_label(item["review_status"])
    item["risk_level_label"] = _risk_level_label(item["risk_level"])
    return item


def _business_license_review_metrics(row: dict[str, Any]) -> dict[str, int]:
    total = int(row.get("total") or 0)
    reviewed = int(row.get("reviewed") or 0)
    return {
        "today_reviewed": int(row.get("today_reviewed") or 0),
        "pending_manual_review": int(row.get("pending_manual_review") or 0),
        "high_risk": int(row.get("high_risk") or 0),
        "pass_rate": 0 if total == 0 else round((reviewed / total) * 100),
    }


def _review_status_label(status: str) -> str:
    return {
        "CREATED": "已创建",
        "RUNNING": "审核中",
        "REVIEWED": "已审核",
        "PENDING_MANUAL_REVIEW": "待人工复核",
        "MANUAL_REVIEWED": "人工已复核",
        "FAILED": "审核失败",
    }.get(status, status)


def _risk_level_label(risk_level: str) -> str:
    return {
        "NONE": "无风险",
        "LOW": "低风险",
        "MEDIUM": "中风险",
        "HIGH": "高风险",
    }.get(risk_level, risk_level)


def _skill_result_dict(review_result: ReviewResult) -> dict[str, Any]:
    return (
        review_result.skill_result
        if isinstance(review_result.skill_result, dict)
        else review_result.skill_result.model_dump(mode="json")
    )


def _rule_results_json(review_result: ReviewResult) -> str:
    return dumps(review_result.model_dump(mode="json")["rule_results"], ensure_ascii=False)


def _business_license_projection(review_result: ReviewResult) -> dict[str, Any]:
    skill_result = _skill_result_dict(review_result)
    extracted_fields = dict(skill_result.get("extracted_fields") or {})
    normalized_fields = dict(skill_result.get("normalized_fields") or {})
    extraction_metadata = dict(skill_result.get("extraction_metadata") or {})
    source_evidence = dict(skill_result.get("source_evidence") or {})
    source = dict(source_evidence.get("source") or {})
    document_input = dict(skill_result.get("document_input") or {})
    return {
        "task_id": review_result.task_id,
        "source_record_id": source.get("record_id"),
        "source_attachment_ref_id": source.get("attachment_ref_id"),
        "source_url": document_input.get("source_url"),
        "tenant": source.get("tenant"),
        "document_type": review_result.document_type,
        "business_name": extracted_fields.get("subject_name"),
        "credit_code": extracted_fields.get("credit_code"),
        "business_address": extracted_fields.get("business_address"),
        "legal_person": extracted_fields.get("legal_person"),
        "valid_from": extracted_fields.get("valid_from"),
        "valid_to": extracted_fields.get("valid_to"),
        "issue_authority": extracted_fields.get("issue_authority"),
        "issue_date": extracted_fields.get("issue_date"),
        "review_status": review_result.status.value,
        "risk_level": review_result.risk_level.value,
        "needs_manual_review": int(review_result.needs_manual_review),
        "summary": review_result.summary,
        "rule_results_json": _rule_results_json(review_result),
        "extracted_fields_json": dumps(extracted_fields, ensure_ascii=False),
        "normalized_fields_json": dumps(normalized_fields, ensure_ascii=False),
        "extraction_metadata_json": dumps(extraction_metadata, ensure_ascii=False),
        "source_evidence_json": dumps(source_evidence, ensure_ascii=False),
        "created_at": review_result.created_at.isoformat(),
        "updated_at": review_result.updated_at.isoformat(),
    }


def _business_license_projection_values(projection: dict[str, Any]) -> tuple[Any, ...]:
    return (
        projection["task_id"],
        projection["source_record_id"],
        projection["source_attachment_ref_id"],
        projection["source_url"],
        projection["tenant"],
        projection["document_type"],
        projection["business_name"],
        projection["credit_code"],
        projection["business_address"],
        projection["legal_person"],
        projection["valid_from"],
        projection["valid_to"],
        projection["issue_authority"],
        projection["issue_date"],
        projection["review_status"],
        projection["risk_level"],
        projection["needs_manual_review"],
        projection["summary"],
        projection["rule_results_json"],
        projection["extracted_fields_json"],
        projection["normalized_fields_json"],
        projection["extraction_metadata_json"],
        projection["source_evidence_json"],
        projection["created_at"],
        projection["updated_at"],
    )


def _product_report_projection(review_result: ReviewResult) -> dict[str, Any]:
    skill_result = _skill_result_dict(review_result)
    extracted_fields = dict(skill_result.get("extracted_fields") or {})
    extraction_metadata = dict(skill_result.get("extraction_metadata") or {})
    source_evidence = dict(skill_result.get("source_evidence") or {})
    source = dict(source_evidence.get("source") or {})
    return {
        "task_id": review_result.task_id,
        "source_record_id": source.get("record_id"),
        "source_attachment_ref_id": source.get("attachment_ref_id"),
        "tenant": source.get("tenant"),
        "document_type": review_result.document_type,
        "product_name": extracted_fields.get("product_name"),
        "sample_name": extracted_fields.get("sample_name"),
        "vendor_name": source_evidence.get("supplier_name"),
        "vendor_name_extracted": extracted_fields.get("vendor_name_extracted"),
        "entrusting_party": extracted_fields.get("entrusting_party"),
        "manufacturer_name": extracted_fields.get("manufacturer_name"),
        "batch_no": extracted_fields.get("batch_no"),
        "production_date": extracted_fields.get("production_date"),
        "issue_date": extracted_fields.get("issue_date"),
        "sign_date": extracted_fields.get("sign_date"),
        "inspection_conclusion": extracted_fields.get("inspection_conclusion"),
        "inspection_result": extracted_fields.get("inspection_result"),
        "review_status": review_result.status.value,
        "risk_level": review_result.risk_level.value,
        "needs_manual_review": int(review_result.needs_manual_review),
        "summary": review_result.summary,
        "rule_results_json": _rule_results_json(review_result),
        "extraction_metadata_json": dumps(extraction_metadata, ensure_ascii=False),
        "source_evidence_json": dumps(source_evidence, ensure_ascii=False),
        "created_at": review_result.created_at.isoformat(),
        "updated_at": review_result.updated_at.isoformat(),
        "inspection_items": list(extracted_fields.get("inspection_items") or []),
    }


def _product_report_projection_values(projection: dict[str, Any]) -> tuple[Any, ...]:
    return (
        projection["task_id"],
        projection["source_record_id"],
        projection["source_attachment_ref_id"],
        projection["tenant"],
        projection["document_type"],
        projection["product_name"],
        projection["sample_name"],
        projection["vendor_name"],
        projection["vendor_name_extracted"],
        projection["entrusting_party"],
        projection["manufacturer_name"],
        projection["batch_no"],
        projection["production_date"],
        projection["issue_date"],
        projection["sign_date"],
        projection["inspection_conclusion"],
        projection["inspection_result"],
        projection["review_status"],
        projection["risk_level"],
        projection["needs_manual_review"],
        projection["summary"],
        projection["rule_results_json"],
        projection["extraction_metadata_json"],
        projection["source_evidence_json"],
        projection["created_at"],
        projection["updated_at"],
    )
