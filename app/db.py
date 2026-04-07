"""ClickHouse connection for the analytics app.

Every query creates a fresh client to avoid ClickHouse's
"concurrent queries within the same session" restriction.
Client creation is cheap (~1ms) — ClickHouse HTTP is stateless.
"""

import asyncio
import os
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()


def _conn_kwargs() -> dict:
    return dict(
        host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database="silver",
        autogenerate_session_id=False,
    )


def _new_client():
    return clickhouse_connect.create_client(**_conn_kwargs())


# --- Sync (used by /api/v1/query route) ---

def query_value(sql: str):
    """Execute SQL and return a single scalar value."""
    client = _new_client()
    try:
        return client.command(sql)
    finally:
        client.close()


def query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts."""
    client = _new_client()
    try:
        result = client.query(sql)
        columns = result.column_names
        return [dict(zip(columns, row)) for row in result.result_rows]
    finally:
        client.close()


# --- Async (used by /api/v1/sql, /api/v1/chat, dashboard) ---

async def async_query_value(sql: str):
    """Execute SQL and return a single scalar value (async, isolated client)."""
    return await asyncio.to_thread(query_value, sql)


async def async_query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts (async, isolated client)."""
    return await asyncio.to_thread(query_rows, sql)
