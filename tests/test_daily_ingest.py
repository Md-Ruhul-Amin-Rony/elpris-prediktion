"""Focused tests for daily_ingest bootstrap behavior."""

import importlib
import os

os.environ.setdefault("DATABASE_URL", "postgresql://example.invalid/test")
daily_ingest = importlib.import_module("daily_ingest")


class _FakeCursor:
    def __init__(self) -> None:
        self.executed_sql = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        self.executed_sql.append(sql)


class _FakeConnection:
    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()

    def cursor(self):
        return self.cursor_instance


def test_ensure_raw_tables_executes_bronze_schema_sql():
    conn = _FakeConnection()

    daily_ingest.ensure_raw_tables(conn)

    assert conn.cursor_instance.executed_sql == [daily_ingest.BRONZE_SCHEMA_SQL]
    assert "CREATE TABLE IF NOT EXISTS raw__weather" in daily_ingest.BRONZE_SCHEMA_SQL
    assert "CREATE TABLE IF NOT EXISTS raw__elpris" in daily_ingest.BRONZE_SCHEMA_SQL
