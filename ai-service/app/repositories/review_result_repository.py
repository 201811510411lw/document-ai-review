import sqlite3
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

    def get_by_task_id(self, task_id: str) -> ReviewResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM review_results WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return ReviewResult.model_validate_json(row["payload_json"])

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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection
