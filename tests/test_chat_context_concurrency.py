"""Tests for concurrent context-KPI execution in the chat path (CLI-143).

The context KPIs are independent read-only queries fanned out with
asyncio.gather instead of a sequential loop. These tests lock in the behavior
that must be preserved across that change:

- output order is stable (matches LLM input order),
- invalid KPI SQL is skipped (no result),
- per-KPI query failures are swallowed (no result, request not failed),
- the queries actually run concurrently, not one-after-another,
- the semaphore bounds how many run at once.

No pytest-asyncio in this project — coroutines are driven via asyncio.run,
matching the style of the other route tests.
"""

import asyncio

import app.api.chat_routes as cr
from app.api.chat_routes import _run_context_kpi
from app.llm.response_schema import ContextKPI


def _gather(kpis, concurrency):
    """Run the KPIs through the gather path on a fresh loop.

    The semaphore is created inside the coroutine: on Python 3.10 an
    asyncio.Semaphore binds to the running loop at construction time, so it must
    be built once asyncio.run has a loop going.
    """

    async def _main():
        sem = asyncio.Semaphore(concurrency)
        return await asyncio.wait_for(
            asyncio.gather(*(_run_context_kpi(k, sem) for k in kpis)), timeout=5
        )

    return asyncio.run(_main())


def _run_one(kpi):
    """Drive a single KPI through the helper on a fresh loop."""

    async def _main():
        return await _run_context_kpi(kpi, asyncio.Semaphore(8))

    return asyncio.run(_main())


def test_invalid_kpi_skipped(monkeypatch):
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (False, "bad"))
    result = _run_one(ContextKPI(sql="SELECT 1", label="X"))
    assert result is None


def test_failed_kpi_swallowed(monkeypatch):
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    monkeypatch.setattr(cr, "ensure_limit", lambda sql, max_limit=1: sql)

    async def boom(sql):
        raise RuntimeError("clickhouse down")

    monkeypatch.setattr(cr, "async_query_value", boom)
    result = _run_one(ContextKPI(sql="SELECT 1", label="X"))
    assert result is None


def test_failed_previous_does_not_fail_primary(monkeypatch):
    """A failing previous_sql must not lose the primary KPI value."""
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    monkeypatch.setattr(cr, "ensure_limit", lambda sql, max_limit=1: sql)

    async def query(sql):
        if "PREV" in sql:
            raise RuntimeError("prev failed")
        return 42

    monkeypatch.setattr(cr, "async_query_value", query)
    kpi = ContextKPI(sql="SELECT cur", label="X", previous_sql="SELECT PREV")
    result = _run_one(kpi)
    assert result is not None
    assert result.value == 42
    assert result.previous_value is None


def test_order_stable_and_concurrent(monkeypatch):
    """gather over KPIs preserves input order, skips invalid, and overlaps."""
    monkeypatch.setattr(cr, "ensure_limit", lambda sql, max_limit=1: sql)
    # KPI "bad" is invalid; everything else is valid.
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (("bad" not in sql), None))

    active = 0
    max_active = 0

    async def query(sql):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)  # hold the slot so overlap is observable
        active -= 1
        return sql  # echo back so we can check ordering

    monkeypatch.setattr(cr, "async_query_value", query)

    kpis = [
        ContextKPI(sql="SELECT a", label="A"),
        ContextKPI(sql="SELECT bad", label="B"),  # invalid → skipped
        ContextKPI(sql="SELECT c", label="C"),
        ContextKPI(sql="SELECT d", label="D"),
    ]
    results = _gather(kpis, cr._CONTEXT_KPI_CONCURRENCY)
    kept = [r for r in results if r is not None]

    # Invalid one dropped, order of the rest preserved.
    assert [r.label for r in kept] == ["A", "C", "D"]
    # They ran concurrently (sequential would peak at 1).
    assert max_active > 1


def test_concurrency_is_bounded(monkeypatch):
    """The semaphore caps how many KPIs hit the DB at once."""
    monkeypatch.setattr(cr, "validate_sql", lambda sql: (True, None))
    monkeypatch.setattr(cr, "ensure_limit", lambda sql, max_limit=1: sql)

    active = 0
    max_active = 0

    async def query(sql):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return 1

    monkeypatch.setattr(cr, "async_query_value", query)

    kpis = [ContextKPI(sql=f"SELECT {i}", label=str(i)) for i in range(20)]
    _gather(kpis, 3)
    assert max_active <= 3
