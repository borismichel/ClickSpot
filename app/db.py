"""ClickHouse connection for the analytics app.

Single shared client, safe for concurrent use because:
  1. autogenerate_session_id=False globally — no session IDs sent
  2. cancel_http_readonly_queries_on_client_close=0 — no implicit sessions
Without sessions, ClickHouse treats each HTTP request independently.
"""

import asyncio
import os

import clickhouse_connect
import clickhouse_connect.common as _ch_common
from dotenv import load_dotenv

load_dotenv()

# Disable session IDs globally — prevents any client from ever
# generating a session_id, which is the root cause of
# "concurrent queries within the same session" errors.
_ch_common.set_setting("autogenerate_session_id", False)

_client = None

# Default per-query wall-clock cap for the interactive read path, in seconds.
# Bounds a runaway user query so it fails fast with TIMEOUT_EXCEEDED instead of
# holding the 2 GB memory cap for minutes (CLI-124). Applies only to this app
# client — the Dagster pipeline uses its own ClickHouse clients, so heavy
# silver/gold rebuilds are unaffected. Set CLICKHOUSE_MAX_EXECUTION_TIME=0 to
# disable.
_DEFAULT_MAX_EXECUTION_TIME = "60"


def _read_client_settings() -> dict[str, str]:
    settings = {"cancel_http_readonly_queries_on_client_close": "0"}
    max_exec = os.environ.get(
        "CLICKHOUSE_MAX_EXECUTION_TIME", _DEFAULT_MAX_EXECUTION_TIME
    ).strip()
    if max_exec and max_exec != "0":
        settings["max_execution_time"] = max_exec
    return settings


def get_client():
    global _client
    if _client is None:
        # Fail fast if credentials aren't explicitly set. The previous fallback
        # ("default" superuser with empty password) is a security trap — it
        # silently works against a fresh ClickHouse install and gives the app
        # superuser privileges. Force the operator to set CLICKHOUSE_USER /
        # CLICKHOUSE_PASSWORD via .env or environment.
        user = os.environ.get("CLICKHOUSE_USER")
        password = os.environ.get("CLICKHOUSE_PASSWORD")
        if not user or password is None:
            raise RuntimeError(
                "CLICKHOUSE_USER and CLICKHOUSE_PASSWORD must be set "
                "(see .env.example). Refusing to fall back to the 'default' "
                "ClickHouse superuser."
            )
        _client = clickhouse_connect.create_client(
            host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
            port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
            username=user,
            password=password,
            database="silver",
            autogenerate_session_id=False,
            settings=_read_client_settings(),
        )
        # Verify no session leaked in — this would cause concurrent query errors
        assert "session_id" not in _client.params, f"session_id leaked: {_client.params}"
    return _client


def query_value(sql: str):
    """Execute SQL and return a single scalar value."""
    return get_client().command(sql)


def query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts."""
    result = get_client().query(sql)
    columns = result.column_names
    return [dict(zip(columns, row)) for row in result.result_rows]


# --- Async wrappers (run sync client in thread) ---

async def async_query_value(sql: str):
    """Execute SQL and return a single scalar value (async)."""
    return await asyncio.to_thread(query_value, sql)


async def async_query_rows(sql: str) -> list[dict]:
    """Execute SQL and return rows as list of dicts (async)."""
    return await asyncio.to_thread(query_rows, sql)
