import json
import sqlite3
from pathlib import Path

from app.models import ReviewResult


class SQLiteReviewRepository:
    def __init__(self, db_path: str | Path = "data/reviews.sqlite3") -> None:
        self.db_path = Path(db_path)
        self._init_schema()

    def save(self, review_result: ReviewResult) -> ReviewResult:
        payload = review_result.model_dump(mode="json")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO review_tasks (task_id, payload, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (
                    review_result.task_id,
                    json.dumps(payload, ensure_ascii=False),
                    review_result.updated_at.isoformat(),
                ),
            )
        return review_result

    def get(self, task_id: str) -> ReviewResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM review_tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        if row is None:
            return None
        return ReviewResult.model_validate(json.loads(row["payload"]))

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS review_tasks (
                    task_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
