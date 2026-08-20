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
import os
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("app.warehouse_init")

INIT_SQL_PATH = Path(__file__).resolve().parent.parent / "scripts" / "init_clickhouse.sql"


def bootstrap_client():
    """A short-lived client for schema init only, with NO default database.

    app.db's shared client connects with database="silver" — on the fresh
    stack this module exists for, silver doesn't exist yet, so that client
    fails with UNKNOWN_DATABASE before any DDL could run. Same credential
    stance as app.db: refuse to fall back to the 'default' superuser.
    """
    user = os.environ.get("CLICKHOUSE_USER")
    password = os.environ.get("CLICKHOUSE_PASSWORD")
    if not user or password is None:
        raise RuntimeError(
            "CLICKHOUSE_USER and CLICKHOUSE_PASSWORD must be set (see .env.example)."
        )
    import clickhouse_connect

    return clickhouse_connect.get_client(
        host=os.environ.get("CLICKHOUSE_HOST", "localhost"),
        port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
        username=user,
        password=password,
    )


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


def ensure_schema_best_effort(context: str) -> bool:
    """Run ensure_schema on a bootstrap client; warn instead of raising.

    Init failure must never block a startup or a sync launch: from source
    ClickHouse may not be up yet (start.sh runs the same DDL), and an
    `external`-mode warehouse user may lack CREATE DATABASE rights on a
    warehouse that was initialized out of band.
    """
    try:
        client = bootstrap_client()
        try:
            ensure_schema(client)
        finally:
            client.close()
        return True
    except Exception as e:
        log.warning("ClickHouse schema init skipped (%s): %s", context, e)
        return False
