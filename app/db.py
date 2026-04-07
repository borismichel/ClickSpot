"""ClickHouse connection for the analytics app.

Sync path: clickhouse-connect (used by Dagster /api/v1/query route).
Async path: raw httpx to ClickHouse HTTP API (used by /api/v1/sql, /chat, dashboard).
  - Each request is a standalone HTTP POST with no session, no shared pool.
  - This completely avoids "concurrent queries in same session" errors.
"""

import json
import os

import clickhouse_connect
import httpx
from dotenv import load_dotenv

load_dotenv()


def _ch_url() -> str:
    host = os.environ.get("CLICKHOUSE_HOST", "localhost")
    port = int(os.environ.get("CLICKHOUSE_PORT", 8123))
    return f"http://{host}:{port}"


def _ch_auth() -> tuple[str, str]:
    return (
        os.environ.get("CLICKHOUSE_USER", "default"),
        os.environ.get("CLICKHOUSE_PASSWORD", ""),
    )


# --- Sync (clickhouse-connect, used by /api/v1/query route) ---

def _new_client():
    return clickhouse_connect.create_client(
        host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
        username=os.environ.get("CLICKHOUSE_USER", "default"),
        password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
        database="silver",
        autogenerate_session_id=False,
        settings={"cancel_http_readonly_queries_on_client_close": "0"},
    )


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


# --- Async (raw httpx, no clickhouse-connect, no shared state) ---

async def async_query_value(sql: str):
    """Execute SQL and return a single scalar value (async)."""
    rows = await async_query_rows(sql)
    if not rows:
        return None
    return next(iter(rows[0].values()))


async def async_query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts (async).

    Uses a fresh httpx connection per call — no connection pooling,
    no session IDs, no shared state. Fully concurrent-safe.
    """
    url = _ch_url()
    user, password = _ch_auth()
    # FORMAT JSON returns {meta, data, rows, statistics}
    full_sql = sql.rstrip(";") + " FORMAT JSON"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            content=full_sql,
            params={"database": "silver"},
            auth=(user, password),
            headers={"Content-Type": "text/plain"},
            timeout=60.0,
        )
    if resp.status_code != 200:
        raise Exception(resp.text.strip())
    body = resp.json()
    return body.get("data", [])
