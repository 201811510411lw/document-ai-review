import os
from dataclasses import dataclass
from typing import Any

import pymysql


@dataclass(frozen=True)
class MySqlSettings:
    host: str
    port: int
    user: str
    password: str
    database: str | None = None
    charset: str = "utf8mb4"
    connect_timeout: int = 10


class MySqlFetchClient:
    def __init__(self, settings: MySqlSettings) -> None:
        self.settings = settings
        self._connection = None

    def fetch_all(self, sql: str) -> list[dict[str, Any]]:
        connection = self._connect()
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return list(cursor.fetchall())

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _connect(self):
        if self._connection is not None:
            try:
                self._connection.ping(reconnect=True)
                return self._connection
            except Exception:
                self.close()
        self._connection = pymysql.connect(
            host=self.settings.host,
            port=self.settings.port,
            user=self.settings.user,
            password=self.settings.password,
            database=self.settings.database,
            charset=self.settings.charset,
            connect_timeout=self.settings.connect_timeout,
            cursorclass=pymysql.cursors.DictCursor,
        )
        return self._connection


def mysql_settings_from_env(prefix: str = "STARROCKS") -> MySqlSettings:
    return MySqlSettings(
        host=_required_env(f"{prefix}_HOST"),
        port=int(os.environ.get(f"{prefix}_PORT", "3306")),
        user=_required_env(f"{prefix}_USER"),
        password=_required_env(f"{prefix}_PASSWORD"),
        database=os.environ.get(f"{prefix}_DATABASE"),
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value
