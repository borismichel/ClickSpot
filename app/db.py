"""ClickHouse connection for the analytics app."""

import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
            port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
            username=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
            database="silver",
        )
    return _client


def query_value(sql: str):
    """Execute SQL and return a single scalar value."""
    return get_client().command(sql)


def query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts."""
    result = get_client().query(sql)
    columns = result.column_names
    return [dict(zip(columns, row)) for row in result.result_rows]
