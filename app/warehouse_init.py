"""Idempotent ClickHouse schema bootstrap.

`scripts/init_clickhouse.sql` is all IF NOT EXISTS DDL (the five databases plus
the bronze tables), so it is safe to run on every startup. The backend runs it
in the FastAPI lifespan and again before each sync/apply launch; `start.sh`,
`bootstrap.sh`, `scripts/seed.py`, and `scripts/init_clickhouse.py` execute the
same statements through this module. Without this, a fresh `docker compose up`
(no demo profile) comes up with only the empty `bronze` database created by
CLICKHOUSE_DB — bronze assets insert without creating tables, and silver/gold
builds need databases only the init DDL creates.
"""

import logging
from pathlib import Path
from typing import Iterator

log = logging.getLogger("app.warehouse_init")

INIT_SQL_PATH = Path(__file__).resolve().parent.parent / "scripts" / "init_clickhouse.sql"


def iter_statements(sql_text: str) -> Iterator[str]:
    """Split a .sql file into executable statements, dropping comment lines."""
    for statement in sql_text.split(";"):
        lines = [l for l in statement.strip().splitlines() if not l.strip().startswith("--")]
        stmt = "\n".join(lines).strip()
        if stmt:
            yield stmt


def ensure_schema(client) -> int:
    """Run every statement in scripts/init_clickhouse.sql; return the count.

    All DDL is IF NOT EXISTS, so calling this against an already-initialized
    warehouse is a no-op.
    """
    count = 0
    for stmt in iter_statements(INIT_SQL_PATH.read_text()):
        try:
            client.command(stmt)
        except Exception:
            log.error("Schema init failed on: %s...", stmt[:80])
            raise
        count += 1
    return count
