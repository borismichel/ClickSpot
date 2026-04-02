"""Run scripts/init_clickhouse.sql against the ClickHouse instance.
Usage: python scripts/init_clickhouse.py
Requires CLICKHOUSE_HOST, CLICKHOUSE_USER (admin), CLICKHOUSE_PASSWORD in .env.
"""
import os
from pathlib import Path
import clickhouse_connect
from dotenv import load_dotenv

load_dotenv()

client = clickhouse_connect.get_client(
    host=os.environ["CLICKHOUSE_HOST"],
    port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
    username=os.environ.get("CLICKHOUSE_ADMIN_USER", "default"),
    password=os.environ.get("CLICKHOUSE_ADMIN_PASSWORD", ""),
)

sql = Path(__file__).parent / "init_clickhouse.sql"
for statement in sql.read_text().split(";"):
    stmt = statement.strip()
    if stmt:
        client.command(stmt)
        print(f"OK: {stmt[:60]}...")

print("ClickHouse bronze layer initialized.")
