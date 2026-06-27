from datetime import date, datetime
from json import dumps, loads
from queue import Empty, LifoQueue
from threading import Lock
from typing import Any

import pymysql
from fastapi.encoders import jsonable_encoder

from app.integrations.mysql_client import MySqlSettings, mysql_settings_from_env
from app.models import AuditEvent, ManualReview, ManualReviewStatus, ReviewResult, ReviewStatus
from app.services.wecom_notifications import notification_details_json


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
    updated_at,
    manual_review_decision
"""

_REPOSITORY_CACHE: dict[tuple[Any, ...], "MySQLReviewResultRepository"] = {}
_repository_cache_lock = Lock()


class _PooledConnection:
    def __init__(self, repository: "MySQLReviewResultRepository", connection) -> None:
        self._repository = repository
        self._connection = connection

    def __getattr__(self, name: str):
        return getattr(self._connection, name)

    def __enter__(self):
        return self._connection

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            self._repository._release_connection(self._connection)
        else:
            self._repository._discard_connection(self._connection)
        return False


class MySQLReviewResultRepository:
    def __init__(self, settings: MySqlSettings, *, pool_size: int = 5) -> None:
        self.settings = settings
        self._schema_ready = False
        self._pool_size = max(1, pool_size)
        self._pool: LifoQueue = LifoQueue(maxsize=self._pool_size)
        self._pool_lock = Lock()
        self._open_connections = 0

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
                self._save_food_license_projection(cursor, review_result)
                self._save_food_production_license_projection(cursor, review_result)
                self._save_tobacco_license_projection(cursor, review_result)
                self._save_tobacco_consistency_projection(cursor, review_result)
                self._save_product_report_projection(cursor, review_result)
            connection.commit()

    def close(self) -> None:
        with self._pool_lock:
            while True:
                try:
                    connection = self._pool.get_nowait()
                except Empty:
                    break
                _close_connection(connection)
                self._open_connections = max(0, self._open_connections - 1)

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

    def manual_review_business_license(
        self,
        *,
        task_id: str,
        decision: str,
        comment: str,
        reviewer_id: str,
        reviewer_username: str,
        reviewed_at: datetime,
    ) -> dict[str, Any] | None:
        self._ensure_schema_once()
        reviewed_at_text = reviewed_at.isoformat()
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
                existing = cursor.fetchone()
                if existing is None:
                    return None
                cursor.execute(
                    "SELECT payload_json FROM review_results WHERE task_id = %s",
                    (task_id,),
                )
                payload_row = cursor.fetchone()
                updated_payload = (
                    _manual_review_payload(
                        payload_json=payload_row["payload_json"],
                        decision=decision,
                        comment=comment,
                        reviewer_id=reviewer_id,
                        reviewer_username=reviewer_username,
                        reviewed_at=reviewed_at,
                    )
                    if payload_row is not None
                    else None
                )
                cursor.execute(
                    """
                    UPDATE business_license_reviews
                    SET
                        review_status = %s,
                        needs_manual_review = %s,
                        manual_review_status = %s,
                        manual_review_decision = %s,
                        manual_review_comment = %s,
                        manual_review_reviewer_id = %s,
                        manual_review_reviewer_username = %s,
                        manual_review_reviewed_at = %s,
                        updated_at = %s
                    WHERE task_id = %s
                    """,
                    (
                        "MANUAL_REVIEWED",
                        0,
                        "COMPLETED",
                        decision,
                        comment,
                        reviewer_id,
                        reviewer_username,
                        reviewed_at_text,
                        reviewed_at_text,
                        task_id,
                    ),
                )
                if updated_payload is not None:
                    cursor.execute(
                        """
                        UPDATE review_results
                        SET payload_json = %s
                        WHERE task_id = %s
                        """,
                        (updated_payload.model_dump_json(), task_id),
                    )
                cursor.execute(
                    """
                    INSERT INTO business_license_review_audit_events (
                        task_id,
                        event_type,
                        message,
                        occurred_at,
                        actor_id,
                        actor_username,
                        details_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        task_id,
                        "BUSINESS_LICENSE_MANUAL_REVIEW",
                        _manual_review_audit_message(decision),
                        reviewed_at_text,
                        reviewer_id,
                        reviewer_username,
                        dumps(
                            {
                                "decision": decision,
                                "comment": comment,
                                "reviewer_id": reviewer_id,
                                "reviewer_username": reviewer_username,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
            connection.commit()
        return self.get_business_license_snapshot(task_id)

    def list_business_license_audit_events(self, task_id: str) -> list[dict[str, Any]]:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        event_type,
                        message,
                        occurred_at,
                        actor_id,
                        actor_username,
                        details_json
                    FROM business_license_review_audit_events
                    WHERE task_id = %s
                    ORDER BY occurred_at ASC, id ASC
                    """,
                    (task_id,),
                )
                rows = cursor.fetchall()
        return [
            {
                "event_type": row["event_type"],
                "message": row["message"],
                "occurred_at": row["occurred_at"],
                "actor_id": row.get("actor_id"),
                "actor_username": row.get("actor_username"),
                "details": loads(row["details_json"] or "{}"),
            }
            for row in rows
        ]

    def enqueue_wecom_notification(
        self,
        *,
        template: str,
        to_user_ids: list[str],
        recipient_names: list[str],
        message: str,
        task_id: str | None,
        document_type: str | None,
        detail_url: str | None,
        created_at: datetime,
    ) -> dict[str, Any]:
        self._ensure_schema_once()
        created_at_text = created_at.isoformat()
        details_json = notification_details_json(
            to_user_ids=to_user_ids,
            recipient_names=recipient_names,
            detail_url=detail_url,
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO wecom_notification_queue (
                        channel,
                        status,
                        template,
                        to_user_ids_json,
                        recipient_names_json,
                        message,
                        task_id,
                        document_type,
                        detail_url,
                        attempts,
                        error,
                        next_retry_at,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        "wecom",
                        "queued" if to_user_ids else "failed",
                        template,
                        dumps(to_user_ids, ensure_ascii=False),
                        dumps(recipient_names, ensure_ascii=False),
                        message,
                        task_id,
                        document_type,
                        detail_url,
                        0,
                        None if to_user_ids else "企业微信通知缺少接收人",
                        None,
                        created_at_text,
                        created_at_text,
                    ),
                )
                notification_id = cursor.lastrowid
                if task_id:
                    cursor.execute(
                        """
                        INSERT INTO business_license_review_audit_events (
                            task_id,
                            event_type,
                            message,
                            occurred_at,
                            actor_id,
                            actor_username,
                            details_json
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            task_id,
                            "WECOM_NOTIFICATION_QUEUED" if to_user_ids else "WECOM_NOTIFICATION_FAILED",
                            "企业微信通知已入队" if to_user_ids else "企业微信通知缺少接收人",
                            created_at_text,
                            None,
                            None,
                            details_json,
                        ),
                    )
            connection.commit()
        return {
            "id": notification_id,
            "status": "queued" if to_user_ids else "failed",
            "task_id": task_id,
        }

    def list_due_wecom_notifications(self, now: datetime) -> list[dict[str, Any]]:
        self._ensure_schema_once()
        now_text = now.isoformat()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM wecom_notification_queue
                    WHERE channel = 'wecom'
                        AND status = 'queued'
                        AND attempts < 3
                        AND (next_retry_at IS NULL OR next_retry_at <= %s)
                    ORDER BY created_at ASC, id ASC
                    LIMIT 100
                    """,
                    (now_text,),
                )
                rows = cursor.fetchall()
        return [_wecom_notification_row(row) for row in rows]

    def mark_wecom_notification_sent(
        self,
        *,
        notification_id: int,
        sent_at: datetime,
    ) -> None:
        self._update_wecom_notification_status(
            notification_id=notification_id,
            status="sent",
            attempts=None,
            error=None,
            sent_at=sent_at,
            next_retry_at=None,
            updated_at=sent_at,
        )

    def mark_wecom_notification_retry(
        self,
        *,
        notification_id: int,
        attempts: int,
        error: str,
        next_retry_at: datetime,
        updated_at: datetime,
    ) -> None:
        self._update_wecom_notification_status(
            notification_id=notification_id,
            status="queued",
            attempts=attempts,
            error=error,
            sent_at=None,
            next_retry_at=next_retry_at,
            updated_at=updated_at,
        )

    def mark_wecom_notification_failed(
        self,
        *,
        notification_id: int,
        attempts: int,
        error: str,
        updated_at: datetime,
    ) -> None:
        self._update_wecom_notification_status(
            notification_id=notification_id,
            status="failed",
            attempts=attempts,
            error=error,
            sent_at=None,
            next_retry_at=None,
            updated_at=updated_at,
        )

    def get_frontend_setting(self, key: str, default: Any = None) -> Any:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT value_json
                    FROM frontend_settings
                    WHERE setting_key = %s
                    """,
                    (key,),
                )
                row = cursor.fetchone()
        if row is None:
            return default
        return loads(row["value_json"])

    def set_frontend_setting(self, key: str, value: Any) -> None:
        self._ensure_schema_once()
        updated_at = datetime.now().astimezone().isoformat()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO frontend_settings (setting_key, value_json, updated_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        value_json = VALUES(value_json),
                        updated_at = VALUES(updated_at)
                    """,
                    (key, dumps(value, ensure_ascii=False), updated_at),
                )
            connection.commit()

    def _update_wecom_notification_status(
        self,
        *,
        notification_id: int,
        status: str,
        attempts: int | None,
        error: str | None,
        sent_at: datetime | None,
        next_retry_at: datetime | None,
        updated_at: datetime,
    ) -> None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE wecom_notification_queue
                    SET
                        status = %s,
                        attempts = COALESCE(%s, attempts),
                        error = %s,
                        sent_at = %s,
                        next_retry_at = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        status,
                        attempts,
                        error,
                        sent_at.isoformat() if sent_at else None,
                        next_retry_at.isoformat() if next_retry_at else None,
                        updated_at.isoformat(),
                        notification_id,
                    ),
                )
            connection.commit()

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
                total = int(metrics_row.get("total") or 0)
                total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
                safe_page = min(max(1, page), total_pages)
                offset = (safe_page - 1) * safe_page_size
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

    def get_food_license_snapshot(self, task_id: str) -> dict | None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM food_license_reviews
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
                row = cursor.fetchone()
        if row is None:
            return None
        snapshot = dict(row)
        snapshot["needs_manual_review"] = bool(snapshot["needs_manual_review"])
        snapshot["business_items"] = loads(snapshot["business_items_json"])
        snapshot["rule_results"] = loads(snapshot["rule_results_json"])
        snapshot["extracted_fields"] = loads(snapshot["extracted_fields_json"])
        snapshot["normalized_fields"] = loads(snapshot["normalized_fields_json"])
        snapshot["extraction_metadata"] = loads(snapshot["extraction_metadata_json"])
        snapshot["source_evidence"] = loads(snapshot["source_evidence_json"])
        return snapshot

    def get_food_production_license_snapshot(self, task_id: str) -> dict | None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM food_production_license_reviews
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

    def get_tobacco_license_snapshot(self, task_id: str) -> dict | None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM tobacco_license_reviews
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

    def get_tobacco_consistency_snapshot(self, task_id: str) -> dict | None:
        self._ensure_schema_once()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM tobacco_consistency_reviews
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
        snapshot["comparison"] = loads(snapshot["comparison_json"])
        snapshot["business_license_fields"] = loads(snapshot["business_license_fields_json"])
        snapshot["tobacco_license_fields"] = loads(snapshot["tobacco_license_fields_json"])
        snapshot["source_evidence"] = loads(snapshot["source_evidence_json"])
        return snapshot

    def list_qc_reviews(
        self,
        *,
        supplier_name: str | None = None,
        credit_code: str | None = None,
        document_type: str | None = None,
        risk_level: str | None = None,
        review_status: str | None = None,
        needs_manual_review: bool | None = None,
        created_from: str | None = None,
        created_to: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        self._ensure_schema_once()
        rows = self._all_qc_review_rows()
        filtered = [
            row
            for row in rows
            if _qc_row_matches(
                row,
                supplier_name=supplier_name,
                credit_code=credit_code,
                document_type=document_type,
                risk_level=risk_level,
                review_status=review_status,
                needs_manual_review=needs_manual_review,
                created_from=created_from,
                created_to=created_to,
            )
        ]
        filtered.sort(
            key=lambda row: (row.get("created_at") or "", row.get("task_id") or ""),
            reverse=True,
        )
        safe_page_size = min(max(1, page_size), 100)
        total = len(filtered)
        total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
        safe_page = min(max(1, page), total_pages)
        offset = (safe_page - 1) * safe_page_size
        return {
            "items": filtered[offset : offset + safe_page_size],
            "metrics": _qc_review_metrics(filtered),
            "page": safe_page,
            "page_size": safe_page_size,
            "total": total,
            "total_pages": total_pages,
        }

    def get_qc_review_detail(self, task_id: str) -> dict[str, Any] | None:
        business_license = self.get_business_license_snapshot(task_id)
        if business_license is not None:
            return _qc_business_license_detail(business_license)
        food_license = self.get_food_license_snapshot(task_id)
        if food_license is not None:
            return _qc_food_license_detail(food_license)
        food_production_license = self.get_food_production_license_snapshot(task_id)
        if food_production_license is not None:
            return _qc_food_production_license_detail(food_production_license)
        tobacco_license = self.get_tobacco_license_snapshot(task_id)
        if tobacco_license is not None:
            return _qc_tobacco_license_detail(tobacco_license)
        consistency = self.get_tobacco_consistency_snapshot(task_id)
        if consistency is not None:
            return _qc_tobacco_consistency_detail(consistency)
        product_report = self.get_product_report_snapshot(task_id)
        if product_report is not None:
            return _qc_product_report_detail(product_report)
        return None

    def manual_review_qc_review(
        self,
        *,
        task_id: str,
        decision: str,
        comment: str,
        reviewer_id: str,
        reviewer_username: str,
        reviewed_at: datetime,
    ) -> dict[str, Any] | None:
        self._ensure_schema_once()
        table = self._qc_projection_table_for_task(task_id)
        if table is None:
            return None
        reviewed_at_text = reviewed_at.isoformat()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT payload_json FROM review_results WHERE task_id = %s",
                    (task_id,),
                )
                payload_row = cursor.fetchone()
                updated_payload = (
                    _manual_review_payload(
                        payload_json=payload_row["payload_json"],
                        decision=decision,
                        comment=comment,
                        reviewer_id=reviewer_id,
                        reviewer_username=reviewer_username,
                        reviewed_at=reviewed_at,
                    )
                    if payload_row is not None
                    else None
                )
                cursor.execute(
                    f"""
                    UPDATE {table}
                    SET
                        review_status = %s,
                        needs_manual_review = %s,
                        manual_review_status = %s,
                        manual_review_decision = %s,
                        manual_review_comment = %s,
                        manual_review_reviewer_id = %s,
                        manual_review_reviewer_username = %s,
                        manual_review_reviewed_at = %s,
                        updated_at = %s
                    WHERE task_id = %s
                    """,
                    (
                        "MANUAL_REVIEWED",
                        0,
                        "COMPLETED",
                        decision,
                        comment,
                        reviewer_id,
                        reviewer_username,
                        reviewed_at_text,
                        reviewed_at_text,
                        task_id,
                    ),
                )
                if updated_payload is not None:
                    cursor.execute(
                        """
                        UPDATE review_results
                        SET payload_json = %s
                        WHERE task_id = %s
                        """,
                        (updated_payload.model_dump_json(), task_id),
                    )
            connection.commit()
        return self.get_qc_review_detail(task_id)

    def _qc_projection_table_for_task(self, task_id: str) -> str | None:
        for table in (
            "business_license_reviews",
            "food_license_reviews",
            "food_production_license_reviews",
            "tobacco_license_reviews",
            "tobacco_consistency_reviews",
            "product_report_reviews",
        ):
            with self._connect() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"SELECT task_id FROM {table} WHERE task_id = %s",
                        (task_id,),
                    )
                    if cursor.fetchone() is not None:
                        return table
        return None

    def _all_qc_review_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {BUSINESS_LICENSE_REVIEW_ROW_COLUMNS}
                    FROM business_license_reviews
                    """
                )
                rows.extend(_qc_business_license_row(row) for row in cursor.fetchall())
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        source_record_id,
                        source_attachment_ref_id,
                        source_url,
                        tenant,
                        document_type,
                        subject_name,
                        credit_code,
                        license_no,
                        review_status,
                        risk_level,
                        needs_manual_review,
                        summary,
                        created_at,
                        updated_at
                    FROM food_license_reviews
                    """
                )
                rows.extend(_qc_food_license_row(row) for row in cursor.fetchall())
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        source_record_id,
                        source_attachment_ref_id,
                        source_url,
                        tenant,
                        document_type,
                        supplier_name,
                        credit_code,
                        review_status,
                        risk_level,
                        needs_manual_review,
                        summary,
                        created_at,
                        updated_at
                    FROM food_production_license_reviews
                    """
                )
                rows.extend(
                    _qc_food_production_license_row(row) for row in cursor.fetchall()
                )
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        source_record_id,
                        source_attachment_ref_id,
                        source_url,
                        tenant,
                        document_type,
                        subject_name,
                        license_no,
                        review_status,
                        risk_level,
                        needs_manual_review,
                        summary,
                        created_at,
                        updated_at
                    FROM tobacco_license_reviews
                    """
                )
                rows.extend(_qc_tobacco_license_row(row) for row in cursor.fetchall())
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        source_record_id,
                        source_attachment_ref_id,
                        source_url,
                        tenant,
                        document_type,
                        subject_name,
                        review_status,
                        risk_level,
                        needs_manual_review,
                        summary,
                        created_at,
                        updated_at
                    FROM tobacco_consistency_reviews
                    """
                )
                rows.extend(_qc_tobacco_consistency_row(row) for row in cursor.fetchall())
                cursor.execute(
                    """
                    SELECT
                        task_id,
                        source_record_id,
                        source_attachment_ref_id,
                        NULL AS source_url,
                        tenant,
                        document_type,
                        product_name,
                        sample_name,
                        vendor_name,
                        vendor_name_extracted,
                        review_status,
                        risk_level,
                        needs_manual_review,
                        summary,
                        created_at,
                        updated_at
                    FROM product_report_reviews
                    """
                )
                rows.extend(_qc_product_report_row(row) for row in cursor.fetchall())
        return rows

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
                        manual_review_status VARCHAR(64),
                        manual_review_decision VARCHAR(32),
                        manual_review_comment TEXT,
                        manual_review_reviewer_id VARCHAR(128),
                        manual_review_reviewer_username VARCHAR(128),
                        manual_review_reviewed_at VARCHAR(64),
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_business_license_source_record_id (source_record_id),
                        INDEX idx_business_license_credit_code (credit_code),
                        INDEX idx_business_license_status_risk (review_status, risk_level),
                        INDEX idx_business_license_created_at (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                for ddl in (
                    "ALTER TABLE business_license_reviews ADD COLUMN manual_review_status VARCHAR(64)",
                    "ALTER TABLE business_license_reviews ADD COLUMN manual_review_decision VARCHAR(32)",
                    "ALTER TABLE business_license_reviews ADD COLUMN manual_review_comment TEXT",
                    "ALTER TABLE business_license_reviews ADD COLUMN manual_review_reviewer_id VARCHAR(128)",
                    "ALTER TABLE business_license_reviews ADD COLUMN manual_review_reviewer_username VARCHAR(128)",
                    "ALTER TABLE business_license_reviews ADD COLUMN manual_review_reviewed_at VARCHAR(64)",
                ):
                    _try_add_column(cursor, ddl)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS business_license_review_audit_events (
                        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        task_id VARCHAR(128) NOT NULL,
                        event_type VARCHAR(128) NOT NULL,
                        message TEXT NOT NULL,
                        occurred_at VARCHAR(64) NOT NULL,
                        actor_id VARCHAR(128),
                        actor_username VARCHAR(128),
                        details_json JSON NOT NULL,
                        INDEX idx_business_license_review_audit_task_id (task_id),
                        INDEX idx_business_license_review_audit_occurred_at (occurred_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wecom_notification_queue (
                        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                        channel VARCHAR(32) NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        template VARCHAR(128) NOT NULL,
                        to_user_ids_json JSON NOT NULL,
                        recipient_names_json JSON NOT NULL,
                        message TEXT NOT NULL,
                        task_id VARCHAR(128),
                        document_type VARCHAR(64),
                        detail_url TEXT,
                        attempts INT NOT NULL DEFAULT 0,
                        error TEXT,
                        next_retry_at VARCHAR(64),
                        sent_at VARCHAR(64),
                        created_at VARCHAR(64) NOT NULL,
                        updated_at VARCHAR(64) NOT NULL,
                        INDEX idx_wecom_notification_status (channel, status, next_retry_at),
                        INDEX idx_wecom_notification_task_id (task_id)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS frontend_settings (
                        setting_key VARCHAR(128) PRIMARY KEY,
                        value_json JSON NOT NULL,
                        updated_at VARCHAR(64) NOT NULL
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
                        manual_review_status VARCHAR(64),
                        manual_review_decision VARCHAR(32),
                        manual_review_comment TEXT,
                        manual_review_reviewer_id VARCHAR(128),
                        manual_review_reviewer_username VARCHAR(128),
                        manual_review_reviewed_at VARCHAR(64),
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_product_report_source_record_id (source_record_id),
                        INDEX idx_product_report_status_risk (review_status, risk_level),
                        INDEX idx_product_report_created_at (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                for ddl in (
                    "ALTER TABLE product_report_reviews ADD COLUMN manual_review_status VARCHAR(64)",
                    "ALTER TABLE product_report_reviews ADD COLUMN manual_review_decision VARCHAR(32)",
                    "ALTER TABLE product_report_reviews ADD COLUMN manual_review_comment TEXT",
                    "ALTER TABLE product_report_reviews ADD COLUMN manual_review_reviewer_id VARCHAR(128)",
                    "ALTER TABLE product_report_reviews ADD COLUMN manual_review_reviewer_username VARCHAR(128)",
                    "ALTER TABLE product_report_reviews ADD COLUMN manual_review_reviewed_at VARCHAR(64)",
                ):
                    _try_add_column(cursor, ddl)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS food_license_reviews (
                        task_id VARCHAR(128) PRIMARY KEY,
                        source_record_id VARCHAR(255),
                        source_attachment_ref_id VARCHAR(255),
                        source_url TEXT,
                        tenant VARCHAR(128),
                        document_type VARCHAR(64) NOT NULL,
                        subject_name VARCHAR(512),
                        credit_code VARCHAR(64),
                        license_no VARCHAR(255),
                        business_address TEXT,
                        legal_person VARCHAR(255),
                        business_items_json JSON NOT NULL,
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
                        manual_review_status VARCHAR(64),
                        manual_review_decision VARCHAR(32),
                        manual_review_comment TEXT,
                        manual_review_reviewer_id VARCHAR(128),
                        manual_review_reviewer_username VARCHAR(128),
                        manual_review_reviewed_at VARCHAR(64),
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_food_license_source_record_id (source_record_id),
                        INDEX idx_food_license_credit_code (credit_code),
                        INDEX idx_food_license_status_risk (review_status, risk_level),
                        INDEX idx_food_license_created_at (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS food_production_license_reviews (
                        task_id VARCHAR(128) PRIMARY KEY,
                        source_record_id VARCHAR(255),
                        source_attachment_ref_id VARCHAR(255),
                        source_url TEXT,
                        tenant VARCHAR(128),
                        document_type VARCHAR(64) NOT NULL,
                        supplier_name VARCHAR(512),
                        credit_code VARCHAR(64),
                        review_status VARCHAR(64) NOT NULL,
                        risk_level VARCHAR(64) NOT NULL,
                        needs_manual_review TINYINT NOT NULL,
                        summary TEXT NOT NULL,
                        rule_results_json JSON NOT NULL,
                        extracted_fields_json JSON NOT NULL,
                        normalized_fields_json JSON NOT NULL,
                        extraction_metadata_json JSON NOT NULL,
                        source_evidence_json JSON NOT NULL,
                        manual_review_status VARCHAR(64),
                        manual_review_decision VARCHAR(32),
                        manual_review_comment TEXT,
                        manual_review_reviewer_id VARCHAR(128),
                        manual_review_reviewer_username VARCHAR(128),
                        manual_review_reviewed_at VARCHAR(64),
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_food_production_license_source_record_id (source_record_id),
                        INDEX idx_food_production_license_credit_code (credit_code),
                        INDEX idx_food_production_license_status_risk (review_status, risk_level),
                        INDEX idx_food_production_license_created_at (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tobacco_license_reviews (
                        task_id VARCHAR(128) PRIMARY KEY,
                        source_record_id VARCHAR(255),
                        source_attachment_ref_id VARCHAR(255),
                        source_url TEXT,
                        tenant VARCHAR(128),
                        document_type VARCHAR(64) NOT NULL,
                        subject_name VARCHAR(512),
                        business_address TEXT,
                        legal_person VARCHAR(255),
                        license_no VARCHAR(255),
                        valid_from VARCHAR(64),
                        valid_to VARCHAR(64),
                        review_status VARCHAR(64) NOT NULL,
                        risk_level VARCHAR(64) NOT NULL,
                        needs_manual_review TINYINT NOT NULL,
                        summary TEXT NOT NULL,
                        rule_results_json JSON NOT NULL,
                        extracted_fields_json JSON NOT NULL,
                        normalized_fields_json JSON NOT NULL,
                        extraction_metadata_json JSON NOT NULL,
                        source_evidence_json JSON NOT NULL,
                        manual_review_status VARCHAR(64),
                        manual_review_decision VARCHAR(32),
                        manual_review_comment TEXT,
                        manual_review_reviewer_id VARCHAR(128),
                        manual_review_reviewer_username VARCHAR(128),
                        manual_review_reviewed_at VARCHAR(64),
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_tobacco_license_source_record_id (source_record_id),
                        INDEX idx_tobacco_license_status_risk (review_status, risk_level),
                        INDEX idx_tobacco_license_created_at (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tobacco_consistency_reviews (
                        task_id VARCHAR(128) PRIMARY KEY,
                        source_record_id VARCHAR(255),
                        source_attachment_ref_id VARCHAR(255),
                        source_url TEXT,
                        tenant VARCHAR(128),
                        document_type VARCHAR(64) NOT NULL,
                        subject_name VARCHAR(512),
                        review_status VARCHAR(64) NOT NULL,
                        risk_level VARCHAR(64) NOT NULL,
                        needs_manual_review TINYINT NOT NULL,
                        summary TEXT NOT NULL,
                        rule_results_json JSON NOT NULL,
                        comparison_json JSON NOT NULL,
                        business_license_fields_json JSON NOT NULL,
                        tobacco_license_fields_json JSON NOT NULL,
                        source_evidence_json JSON NOT NULL,
                        manual_review_status VARCHAR(64),
                        manual_review_decision VARCHAR(32),
                        manual_review_comment TEXT,
                        manual_review_reviewer_id VARCHAR(128),
                        manual_review_reviewer_username VARCHAR(128),
                        manual_review_reviewed_at VARCHAR(64),
                        created_at VARCHAR(64),
                        updated_at VARCHAR(64),
                        INDEX idx_tobacco_consistency_source_record_id (source_record_id),
                        INDEX idx_tobacco_consistency_status_risk (review_status, risk_level),
                        INDEX idx_tobacco_consistency_created_at (created_at)
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
        return _PooledConnection(self, self._acquire_connection())

    def _acquire_connection(self):
        try:
            connection = self._pool.get_nowait()
        except Empty:
            with self._pool_lock:
                if self._open_connections < self._pool_size:
                    self._open_connections += 1
                    return self._new_connection()
            connection = self._pool.get()
        try:
            connection.ping(reconnect=True)
        except Exception:
            self._discard_connection(connection)
            return self._acquire_connection()
        return connection

    def _release_connection(self, connection) -> None:
        try:
            self._pool.put_nowait(connection)
        except Exception:
            self._discard_connection(connection)

    def _discard_connection(self, connection) -> None:
        _close_connection(connection)
        with self._pool_lock:
            self._open_connections = max(0, self._open_connections - 1)

    def _new_connection(self):
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

    def _save_food_license_projection(self, cursor, review_result: ReviewResult) -> None:
        if review_result.document_type != "food_license":
            return

        projection = _food_license_projection(review_result)
        cursor.execute(
            """
            INSERT INTO food_license_reviews (
                task_id,
                source_record_id,
                source_attachment_ref_id,
                source_url,
                tenant,
                document_type,
                subject_name,
                credit_code,
                license_no,
                business_address,
                legal_person,
                business_items_json,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_record_id = VALUES(source_record_id),
                source_attachment_ref_id = VALUES(source_attachment_ref_id),
                source_url = VALUES(source_url),
                tenant = VALUES(tenant),
                document_type = VALUES(document_type),
                subject_name = VALUES(subject_name),
                credit_code = VALUES(credit_code),
                license_no = VALUES(license_no),
                business_address = VALUES(business_address),
                legal_person = VALUES(legal_person),
                business_items_json = VALUES(business_items_json),
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
            _food_license_projection_values(projection),
        )

    def _save_food_production_license_projection(self, cursor, review_result: ReviewResult) -> None:
        if review_result.document_type != "food_production_license":
            return

        projection = _food_production_license_projection(review_result)
        cursor.execute(
            """
            INSERT INTO food_production_license_reviews (
                task_id,
                source_record_id,
                source_attachment_ref_id,
                source_url,
                tenant,
                document_type,
                supplier_name,
                credit_code,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_record_id = VALUES(source_record_id),
                source_attachment_ref_id = VALUES(source_attachment_ref_id),
                source_url = VALUES(source_url),
                tenant = VALUES(tenant),
                document_type = VALUES(document_type),
                supplier_name = VALUES(supplier_name),
                credit_code = VALUES(credit_code),
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
            _food_production_license_projection_values(projection),
        )

    def _save_tobacco_license_projection(self, cursor, review_result: ReviewResult) -> None:
        if review_result.document_type != "tobacco_license":
            return

        projection = _tobacco_license_projection(review_result)
        cursor.execute(
            """
            INSERT INTO tobacco_license_reviews (
                task_id,
                source_record_id,
                source_attachment_ref_id,
                source_url,
                tenant,
                document_type,
                subject_name,
                business_address,
                legal_person,
                license_no,
                valid_from,
                valid_to,
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_record_id = VALUES(source_record_id),
                source_attachment_ref_id = VALUES(source_attachment_ref_id),
                source_url = VALUES(source_url),
                tenant = VALUES(tenant),
                document_type = VALUES(document_type),
                subject_name = VALUES(subject_name),
                business_address = VALUES(business_address),
                legal_person = VALUES(legal_person),
                license_no = VALUES(license_no),
                valid_from = VALUES(valid_from),
                valid_to = VALUES(valid_to),
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
            _tobacco_license_projection_values(projection),
        )

    def _save_tobacco_consistency_projection(self, cursor, review_result: ReviewResult) -> None:
        if review_result.document_type != "business_tobacco_consistency":
            return

        projection = _tobacco_consistency_projection(review_result)
        cursor.execute(
            """
            INSERT INTO tobacco_consistency_reviews (
                task_id,
                source_record_id,
                source_attachment_ref_id,
                source_url,
                tenant,
                document_type,
                subject_name,
                review_status,
                risk_level,
                needs_manual_review,
                summary,
                rule_results_json,
                comparison_json,
                business_license_fields_json,
                tobacco_license_fields_json,
                source_evidence_json,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                source_record_id = VALUES(source_record_id),
                source_attachment_ref_id = VALUES(source_attachment_ref_id),
                source_url = VALUES(source_url),
                tenant = VALUES(tenant),
                document_type = VALUES(document_type),
                subject_name = VALUES(subject_name),
                review_status = VALUES(review_status),
                risk_level = VALUES(risk_level),
                needs_manual_review = VALUES(needs_manual_review),
                summary = VALUES(summary),
                rule_results_json = VALUES(rule_results_json),
                comparison_json = VALUES(comparison_json),
                business_license_fields_json = VALUES(business_license_fields_json),
                tobacco_license_fields_json = VALUES(tobacco_license_fields_json),
                source_evidence_json = VALUES(source_evidence_json),
                created_at = VALUES(created_at),
                updated_at = VALUES(updated_at)
            """,
            _tobacco_consistency_projection_values(projection),
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
    settings = mysql_settings_from_env("REVIEW_RESULT_MYSQL")
    cache_key = (
        settings.host,
        settings.port,
        settings.user,
        settings.database,
        settings.charset,
        settings.connect_timeout,
    )
    with _repository_cache_lock:
        if cache_key not in _REPOSITORY_CACHE:
            _REPOSITORY_CACHE[cache_key] = MySQLReviewResultRepository(settings)
        return _REPOSITORY_CACHE[cache_key]


def reset_review_result_repository_cache() -> None:
    with _repository_cache_lock:
        for repository in _REPOSITORY_CACHE.values():
            repository.close()
        _REPOSITORY_CACHE.clear()


def _close_connection(connection) -> None:
    try:
        connection.close()
    except Exception:
        pass


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


def _qc_business_license_row(row: dict[str, Any]) -> dict[str, Any]:
    item = _business_license_review_row(row)
    return {
        "task_id": item["task_id"],
        "use_case_name": "business_license",
        "document_type": "business_license",
        "document_type_label": _document_type_label("business_license"),
        "supplier_name": item.get("business_name"),
        "credit_code": item.get("credit_code"),
        "review_status": item.get("review_status"),
        "review_status_label": item.get("review_status_label"),
        "risk_level": item.get("risk_level"),
        "risk_level_label": item.get("risk_level_label"),
        "needs_manual_review": item.get("needs_manual_review"),
        "summary": item.get("summary"),
        "source_record_id": item.get("source_record_id"),
        "source_attachment_ref_id": item.get("source_attachment_ref_id"),
        "source_url": item.get("source_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _qc_product_report_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["needs_manual_review"] = bool(item["needs_manual_review"])
    supplier_name = (
        item.get("vendor_name")
        or item.get("vendor_name_extracted")
        or item.get("product_name")
        or item.get("sample_name")
    )
    return {
        "task_id": item["task_id"],
        "use_case_name": "qc_document_review",
        "document_type": "product_report",
        "document_type_label": _document_type_label("product_report"),
        "supplier_name": supplier_name,
        "credit_code": None,
        "review_status": item.get("review_status"),
        "review_status_label": _review_status_label(item.get("review_status") or ""),
        "risk_level": item.get("risk_level"),
        "risk_level_label": _risk_level_label(item.get("risk_level") or ""),
        "needs_manual_review": item.get("needs_manual_review"),
        "summary": item.get("summary"),
        "source_record_id": item.get("source_record_id"),
        "source_attachment_ref_id": item.get("source_attachment_ref_id"),
        "source_url": item.get("source_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _qc_food_license_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["needs_manual_review"] = bool(item["needs_manual_review"])
    return {
        "task_id": item["task_id"],
        "use_case_name": "food_license",
        "document_type": "food_license",
        "document_type_label": _document_type_label("food_license"),
        "supplier_name": item.get("subject_name"),
        "credit_code": item.get("credit_code"),
        "review_status": item.get("review_status"),
        "review_status_label": _review_status_label(item.get("review_status") or ""),
        "risk_level": item.get("risk_level"),
        "risk_level_label": _risk_level_label(item.get("risk_level") or ""),
        "needs_manual_review": item.get("needs_manual_review"),
        "summary": item.get("summary"),
        "source_record_id": item.get("source_record_id"),
        "source_attachment_ref_id": item.get("source_attachment_ref_id"),
        "source_url": item.get("source_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _qc_food_production_license_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["needs_manual_review"] = bool(item["needs_manual_review"])
    return {
        "task_id": item["task_id"],
        "use_case_name": "food_production_license",
        "document_type": "food_production_license",
        "document_type_label": _document_type_label("food_production_license"),
        "supplier_name": item.get("supplier_name"),
        "credit_code": _food_production_credit_code_for_display(item.get("credit_code")),
        "review_status": item.get("review_status"),
        "review_status_label": _review_status_label(item.get("review_status") or ""),
        "risk_level": item.get("risk_level"),
        "risk_level_label": _risk_level_label(item.get("risk_level") or ""),
        "needs_manual_review": item.get("needs_manual_review"),
        "summary": item.get("summary"),
        "source_record_id": item.get("source_record_id"),
        "source_attachment_ref_id": item.get("source_attachment_ref_id"),
        "source_url": item.get("source_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _qc_tobacco_license_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["needs_manual_review"] = bool(item["needs_manual_review"])
    return {
        "task_id": item["task_id"],
        "use_case_name": "tobacco_license",
        "document_type": "tobacco_license",
        "document_type_label": _document_type_label("tobacco_license"),
        "supplier_name": item.get("subject_name"),
        "credit_code": None,
        "review_status": item.get("review_status"),
        "review_status_label": _review_status_label(item.get("review_status") or ""),
        "risk_level": item.get("risk_level"),
        "risk_level_label": _risk_level_label(item.get("risk_level") or ""),
        "needs_manual_review": item.get("needs_manual_review"),
        "summary": item.get("summary"),
        "source_record_id": item.get("source_record_id"),
        "source_attachment_ref_id": item.get("source_attachment_ref_id"),
        "source_url": item.get("source_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _qc_tobacco_consistency_row(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["needs_manual_review"] = bool(item["needs_manual_review"])
    return {
        "task_id": item["task_id"],
        "use_case_name": "tobacco_license_consistency_review",
        "document_type": "business_tobacco_consistency",
        "document_type_label": _document_type_label("business_tobacco_consistency"),
        "supplier_name": item.get("subject_name"),
        "credit_code": None,
        "review_status": item.get("review_status"),
        "review_status_label": _review_status_label(item.get("review_status") or ""),
        "risk_level": item.get("risk_level"),
        "risk_level_label": _risk_level_label(item.get("risk_level") or ""),
        "needs_manual_review": item.get("needs_manual_review"),
        "summary": item.get("summary"),
        "source_record_id": item.get("source_record_id"),
        "source_attachment_ref_id": item.get("source_attachment_ref_id"),
        "source_url": item.get("source_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def _qc_business_license_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
    row = _qc_business_license_row(snapshot)
    return {
        **row,
        "business_address": snapshot.get("business_address"),
        "legal_person": snapshot.get("legal_person"),
        "valid_from": snapshot.get("valid_from"),
        "valid_to": snapshot.get("valid_to"),
        "issue_authority": snapshot.get("issue_authority"),
        "issue_date": snapshot.get("issue_date"),
        "rule_results": snapshot["rule_results"],
        "extracted_fields": snapshot["extracted_fields"],
        "normalized_fields": snapshot["normalized_fields"],
        "extraction_metadata": snapshot["extraction_metadata"],
        "source_evidence": snapshot["source_evidence"],
        "manual_review": {
            "status": snapshot.get("manual_review_status") or (
                "PENDING" if snapshot.get("needs_manual_review") else "NOT_REQUIRED"
            ),
            "decision": snapshot.get("manual_review_decision"),
            "comment": snapshot.get("manual_review_comment"),
            "reviewer_id": snapshot.get("manual_review_reviewer_id"),
            "reviewer_username": snapshot.get("manual_review_reviewer_username"),
            "reviewed_at": snapshot.get("manual_review_reviewed_at"),
            "reasons": [],
        },
    }


def _qc_food_license_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
    row = _qc_food_license_row(snapshot)
    return {
        **row,
        "business_address": snapshot.get("business_address"),
        "legal_person": snapshot.get("legal_person"),
        "valid_from": snapshot.get("valid_from"),
        "valid_to": snapshot.get("valid_to"),
        "issue_authority": snapshot.get("issue_authority"),
        "issue_date": snapshot.get("issue_date"),
        "license_no": snapshot.get("license_no"),
        "business_items": snapshot.get("business_items", []),
        "rule_results": snapshot["rule_results"],
        "extracted_fields": snapshot["extracted_fields"],
        "normalized_fields": snapshot["normalized_fields"],
        "extraction_metadata": snapshot["extraction_metadata"],
        "source_evidence": snapshot["source_evidence"],
        "manual_review": {
            "status": snapshot.get("manual_review_status") or (
                "PENDING" if snapshot.get("needs_manual_review") else "NOT_REQUIRED"
            ),
            "decision": snapshot.get("manual_review_decision"),
            "comment": snapshot.get("manual_review_comment"),
            "reviewer_id": snapshot.get("manual_review_reviewer_id"),
            "reviewer_username": snapshot.get("manual_review_reviewer_username"),
            "reviewed_at": snapshot.get("manual_review_reviewed_at"),
            "reasons": [],
        },
    }


def _qc_food_production_license_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
    row = _qc_food_production_license_row(snapshot)
    normalized_fields = snapshot["normalized_fields"]
    return {
        **row,
        "producer_name": normalized_fields.get("producer_name"),
        "production_address": normalized_fields.get("production_address"),
        "legal_person": normalized_fields.get("legal_person"),
        "valid_from": normalized_fields.get("valid_from"),
        "valid_to": normalized_fields.get("valid_to"),
        "license_no": normalized_fields.get("license_no"),
        "food_categories": normalized_fields.get("food_categories", []),
        "rule_results": snapshot["rule_results"],
        "extracted_fields": snapshot["extracted_fields"],
        "normalized_fields": normalized_fields,
        "extraction_metadata": snapshot["extraction_metadata"],
        "source_evidence": snapshot["source_evidence"],
        "manual_review": {
            "status": snapshot.get("manual_review_status") or (
                "PENDING" if snapshot.get("needs_manual_review") else "NOT_REQUIRED"
            ),
            "decision": snapshot.get("manual_review_decision"),
            "comment": snapshot.get("manual_review_comment"),
            "reviewer_id": snapshot.get("manual_review_reviewer_id"),
            "reviewer_username": snapshot.get("manual_review_reviewer_username"),
            "reviewed_at": snapshot.get("manual_review_reviewed_at"),
            "reasons": [],
        },
    }


def _qc_tobacco_license_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
    row = _qc_tobacco_license_row(snapshot)
    return {
        **row,
        "business_address": snapshot.get("business_address"),
        "legal_person": snapshot.get("legal_person"),
        "valid_from": snapshot.get("valid_from"),
        "valid_to": snapshot.get("valid_to"),
        "license_no": snapshot.get("license_no"),
        "rule_results": snapshot["rule_results"],
        "extracted_fields": snapshot["extracted_fields"],
        "normalized_fields": snapshot["normalized_fields"],
        "extraction_metadata": snapshot["extraction_metadata"],
        "source_evidence": snapshot["source_evidence"],
        "manual_review": {
            "status": snapshot.get("manual_review_status") or (
                "PENDING" if snapshot.get("needs_manual_review") else "NOT_REQUIRED"
            ),
            "decision": snapshot.get("manual_review_decision"),
            "comment": snapshot.get("manual_review_comment"),
            "reviewer_id": snapshot.get("manual_review_reviewer_id"),
            "reviewer_username": snapshot.get("manual_review_reviewer_username"),
            "reviewed_at": snapshot.get("manual_review_reviewed_at"),
            "reasons": [],
        },
    }


def _qc_tobacco_consistency_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
    row = _qc_tobacco_consistency_row(snapshot)
    return {
        **row,
        "rule_results": snapshot["rule_results"],
        "comparison": snapshot["comparison"],
        "business_license_fields": snapshot["business_license_fields"],
        "tobacco_license_fields": snapshot["tobacco_license_fields"],
        "extracted_fields": {
            "business_license": snapshot["business_license_fields"],
            "tobacco_license": snapshot["tobacco_license_fields"],
        },
        "normalized_fields": snapshot["comparison"],
        "source_evidence": snapshot["source_evidence"],
        "manual_review": {
            "status": snapshot.get("manual_review_status") or (
                "PENDING" if snapshot.get("needs_manual_review") else "NOT_REQUIRED"
            ),
            "decision": snapshot.get("manual_review_decision"),
            "comment": snapshot.get("manual_review_comment"),
            "reviewer_id": snapshot.get("manual_review_reviewer_id"),
            "reviewer_username": snapshot.get("manual_review_reviewer_username"),
            "reviewed_at": snapshot.get("manual_review_reviewed_at"),
            "reasons": [],
        },
    }


def _qc_product_report_detail(snapshot: dict[str, Any]) -> dict[str, Any]:
    row = _qc_product_report_row(snapshot)
    extracted_fields = {
        "product_name": snapshot.get("product_name"),
        "sample_name": snapshot.get("sample_name"),
        "vendor_name_extracted": snapshot.get("vendor_name_extracted"),
        "entrusting_party": snapshot.get("entrusting_party"),
        "manufacturer_name": snapshot.get("manufacturer_name"),
        "batch_no": snapshot.get("batch_no"),
        "production_date": snapshot.get("production_date"),
        "issue_date": snapshot.get("issue_date"),
        "sign_date": snapshot.get("sign_date"),
        "inspection_conclusion": snapshot.get("inspection_conclusion"),
        "inspection_result": snapshot.get("inspection_result"),
        "inspection_items": snapshot.get("inspection_items", []),
    }
    return {
        **row,
        "rule_results": snapshot["rule_results"],
        "extracted_fields": extracted_fields,
        "normalized_fields": extracted_fields,
        "extraction_metadata": snapshot["extraction_metadata"],
        "source_evidence": snapshot["source_evidence"],
        "manual_review": {
            "status": snapshot.get("manual_review_status") or (
                "PENDING" if snapshot.get("needs_manual_review") else "NOT_REQUIRED"
            ),
            "decision": snapshot.get("manual_review_decision"),
            "comment": snapshot.get("manual_review_comment"),
            "reviewer_id": snapshot.get("manual_review_reviewer_id"),
            "reviewer_username": snapshot.get("manual_review_reviewer_username"),
            "reviewed_at": snapshot.get("manual_review_reviewed_at"),
            "reasons": [],
        },
    }


def _qc_row_matches(
    row: dict[str, Any],
    *,
    supplier_name: str | None,
    credit_code: str | None,
    document_type: str | None,
    risk_level: str | None,
    review_status: str | None,
    needs_manual_review: bool | None,
    created_from: str | None,
    created_to: str | None,
) -> bool:
    if supplier_name and supplier_name not in str(row.get("supplier_name") or ""):
        return False
    if credit_code and credit_code.upper() not in str(row.get("credit_code") or "").upper():
        return False
    if document_type and row.get("document_type") != document_type:
        return False
    if risk_level and row.get("risk_level") != risk_level:
        return False
    if review_status and row.get("review_status") != review_status:
        return False
    if needs_manual_review is not None and bool(row.get("needs_manual_review")) is not needs_manual_review:
        return False
    created_at = str(row.get("created_at") or "")
    if created_from and created_at < _created_from_boundary(created_from):
        return False
    if created_to and created_at > _created_to_boundary(created_to):
        return False
    return True


def _qc_review_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    reviewed = sum(1 for row in rows if row.get("review_status") == "REVIEWED")
    document_type_counts: dict[str, int] = {}
    for row in rows:
        document_type = str(row.get("document_type") or "unknown")
        document_type_counts[document_type] = document_type_counts.get(document_type, 0) + 1
    return {
        "today_reviewed": sum(1 for row in rows if _is_today(row.get("created_at"))),
        "pending_manual_review": sum(1 for row in rows if row.get("needs_manual_review")),
        "high_risk": sum(1 for row in rows if row.get("risk_level") == "HIGH"),
        "pass_rate": 0 if total == 0 else round((reviewed / total) * 100),
        "document_type_counts": document_type_counts,
    }


def _document_type_label(document_type: str) -> str:
    return {
        "business_license": "营业执照",
        "food_license": "食品经营许可证",
        "food_production_license": "食品生产许可证",
        "product_report": "产品报告",
        "tobacco_license": "烟草专卖零售许可证",
        "business_tobacco_consistency": "营业执照与烟草证一致性",
    }.get(document_type, document_type)


def _try_add_column(cursor, ddl: str) -> None:
    try:
        cursor.execute(ddl)
    except pymysql.err.OperationalError as error:
        if error.args and error.args[0] == 1060:
            return
        raise


def _manual_review_audit_message(decision: str) -> str:
    return {
        "approved": "人工复核确认通过",
        "rejected": "人工复核驳回",
    }.get(decision, "人工复核完成")


def _wecom_notification_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "channel": row["channel"],
        "status": row["status"],
        "template": row["template"],
        "to_user_ids": loads(row["to_user_ids_json"] or "[]"),
        "recipient_names": loads(row["recipient_names_json"] or "[]"),
        "message": row["message"],
        "task_id": row.get("task_id"),
        "document_type": row.get("document_type"),
        "detail_url": row.get("detail_url"),
        "attempts": int(row.get("attempts") or 0),
        "error": row.get("error"),
        "next_retry_at": row.get("next_retry_at"),
        "sent_at": row.get("sent_at"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _manual_review_payload(
    *,
    payload_json: str,
    decision: str,
    comment: str,
    reviewer_id: str,
    reviewer_username: str,
    reviewed_at: datetime,
) -> ReviewResult:
    result = ReviewResult.model_validate_json(payload_json)
    audit_event = AuditEvent(
        event_type="BUSINESS_LICENSE_MANUAL_REVIEW",
        message=_manual_review_audit_message(decision),
        occurred_at=reviewed_at,
        details={
            "decision": decision,
            "comment": comment,
            "reviewer_id": reviewer_id,
            "reviewer_username": reviewer_username,
        },
    )
    return result.model_copy(
        update={
            "status": ReviewStatus.MANUAL_REVIEWED,
            "needs_manual_review": False,
            "manual_review": ManualReview(
                status=ManualReviewStatus.COMPLETED,
                reasons=result.manual_review.reasons,
                reviewer=reviewer_id,
                action=decision,
                comment=comment,
                reviewed_at=reviewed_at,
            ),
            "audit_events": [*result.audit_events, audit_event],
            "updated_at": reviewed_at,
        }
    )


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
    return _json_dumps(review_result.model_dump(mode="json")["rule_results"])


def _json_dumps(payload: Any) -> str:
    return dumps(jsonable_encoder(payload), ensure_ascii=False)


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
        "extracted_fields_json": _json_dumps(extracted_fields),
        "normalized_fields_json": _json_dumps(normalized_fields),
        "extraction_metadata_json": _json_dumps(extraction_metadata),
        "source_evidence_json": _json_dumps(source_evidence),
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


def _food_license_projection(review_result: ReviewResult) -> dict[str, Any]:
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
        "subject_name": extracted_fields.get("subject_name"),
        "credit_code": extracted_fields.get("credit_code"),
        "license_no": extracted_fields.get("license_no"),
        "business_address": extracted_fields.get("business_address"),
        "legal_person": extracted_fields.get("legal_person"),
        "business_items_json": _json_dumps(list(extracted_fields.get("business_items") or [])),
        "valid_from": extracted_fields.get("valid_from"),
        "valid_to": extracted_fields.get("valid_to"),
        "issue_authority": extracted_fields.get("issue_authority"),
        "issue_date": extracted_fields.get("issue_date"),
        "review_status": review_result.status.value,
        "risk_level": review_result.risk_level.value,
        "needs_manual_review": int(review_result.needs_manual_review),
        "summary": review_result.summary,
        "rule_results_json": _rule_results_json(review_result),
        "extracted_fields_json": _json_dumps(extracted_fields),
        "normalized_fields_json": _json_dumps(normalized_fields),
        "extraction_metadata_json": _json_dumps(extraction_metadata),
        "source_evidence_json": _json_dumps(source_evidence),
        "created_at": review_result.created_at.isoformat(),
        "updated_at": review_result.updated_at.isoformat(),
    }


def _food_license_projection_values(projection: dict[str, Any]) -> tuple[Any, ...]:
    return (
        projection["task_id"],
        projection["source_record_id"],
        projection["source_attachment_ref_id"],
        projection["source_url"],
        projection["tenant"],
        projection["document_type"],
        projection["subject_name"],
        projection["credit_code"],
        projection["license_no"],
        projection["business_address"],
        projection["legal_person"],
        projection["business_items_json"],
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


def _food_production_license_projection(review_result: ReviewResult) -> dict[str, Any]:
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
        "source_url": (
            document_input.get("source_url")
            or source.get("source_payload", {}).get("url")
            if isinstance(source.get("source_payload"), dict)
            else document_input.get("source_url")
        ),
        "tenant": source.get("tenant"),
        "document_type": review_result.document_type,
        "supplier_name": source_evidence.get("supplier_name"),
        "credit_code": (
            extracted_fields.get("credit_code")
            or _source_payload_value(source, "num")
        ),
        "review_status": review_result.status.value,
        "risk_level": review_result.risk_level.value,
        "needs_manual_review": int(review_result.needs_manual_review),
        "summary": review_result.summary,
        "rule_results_json": _rule_results_json(review_result),
        "extracted_fields_json": _json_dumps(extracted_fields),
        "normalized_fields_json": _json_dumps(normalized_fields),
        "extraction_metadata_json": _json_dumps(extraction_metadata),
        "source_evidence_json": _json_dumps(source_evidence),
        "created_at": review_result.created_at.isoformat(),
        "updated_at": review_result.updated_at.isoformat(),
    }


def _food_production_license_projection_values(projection: dict[str, Any]) -> tuple[Any, ...]:
    return (
        projection["task_id"],
        projection["source_record_id"],
        projection["source_attachment_ref_id"],
        projection["source_url"],
        projection["tenant"],
        projection["document_type"],
        projection["supplier_name"],
        projection["credit_code"],
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


def _source_payload_value(source: dict[str, Any], *keys: str) -> Any:
    payload = source.get("source_payload")
    if not isinstance(payload, dict):
        return None
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _food_production_credit_code_for_display(value: Any) -> Any:
    text = "" if value is None else str(value).strip()
    if text.upper().startswith("SC"):
        return None
    return value


def _tobacco_license_projection(review_result: ReviewResult) -> dict[str, Any]:
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
        "subject_name": extracted_fields.get("subject_name"),
        "business_address": extracted_fields.get("business_address"),
        "legal_person": extracted_fields.get("legal_person"),
        "license_no": extracted_fields.get("license_no"),
        "valid_from": extracted_fields.get("valid_from"),
        "valid_to": extracted_fields.get("valid_to"),
        "review_status": review_result.status.value,
        "risk_level": review_result.risk_level.value,
        "needs_manual_review": int(review_result.needs_manual_review),
        "summary": review_result.summary,
        "rule_results_json": _rule_results_json(review_result),
        "extracted_fields_json": _json_dumps(extracted_fields),
        "normalized_fields_json": _json_dumps(normalized_fields),
        "extraction_metadata_json": _json_dumps(extraction_metadata),
        "source_evidence_json": _json_dumps(source_evidence),
        "created_at": review_result.created_at.isoformat(),
        "updated_at": review_result.updated_at.isoformat(),
    }


def _tobacco_license_projection_values(projection: dict[str, Any]) -> tuple[Any, ...]:
    return (
        projection["task_id"],
        projection["source_record_id"],
        projection["source_attachment_ref_id"],
        projection["source_url"],
        projection["tenant"],
        projection["document_type"],
        projection["subject_name"],
        projection["business_address"],
        projection["legal_person"],
        projection["license_no"],
        projection["valid_from"],
        projection["valid_to"],
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


def _tobacco_consistency_projection(review_result: ReviewResult) -> dict[str, Any]:
    skill_result = _skill_result_dict(review_result)
    business_fields = dict(skill_result.get("business_license_fields") or {})
    tobacco_fields = dict(skill_result.get("tobacco_license_fields") or {})
    source_evidence = dict(skill_result.get("source_evidence") or {})
    source = dict(source_evidence.get("source") or {})
    comparison = dict(skill_result.get("comparison") or {})
    return {
        "task_id": review_result.task_id,
        "source_record_id": source.get("record_id"),
        "source_attachment_ref_id": source.get("attachment_ref_id"),
        "source_url": source_evidence.get("source_url"),
        "tenant": source.get("tenant"),
        "document_type": review_result.document_type,
        "subject_name": business_fields.get("subject_name") or tobacco_fields.get("subject_name"),
        "review_status": review_result.status.value,
        "risk_level": review_result.risk_level.value,
        "needs_manual_review": int(review_result.needs_manual_review),
        "summary": review_result.summary,
        "rule_results_json": _rule_results_json(review_result),
        "comparison_json": _json_dumps(comparison),
        "business_license_fields_json": _json_dumps(business_fields),
        "tobacco_license_fields_json": _json_dumps(tobacco_fields),
        "source_evidence_json": _json_dumps(source_evidence),
        "created_at": review_result.created_at.isoformat(),
        "updated_at": review_result.updated_at.isoformat(),
    }


def _tobacco_consistency_projection_values(projection: dict[str, Any]) -> tuple[Any, ...]:
    return (
        projection["task_id"],
        projection["source_record_id"],
        projection["source_attachment_ref_id"],
        projection["source_url"],
        projection["tenant"],
        projection["document_type"],
        projection["subject_name"],
        projection["review_status"],
        projection["risk_level"],
        projection["needs_manual_review"],
        projection["summary"],
        projection["rule_results_json"],
        projection["comparison_json"],
        projection["business_license_fields_json"],
        projection["tobacco_license_fields_json"],
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
        "extraction_metadata_json": _json_dumps(extraction_metadata),
        "source_evidence_json": _json_dumps(source_evidence),
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


def _is_today(value: Any) -> bool:
    return str(value or "").startswith(date.today().isoformat())
