"""Automatic ClickHouse schema bootstrap (app/warehouse_init.py).

A fresh `docker compose up` without the demo profile starts with only the
empty `bronze` database from CLICKHOUSE_DB — these tests pin that the init DDL
the backend now runs automatically is complete (all five databases) and
idempotent by construction (every statement IF NOT EXISTS), so running it on
every startup is safe."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.warehouse_init import INIT_SQL_PATH, ensure_schema, iter_statements


def _statements() -> list[str]:
    return list(iter_statements(INIT_SQL_PATH.read_text()))


def test_every_statement_is_idempotent_ddl():
    stmts = _statements()
    assert len(stmts) >= 40  # 5 databases + 41 bronze tables
    for stmt in stmts:
        assert stmt.upper().startswith(
            ("CREATE DATABASE IF NOT EXISTS", "CREATE TABLE IF NOT EXISTS")
        ), f"not idempotent: {stmt[:80]}"


def test_init_creates_all_five_databases():
    dbs = {
        stmt.split()[-1]
        for stmt in _statements()
        if stmt.upper().startswith("CREATE DATABASE")
    }
    assert {"bronze", "silver", "gold", "silver_anon", "gold_anon"} <= dbs


def test_iter_statements_strips_comments_and_blanks():
    sql = (
        "-- header comment\n"
        "CREATE DATABASE IF NOT EXISTS x;\n"
        "\n"
        "-- CREATE USER commented out\n"
        ";\n"
        "CREATE TABLE IF NOT EXISTS x.t (a String)\n"
        "    ENGINE = MergeTree ORDER BY a;\n"
    )
    stmts = list(iter_statements(sql))
    assert stmts == [
        "CREATE DATABASE IF NOT EXISTS x",
        "CREATE TABLE IF NOT EXISTS x.t (a String)\n    ENGINE = MergeTree ORDER BY a",
    ]


def test_ensure_schema_executes_every_statement():
    client = MagicMock()
    count = ensure_schema(client)
    assert count == len(_statements())
    assert client.command.call_count == count


def test_ensure_schema_propagates_a_failing_statement():
    client = MagicMock()
    client.command.side_effect = [None, RuntimeError("boom")]
    with pytest.raises(RuntimeError, match="boom"):
        ensure_schema(client)
