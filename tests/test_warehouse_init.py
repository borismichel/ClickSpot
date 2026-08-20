"""Automatic ClickHouse schema bootstrap (app/warehouse_init.py).

A fresh `docker compose up` without the demo profile starts with only the
empty `bronze` database from CLICKHOUSE_DB — these tests pin that the init DDL
the backend now runs automatically is complete (all five databases) and
idempotent by construction (every statement IF NOT EXISTS), so running it on
every startup is safe."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app import warehouse_init
from app.warehouse_init import (
    INIT_SQL_PATH,
    bootstrap_client,
    ensure_schema,
    ensure_schema_best_effort,
    iter_statements,
)


def _statements() -> list[str]:
    return list(iter_statements(INIT_SQL_PATH.read_text()))


def test_every_statement_is_idempotent_ddl():
    stmts = _statements()
    assert len(stmts) >= 46  # 5 databases + 41 bronze tables, at minimum
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


def test_bootstrap_client_connects_without_a_default_database(monkeypatch):
    """Regression: init must NOT go through app.db's shared client, which pins
    database="silver" — on a fresh stack silver doesn't exist yet, so that
    client fails with UNKNOWN_DATABASE before any DDL could run."""
    import clickhouse_connect

    monkeypatch.setenv("CLICKHOUSE_USER", "u")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "p")
    captured = {}

    def fake_get_client(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(clickhouse_connect, "get_client", fake_get_client)
    bootstrap_client()
    assert "database" not in captured


def test_bootstrap_client_refuses_missing_credentials(monkeypatch):
    monkeypatch.delenv("CLICKHOUSE_USER", raising=False)
    monkeypatch.delenv("CLICKHOUSE_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="CLICKHOUSE_USER"):
        bootstrap_client()


def test_best_effort_init_never_raises(monkeypatch):
    """An external-mode warehouse user may lack CREATE DATABASE rights, and
    from source ClickHouse may not be up yet — init failure must not block
    a startup or launch."""
    monkeypatch.setattr(
        warehouse_init,
        "bootstrap_client",
        lambda: (_ for _ in ()).throw(RuntimeError("no CH")),
    )
    assert ensure_schema_best_effort("test") is False


def test_best_effort_init_runs_the_ddl_and_closes_the_client(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(warehouse_init, "bootstrap_client", lambda: client)
    assert ensure_schema_best_effort("test") is True
    assert client.command.call_count == len(_statements())
    client.close.assert_called_once()
