from app.integrations.mysql_client import MySqlFetchClient, MySqlSettings


class StubCursor:
    def __init__(self):
        self.executed_sql = None

    def execute(self, sql):
        self.executed_sql = sql

    def fetchall(self):
        return [{"uuid": "cert-business-001"}]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class StubConnection:
    def __init__(self):
        self.cursor_obj = StubCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def close(self):
        self.closed = True


def test_mysql_fetch_client_executes_sql_and_returns_dict_rows(monkeypatch):
    connection = StubConnection()
    calls = []

    def connect(**kwargs):
        calls.append(kwargs)
        return connection

    monkeypatch.setattr("app.integrations.mysql_client.pymysql.connect", connect)
    client = MySqlFetchClient(
        MySqlSettings(
            host="127.0.0.1",
            port=3306,
            user="demo",
            password="secret",
            database="ods",
        )
    )

    rows = client.fetch_all("select 1")

    assert rows == [{"uuid": "cert-business-001"}]
    assert connection.cursor_obj.executed_sql == "select 1"
    assert connection.closed is True
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["cursorclass"].__name__ == "DictCursor"
