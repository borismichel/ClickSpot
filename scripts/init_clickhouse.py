"""Run scripts/init_clickhouse.sql against the ClickHouse instance.
Usage: python scripts/init_clickhouse.py
Uses CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD from .env.

The backend runs the same DDL automatically on startup and before each sync
launch (app/warehouse_init.py) — this script remains for shell bootstrap paths
and for initializing an `external`-mode ClickHouse by hand.
"""
import os
import sys
from pathlib import Path

import clickhouse_connect
from dotenv import load_dotenv

# Make the repo root importable when run as `python scripts/init_clickhouse.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.warehouse_init import ensure_schema  # noqa: E402

load_dotenv()

client = clickhouse_connect.get_client(
    host=os.environ["CLICKHOUSE_HOST"],
    port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
    username=os.environ["CLICKHOUSE_USER"],
    password=os.environ["CLICKHOUSE_PASSWORD"],
)

count = ensure_schema(client)
print(f"ClickHouse bronze layer initialized ({count} statements).")
