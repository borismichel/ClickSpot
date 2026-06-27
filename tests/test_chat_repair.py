"""Tests for the SQL repair loop + EXPLAIN dry-run in the chat path (CLI-144).

A query that fails validation, the EXPLAIN dry-run, or real execution used to
422 straight to the user. Now we run one EXPLAIN-guarded repair round-trip. These
tests lock in:

- happy path runs validate -> EXPLAIN -> execute with no repair LLM call,
- each failure stage (validation / EXPLAIN / execution) triggers exactly one
  repair, and a good correction recovers the query,
- the repair is capped at a single attempt; a still-bad correction surfaces the
  *original* failure,
- repair / EXPLAIN feature flags gate the new behaviour,
- Langfuse repair scores are emitted on both paths.

No pytest-asyncio in this project — coroutines are driven via asyncio.run,
matching the other route tests.
"""

import asyncio
from types import SimpleNamespace

import pytest

import app.api.chat_routes as cr
from app.api.chat_routes import SqlPipelineError, resolve_sql
from app.llm import repair as sql_repair


class FakeProvider:
    """Returns the next queued SQL string per generate() call."""

    def __init__(self, *sqls):
        self._sqls = list(sqls)
        self.calls = []

    async def generate(self, messages, system_prompt=None):
        self.calls.append(messages)
        sql = self._sqls.pop(0)
        return SimpleNamespace(
            sql=sql, explanation="e", viz="bar", title="t", context=[]
        )


@pytest.fixture(autouse=True)
def _scores(monkeypatch):
    """Capture Langfuse scores; keep ensure_limit a pass-through.

    Both feature flags default on via unset env (their real default), so tests
    that need them off patch explicitly — leaving the env-reading flag test free
    to exercise the real functions.
    """
    scores = []
    monkeypatch.setattr(cr.obs, "score", lambda name, value, **kw: scores.append((name, value)))
    monkeypatch.setattr(cr, "ensure_limit", lambda sql: sql)
    monkeypatch.delenv("CLICKSPOT_SQL_EXPLAIN_DRYRUN", raising=False)
    monkeypatch.delenv("CLICKSPOT_SQL_REPAIR", raising=False)
    return scores


def _run(provider):
    return asyncio.run(resolve_sql(provider, [{"role": "user", "content": "q"}]))


def _ok_explain():
    async def _explain(sql):
        return None
    return _explain


def test_happy_path_no_repair(monkeypatch, _scores):
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    explained = []

    async def explain(sql):
        explained.append(sql)

    async def query(sql):
        return [{"a": 1}]

    monkeypatch.setattr(cr, "async_explain", explain)
    monkeypatch.setattr(cr, "async_query_rows", query)

    provider = FakeProvider("SELECT 1")
    result = _run(provider)

    assert result.repaired is False
    assert result.rows == [{"a": 1}]
    assert len(provider.calls) == 1          # no repair round-trip
    assert explained == ["SELECT 1"]         # EXPLAIN ran on the happy path
    assert ("sql_repair_attempted", 0) in _scores


def test_explain_skipped_when_disabled(monkeypatch, _scores):
    monkeypatch.setattr(sql_repair, "explain_enabled", lambda: False)
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    called = []

    async def explain(sql):
        called.append(sql)

    async def query(sql):
        return [{"a": 1}]

    monkeypatch.setattr(cr, "async_explain", explain)
    monkeypatch.setattr(cr, "async_query_rows", query)

    _run(FakeProvider("SELECT 1"))
    assert called == []                      # EXPLAIN gated off


def test_execution_failure_repaired(monkeypatch, _scores):
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    monkeypatch.setattr(cr, "async_explain", _ok_explain())

    async def query(sql):
        if sql == "BAD":
            raise RuntimeError("Unknown column xyz")
        return [{"a": 2}]

    monkeypatch.setattr(cr, "async_query_rows", query)

    provider = FakeProvider("BAD", "GOOD")
    result = _run(provider)

    assert result.repaired is True
    assert result.sql == "GOOD"
    assert result.rows == [{"a": 2}]
    assert len(provider.calls) == 2
    assert ("sql_repair_attempted", 1) in _scores
    assert ("sql_repair_succeeded", 1) in _scores


def test_validation_failure_repaired(monkeypatch, _scores):
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (sql == "GOOD", None if sql == "GOOD" else "no"))
    monkeypatch.setattr(cr, "async_explain", _ok_explain())

    async def query(sql):
        return [{"a": 3}]

    monkeypatch.setattr(cr, "async_query_rows", query)

    result = _run(FakeProvider("BAD", "GOOD"))
    assert result.repaired is True
    assert ("sql_repair_succeeded", 1) in _scores


def test_explain_failure_repaired(monkeypatch, _scores):
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))

    async def explain(sql):
        if sql == "BAD":
            raise RuntimeError("type mismatch in JOIN")

    async def query(sql):
        return [{"a": 4}]

    monkeypatch.setattr(cr, "async_explain", explain)
    monkeypatch.setattr(cr, "async_query_rows", query)

    result = _run(FakeProvider("BAD", "GOOD"))
    assert result.repaired is True
    assert result.sql == "GOOD"


def test_single_attempt_then_original_error(monkeypatch, _scores):
    """A still-broken repair surfaces the ORIGINAL failure, capped at one retry."""
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    monkeypatch.setattr(cr, "async_explain", _ok_explain())

    async def query(sql):
        raise RuntimeError(f"boom on {sql}")

    monkeypatch.setattr(cr, "async_query_rows", query)
    monkeypatch.setattr(cr, "safe_clickhouse_error", lambda e: "sanitized")

    provider = FakeProvider("BAD1", "BAD2")
    with pytest.raises(SqlPipelineError) as exc:
        _run(provider)

    assert exc.value.stage == sql_repair.STAGE_EXECUTION
    assert exc.value.client_message == "sanitized"
    assert len(provider.calls) == 2          # exactly one repair attempt
    assert ("sql_repair_succeeded", 0) in _scores


def test_repair_disabled_fails_fast(monkeypatch, _scores):
    monkeypatch.setattr(sql_repair, "repair_enabled", lambda: False)
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    monkeypatch.setattr(cr, "async_explain", _ok_explain())
    monkeypatch.setattr(cr, "safe_clickhouse_error", lambda e: "sanitized")

    async def query(sql):
        raise RuntimeError("boom")

    monkeypatch.setattr(cr, "async_query_rows", query)

    provider = FakeProvider("BAD")
    with pytest.raises(SqlPipelineError):
        _run(provider)

    assert len(provider.calls) == 1          # no repair round-trip
    assert ("sql_repair_attempted", 0) in _scores


def test_build_repair_message_carries_sql_and_error():
    msg = sql_repair.build_repair_message("SELECT bad", "Unknown column", sql_repair.STAGE_EXECUTION)
    assert msg["role"] == "user"
    assert "SELECT bad" in msg["content"]
    assert "Unknown column" in msg["content"]
    assert "ClickHouse" in msg["content"]


def test_flags_read_env(monkeypatch):
    monkeypatch.delenv("CLICKSPOT_SQL_EXPLAIN_DRYRUN", raising=False)
    monkeypatch.delenv("CLICKSPOT_SQL_REPAIR", raising=False)
    assert sql_repair.explain_enabled() is True      # default on
    assert sql_repair.repair_enabled() is True
    monkeypatch.setenv("CLICKSPOT_SQL_EXPLAIN_DRYRUN", "0")
    monkeypatch.setenv("CLICKSPOT_SQL_REPAIR", "off")
    assert sql_repair.explain_enabled() is False
    assert sql_repair.repair_enabled() is False
