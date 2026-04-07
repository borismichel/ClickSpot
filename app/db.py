"""ClickHouse connection for the analytics app."""

import asyncio
import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

_client = None


def _conn_kwargs() -> dict:
    return dict(
        host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database="silver",
    )


def get_client():
    global _client
    if _client is None:
        _client = clickhouse_connect.get_client(
            **_conn_kwargs(),
            autogenerate_session_id=False,
        )
    return _client


# --- Sync (used by legacy /api/v1/query route) ---

def query_value(sql: str):
    """Execute SQL and return a single scalar value."""
    return get_client().command(sql)


def query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts."""
    result = get_client().query(sql)
    columns = result.column_names
    return [dict(zip(columns, row)) for row in result.result_rows]


# --- Async (used by /api/v1/sql, /api/v1/chat, dashboard) ---
# Each call creates a fresh sync client via create_client (no caching)
# and runs it in a thread. This guarantees no shared session/connection.

def _isolated_query_rows(sql: str) -> list[dict]:
    client = clickhouse_connect.create_client(**_conn_kwargs(), autogenerate_session_id=False)
    try:
        result = client.query(sql)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]
    finally:
        client.close()


def _isolated_query_value(sql: str):
    client = clickhouse_connect.create_client(**_conn_kwargs(), autogenerate_session_id=False)
    try:
        return client.command(sql)
    finally:
        client.close()


async def async_query_value(sql: str):
    """Execute SQL and return a single scalar value (async, isolated client)."""
    return await asyncio.to_thread(_isolated_query_value, sql)


async def async_query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts (async, isolated client)."""
    return await asyncio.to_thread(_isolated_query_rows, sql)
