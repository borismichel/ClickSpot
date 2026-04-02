"""Run scripts/init_clickhouse.sql against the ClickHouse instance.
Usage: python scripts/init_clickhouse.py
Requires CLICKHOUSE_HOST, CLICKHOUSE_ADMIN_USER, CLICKHOUSE_ADMIN_PASSWORD in .env.
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
    # Strip comments and whitespace; skip if nothing left
    lines = [l for l in statement.strip().splitlines() if not l.strip().startswith("--")]
    stmt = "\n".join(lines).strip()
    if stmt:
        try:
            client.command(stmt)
            print(f"OK: {stmt[:60]}...")
        except Exception as e:
            print(f"FAILED: {stmt[:60]}...\nError: {e}")
            raise

print("ClickHouse bronze layer initialized.")
