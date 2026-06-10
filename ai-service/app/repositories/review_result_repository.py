import sqlite3
from json import dumps, loads
from pathlib import Path

from app.models import ReviewResult


class SQLiteReviewResultRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._ensure_schema()

    def save(self, review_result: ReviewResult) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO review_results (task_id, payload_json, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (
                    review_result.task_id,
                    review_result.model_dump_json(),
                    review_result.created_at.isoformat(),
                ),
            )
            self._save_product_report_projection(connection, review_result)
            self._save_business_license_projection(connection, review_result)

    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM review_results WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return ReviewResult.model_validate_json(row["payload_json"])

    def get_product_report_snapshot(self, task_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM product_report_reviews
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if row is None:
                return None
            item_rows = connection.execute(
                """
                SELECT item_index, item_name, item_result, item_payload_json
                FROM product_report_inspection_items
                WHERE task_id = ?
                ORDER BY item_index ASC
                """,
                (task_id,),
            ).fetchall()
        snapshot = dict(row)
        snapshot["needs_manual_review"] = bool(snapshot["needs_manual_review"])
        snapshot["rule_results"] = loads(snapshot["rule_results_json"])
        snapshot["extraction_metadata"] = loads(snapshot["extraction_metadata_json"])
        snapshot["source_evidence"] = loads(snapshot["source_evidence_json"])
        snapshot["inspection_items"] = [
            loads(item_row["item_payload_json"]) if item_row["item_payload_json"] else {
                "name": item_row["item_name"],
                "result": item_row["item_result"],
            }
            for item_row in item_rows
        ]
        return snapshot

    def get_business_license_snapshot(self, task_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT *
                FROM business_license_reviews
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
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

    def _ensure_schema(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_results (
                    task_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS product_report_reviews (
                    task_id TEXT PRIMARY KEY,
                    source_record_id TEXT,
                    source_attachment_ref_id TEXT,
                    tenant TEXT,
                    document_type TEXT NOT NULL,
                    product_name TEXT,
                    sample_name TEXT,
                    vendor_name TEXT,
                    vendor_name_extracted TEXT,
                    entrusting_party TEXT,
                    manufacturer_name TEXT,
                    batch_no TEXT,
                    production_date TEXT,
                    issue_date TEXT,
                    sign_date TEXT,
                    inspection_conclusion TEXT,
                    inspection_result TEXT,
                    review_status TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    needs_manual_review INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    rule_results_json TEXT NOT NULL,
                    extraction_metadata_json TEXT NOT NULL,
                    source_evidence_json TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS product_report_inspection_items (
                    task_id TEXT NOT NULL,
                    item_index INTEGER NOT NULL,
                    item_name TEXT,
                    item_result TEXT,
                    item_payload_json TEXT NOT NULL,
                    PRIMARY KEY (task_id, item_index)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS business_license_reviews (
                    task_id TEXT PRIMARY KEY,
                    source_record_id TEXT,
                    source_attachment_ref_id TEXT,
                    source_url TEXT,
                    tenant TEXT,
                    document_type TEXT NOT NULL,
                    business_name TEXT,
                    credit_code TEXT,
                    business_address TEXT,
                    legal_person TEXT,
                    valid_from TEXT,
                    valid_to TEXT,
                    issue_authority TEXT,
                    issue_date TEXT,
                    review_status TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    needs_manual_review INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    rule_results_json TEXT NOT NULL,
                    extracted_fields_json TEXT NOT NULL,
                    normalized_fields_json TEXT NOT NULL,
                    extraction_metadata_json TEXT NOT NULL,
                    source_evidence_json TEXT NOT NULL,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _save_product_report_projection(
        self,
        connection: sqlite3.Connection,
        review_result: ReviewResult,
    ) -> None:
        if review_result.document_type != "product_report":
            return

        skill_result = (
            review_result.skill_result
            if isinstance(review_result.skill_result, dict)
            else review_result.skill_result.model_dump(mode="json")
        )
        extracted_fields = dict(skill_result.get("extracted_fields") or {})
        extraction_metadata = dict(skill_result.get("extraction_metadata") or {})
        source_evidence = dict(skill_result.get("source_evidence") or {})
        source = dict(source_evidence.get("source") or {})
        inspection_items = list(extracted_fields.get("inspection_items") or [])

        connection.execute(
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                source_record_id = excluded.source_record_id,
                source_attachment_ref_id = excluded.source_attachment_ref_id,
                tenant = excluded.tenant,
                document_type = excluded.document_type,
                product_name = excluded.product_name,
                sample_name = excluded.sample_name,
                vendor_name = excluded.vendor_name,
                vendor_name_extracted = excluded.vendor_name_extracted,
                entrusting_party = excluded.entrusting_party,
                manufacturer_name = excluded.manufacturer_name,
                batch_no = excluded.batch_no,
                production_date = excluded.production_date,
                issue_date = excluded.issue_date,
                sign_date = excluded.sign_date,
                inspection_conclusion = excluded.inspection_conclusion,
                inspection_result = excluded.inspection_result,
                review_status = excluded.review_status,
                risk_level = excluded.risk_level,
                needs_manual_review = excluded.needs_manual_review,
                summary = excluded.summary,
                rule_results_json = excluded.rule_results_json,
                extraction_metadata_json = excluded.extraction_metadata_json,
                source_evidence_json = excluded.source_evidence_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                review_result.task_id,
                source.get("record_id"),
                source.get("attachment_ref_id"),
                source.get("tenant"),
                review_result.document_type,
                extracted_fields.get("product_name"),
                extracted_fields.get("sample_name"),
                source_evidence.get("supplier_name"),
                extracted_fields.get("vendor_name_extracted"),
                extracted_fields.get("entrusting_party"),
                extracted_fields.get("manufacturer_name"),
                extracted_fields.get("batch_no"),
                extracted_fields.get("production_date"),
                extracted_fields.get("issue_date"),
                extracted_fields.get("sign_date"),
                extracted_fields.get("inspection_conclusion"),
                extracted_fields.get("inspection_result"),
                review_result.status.value,
                review_result.risk_level.value,
                int(review_result.needs_manual_review),
                review_result.summary,
                dumps(review_result.model_dump(mode="json")["rule_results"], ensure_ascii=False),
                dumps(extraction_metadata, ensure_ascii=False),
                dumps(source_evidence, ensure_ascii=False),
                review_result.created_at.isoformat(),
                review_result.updated_at.isoformat(),
            ),
        )
        connection.execute(
            "DELETE FROM product_report_inspection_items WHERE task_id = ?",
            (review_result.task_id,),
        )
        for index, item in enumerate(inspection_items):
            payload = dict(item) if isinstance(item, dict) else {"value": item}
            connection.execute(
                """
                INSERT INTO product_report_inspection_items (
                    task_id,
                    item_index,
                    item_name,
                    item_result,
                    item_payload_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    review_result.task_id,
                    index,
                    payload.get("name"),
                    payload.get("result"),
                    dumps(payload, ensure_ascii=False),
                ),
            )

    def _save_business_license_projection(
        self,
        connection: sqlite3.Connection,
        review_result: ReviewResult,
    ) -> None:
        if review_result.document_type != "business_license":
            return

        skill_result = (
            review_result.skill_result
            if isinstance(review_result.skill_result, dict)
            else review_result.skill_result.model_dump(mode="json")
        )
        extracted_fields = dict(skill_result.get("extracted_fields") or {})
        normalized_fields = dict(skill_result.get("normalized_fields") or {})
        extraction_metadata = dict(skill_result.get("extraction_metadata") or {})
        source_evidence = dict(skill_result.get("source_evidence") or {})
        source = dict(source_evidence.get("source") or {})
        document_input = dict(skill_result.get("document_input") or {})

        connection.execute(
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                source_record_id = excluded.source_record_id,
                source_attachment_ref_id = excluded.source_attachment_ref_id,
                source_url = excluded.source_url,
                tenant = excluded.tenant,
                document_type = excluded.document_type,
                business_name = excluded.business_name,
                credit_code = excluded.credit_code,
                business_address = excluded.business_address,
                legal_person = excluded.legal_person,
                valid_from = excluded.valid_from,
                valid_to = excluded.valid_to,
                issue_authority = excluded.issue_authority,
                issue_date = excluded.issue_date,
                review_status = excluded.review_status,
                risk_level = excluded.risk_level,
                needs_manual_review = excluded.needs_manual_review,
                summary = excluded.summary,
                rule_results_json = excluded.rule_results_json,
                extracted_fields_json = excluded.extracted_fields_json,
                normalized_fields_json = excluded.normalized_fields_json,
                extraction_metadata_json = excluded.extraction_metadata_json,
                source_evidence_json = excluded.source_evidence_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                review_result.task_id,
                source.get("record_id"),
                source.get("attachment_ref_id"),
                document_input.get("source_url"),
                source.get("tenant"),
                review_result.document_type,
                extracted_fields.get("subject_name"),
                extracted_fields.get("credit_code"),
                extracted_fields.get("business_address"),
                extracted_fields.get("legal_person"),
                extracted_fields.get("valid_from"),
                extracted_fields.get("valid_to"),
                extracted_fields.get("issue_authority"),
                extracted_fields.get("issue_date"),
                review_result.status.value,
                review_result.risk_level.value,
                int(review_result.needs_manual_review),
                review_result.summary,
                dumps(review_result.model_dump(mode="json")["rule_results"], ensure_ascii=False),
                dumps(extracted_fields, ensure_ascii=False),
                dumps(normalized_fields, ensure_ascii=False),
                dumps(extraction_metadata, ensure_ascii=False),
                dumps(source_evidence, ensure_ascii=False),
                review_result.created_at.isoformat(),
                review_result.updated_at.isoformat(),
            ),
        )
