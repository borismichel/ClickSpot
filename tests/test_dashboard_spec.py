"""Tests for the One Shot Dashboard spec generator (CLI-127).

Covers the validated-spec shape (incl. the 6–8 widget cap) and the bounded
per-widget SQL self-repair loop. The LLM provider and the ClickHouse query path
are both faked, so these run with no network and no analytics backend.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.llm.dashboard_spec import (
    MAX_SPEC_ROWS,
    MAX_WIDGETS,
    DashboardEvent,
    DashboardSpec,
    WidgetRegenResult,
    generate_dashboard_spec,
    regenerate_widget,
    stream_dashboard_spec,
)
from app.llm.providers import LLMProvider
from app.llm.response_schema import ChatSQLResponse
from app.spaces.config import DataSpaceConfig, GrainConfig

VIEW = "gold.ds_test_space"


@pytest.fixture
def space() -> DataSpaceConfig:
    return DataSpaceConfig(
        id="test_space",
        name="Test Space",
        grain=GrainConfig(entity="dim_deals", key="deal_id", columns=["amount", "dealstage"]),
    )


@pytest.fixture(autouse=True)
def allow_view():
    """Register the test space VIEW with the SQL validator (as prod does)."""
    from app.llm.sql_validator import ALLOWED_TABLES

    added = VIEW not in ALLOWED_TABLES
    ALLOWED_TABLES.add(VIEW)
    yield
    if added:
        ALLOWED_TABLES.discard(VIEW)


# --- fakes ---------------------------------------------------------------

class FakeProvider(LLMProvider):
    """Returns a canned dashboard plan; generate() returns a canned repair SQL."""

    def __init__(self, plan: dict, repair_sql: str | None = None):
        self._plan = plan
        self._repair_sql = repair_sql
        self.tool_calls = 0
        self.repair_calls = 0

    async def generate_tool(self, **kwargs) -> dict:
        self.tool_calls += 1
        return self._plan

    async def generate(self, messages, system_prompt=None) -> ChatSQLResponse:
        self.repair_calls += 1
        return ChatSQLResponse(
            sql=self._repair_sql or "SELECT amount FROM gold.ds_test_space",
            viz="table",
            title="repaired",
            explanation="repaired query",
        )


class FakeRunner:
    """Async query runner. ``behavior`` maps a SQL substring → rows or Exception."""

    def __init__(self, behavior: dict | None = None, default: list[dict] | None = None):
        self.behavior = behavior or {}
        self.default = default if default is not None else [{"amount": 1}]
        self.calls: list[str] = []

    async def __call__(self, sql: str) -> list[dict]:
        self.calls.append(sql)
        for needle, outcome in self.behavior.items():
            if needle in sql:
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
        return self.default


def _widget(title: str, sql: str, viz: str = "table") -> dict:
    return {
        "title": title,
        "intent": f"answer {title}",
        "sql": sql,
        "viz_type": viz,
        "encoding": {"x": "dealstage", "y": ["amount"]},
        "suggested_filters": ["dealstage"],
    }


def _run(coro):
    return asyncio.run(coro)


# --- spec shape ----------------------------------------------------------

def test_spec_shape_and_widget_cap(space):
    # Plan returns 9 valid widgets — must be capped to MAX_WIDGETS (8).
    widgets = [_widget(f"w{i}", f"SELECT amount FROM {VIEW} WHERE deal_id = '{i}'") for i in range(9)]
    plan = {"dashboard_filters": ["dealstage", "amount"], "widgets": widgets}
    provider = FakeProvider(plan)
    runner = FakeRunner(default=[{"amount": 10}])

    spec = _run(generate_dashboard_spec(space, "revenue overview", provider=provider, run_query=runner))

    assert isinstance(spec, DashboardSpec)
    assert spec.space_id == "test_space"
    assert spec.description == "revenue overview"
    assert spec.widget_count == MAX_WIDGETS == 8
    assert len(spec.widgets) == 8
    assert spec.truncated is True
    assert spec.dashboard_filters == ["dealstage", "amount"]
    assert runner.calls and len(runner.calls) == 8  # each surviving widget executed once

    w = spec.widgets[0]
    assert w.status == "ok"
    assert w.error is None
    assert w.repaired is False
    assert w.viz_type == "table"
    assert w.intent == "answer w0"
    assert w.suggested_filters == ["dealstage"]
    assert w.encoding.x == "dealstage" and w.encoding.y == ["amount"]
    assert w.columns == ["amount"]
    assert w.row_count == 1
    # Rows are carried inline so the draft renders without re-querying (CLI-148).
    assert w.rows == [{"amount": 10}]
    assert "LIMIT" in w.sql.upper()  # ensure_limit injected


def test_no_truncation_when_within_cap(space):
    widgets = [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(6)]
    plan = {"dashboard_filters": [], "widgets": widgets}
    spec = _run(
        generate_dashboard_spec(space, "x", provider=FakeProvider(plan), run_query=FakeRunner())
    )
    assert spec.widget_count == 6
    assert spec.truncated is False


def test_carried_rows_are_bounded(space):
    # A widget returning more than the cap carries only the first MAX_SPEC_ROWS,
    # while row_count still reflects the true (bounded-by-ensure_limit) result.
    big = [{"amount": i} for i in range(MAX_SPEC_ROWS + 50)]
    plan = {"dashboard_filters": [], "widgets": [_widget("big", f"SELECT amount FROM {VIEW}")]}
    spec = _run(
        generate_dashboard_spec(
            space, "x", provider=FakeProvider(plan), run_query=FakeRunner(default=big)
        )
    )
    w = spec.widgets[0]
    assert w.status == "ok"
    assert len(w.rows) == MAX_SPEC_ROWS
    assert w.rows[0] == {"amount": 0}
    assert w.row_count == MAX_SPEC_ROWS + 50


def test_error_widget_carries_no_rows(space):
    # A widget that fails validation and can't be repaired carries an empty set.
    bad = _widget("broken", f"SELECT * FROM {VIEW}")  # SELECT * fails the validator
    plan = {"dashboard_filters": [], "widgets": [bad]}
    provider = FakeProvider(plan, repair_sql=f"SELECT * FROM {VIEW}")  # still invalid
    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=FakeRunner()))
    w = spec.widgets[0]
    assert w.status == "error"
    assert w.rows == []


# --- self-repair ---------------------------------------------------------

def test_self_repair_fixes_invalid_sql(space):
    # Initial SQL fails the validator (SELECT *). Repair returns a valid query.
    bad = _widget("revenue", f"SELECT * FROM {VIEW}")
    plan = {"dashboard_filters": [], "widgets": [bad]}
    provider = FakeProvider(plan, repair_sql=f"SELECT amount FROM {VIEW}")
    runner = FakeRunner(default=[{"amount": 5}])

    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=runner))

    w = spec.widgets[0]
    assert w.status == "ok"
    assert w.repaired is True
    assert provider.repair_calls == 1  # exactly one repair attempt
    assert "SELECT amount" in w.sql
    assert "LIMIT" in w.sql.upper()
    assert w.columns == ["amount"]
    # The invalid SQL is never executed; only the repaired one runs.
    assert len(runner.calls) == 1


def test_self_repair_is_bounded_to_one_retry(space):
    # Initial AND repaired SQL both fail validation → widget ends in error,
    # and we only ever attempt repair once.
    bad = _widget("revenue", f"SELECT * FROM {VIEW}")
    plan = {"dashboard_filters": [], "widgets": [bad]}
    provider = FakeProvider(plan, repair_sql=f"SELECT * FROM {VIEW}")  # still invalid
    runner = FakeRunner()

    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=runner))

    w = spec.widgets[0]
    assert w.status == "error"
    assert w.repaired is True
    assert w.error and "validation" in w.error.lower()
    assert provider.repair_calls == 1  # bounded — no second retry
    assert runner.calls == []  # neither invalid SQL was executed


def test_self_repair_on_clickhouse_error(space):
    # SQL passes the validator but ClickHouse rejects it; repair targets a
    # different column that executes cleanly. Client gets a sanitized error only
    # if it still fails — here it succeeds after repair.
    ch_exc = Exception(
        "Code: 47. DB::Exception: Unknown identifier (UNKNOWN_IDENTIFIER) (version 26.2)"
    )
    bad = _widget("revenue", f"SELECT amount FROM {VIEW}")
    plan = {"dashboard_filters": [], "widgets": [bad]}
    provider = FakeProvider(plan, repair_sql=f"SELECT dealstage FROM {VIEW}")
    runner = FakeRunner(
        behavior={"amount": ch_exc, "dealstage": [{"dealstage": "won"}]},
    )

    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=runner))

    w = spec.widgets[0]
    assert w.status == "ok"
    assert w.repaired is True
    assert provider.repair_calls == 1
    assert "dealstage" in w.sql
    assert w.columns == ["dealstage"]


def test_clickhouse_error_surfaces_sanitized_message(space):
    # Both attempts hit ClickHouse errors → widget errors with a sanitized
    # message (no raw server text / version / paths leaked to the client).
    ch_exc = Exception(
        "Code: 60. DB::Exception: Table silver.secret doesn't exist. "
        "(UNKNOWN_TABLE) (version 26.2.5.45)"
    )
    bad = _widget("revenue", f"SELECT amount FROM {VIEW}")
    plan = {"dashboard_filters": [], "widgets": [bad]}
    provider = FakeProvider(plan, repair_sql=f"SELECT dealstage FROM {VIEW}")
    runner = FakeRunner(behavior={VIEW: ch_exc})  # every query against the view fails

    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=runner))

    w = spec.widgets[0]
    assert w.status == "error"
    assert w.error == "ClickHouse error 60: UNKNOWN_TABLE"
    assert "version" not in w.error
    assert "silver.secret" not in w.error


# --- streaming progress events (CLI-128) ---------------------------------

def _collect_events(coro_factory) -> list[DashboardEvent]:
    async def run():
        return [ev async for ev in coro_factory()]

    return _run(run())


def test_stream_event_sequence_three_widgets(space):
    # Three valid widgets → planning, one bulk running tick, then one
    # completion-counted validated event per widget (any order), then done.
    widgets = [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(3)]
    plan = {"dashboard_filters": ["dealstage"], "widgets": widgets}
    provider = FakeProvider(plan)
    runner = FakeRunner(default=[{"amount": 1}])

    events = _collect_events(
        lambda: stream_dashboard_spec(
            space, "x", provider=provider, run_query=runner, min_widgets=3
        )
    )

    # Framing events are deterministic; the middle validated burst is not ordered.
    assert events[0].stage == "planning"
    assert (events[1].stage, events[1].total, events[1].completed) == ("running", 3, 0)
    assert events[-1].stage == "done" and events[-1].total == 3

    validated = [e for e in events if e.stage == "validated"]
    assert len(validated) == 3
    # Every widget lands exactly once, index-tagged, with a monotonically rising
    # completed tally (1..3) regardless of the order they finish in.
    assert {e.index for e in validated} == {1, 2, 3}
    assert sorted(e.completed for e in validated) == [1, 2, 3]
    assert all(e.total == 3 for e in validated)
    assert {e.widget_title for e in validated} == {"w0", "w1", "w2"}
    assert all(e.error is None for e in events)

    # The terminal event carries the full validated spec, in planned order.
    done = events[-1]
    assert done.spec is not None
    assert done.spec.widget_count == 3
    assert [w.title for w in done.spec.widgets] == ["w0", "w1", "w2"]
    assert [w.status for w in done.spec.widgets] == ["ok", "ok", "ok"]
    assert done.spec.dashboard_filters == ["dealstage"]


def test_stream_parallelizes_and_preserves_order(space):
    # CLI-152: widgets finalize concurrently (bounded), so completion order need
    # not match planned order — but the spec must still be assembled in order.
    import asyncio
    import re

    n = 6
    # Distinct SQL per widget so the runner can key its delay off the index.
    widgets = [_widget(f"w{i}", f"SELECT amount FROM {VIEW} WHERE amount > {i}") for i in range(n)]
    plan = {"dashboard_filters": [], "widgets": widgets}
    provider = FakeProvider(plan)

    state = {"active": 0, "peak": 0}

    async def runner(sql: str) -> list[dict]:
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        i = int(re.search(r"amount > (\d+)", sql).group(1))
        await asyncio.sleep(0.02 * (n - i))  # later widgets finish first
        state["active"] -= 1
        return [{"amount": 1}]

    events = _collect_events(
        lambda: stream_dashboard_spec(
            space, "x", provider=provider, run_query=runner, max_concurrency=4
        )
    )

    # Bounded fan-out genuinely overlapped work, capped at the concurrency limit.
    assert state["peak"] > 1
    assert state["peak"] <= 4

    validated = [e for e in events if e.stage == "validated"]
    assert len(validated) == n
    # Completion order differs from planned order (proves no serial waiting)…
    assert [e.index for e in validated] != list(range(1, n + 1))
    # …yet the terminal spec is still in planned order.
    done = events[-1]
    assert [w.title for w in done.spec.widgets] == [f"w{i}" for i in range(n)]


def test_stream_surfaces_widget_error(space):
    # A widget whose SQL fails validation and whose repair also fails surfaces a
    # sanitized error on its 'validated' event (and status 'error' in the spec).
    bad = _widget("revenue", f"SELECT * FROM {VIEW}")
    plan = {"dashboard_filters": [], "widgets": [bad]}
    provider = FakeProvider(plan, repair_sql=f"SELECT * FROM {VIEW}")  # still invalid
    runner = FakeRunner()

    events = _collect_events(
        lambda: stream_dashboard_spec(
            space, "x", provider=provider, run_query=runner, min_widgets=1
        )
    )

    validated = [e for e in events if e.stage == "validated"]
    assert len(validated) == 1
    assert validated[0].error and "validation" in validated[0].error.lower()

    done = events[-1]
    assert done.stage == "done"
    assert done.spec.widgets[0].status == "error"


def test_stream_route_serializes_sse(space, monkeypatch):
    # End-to-end SSE framing: the route streams 'data: {json}\n\n' lines with the
    # text/event-stream content type. The engine is stubbed so no provider /
    # ClickHouse is needed — this guards the wiring + serialization only.
    from fastapi.testclient import TestClient

    import app.spaces.routes_dashboards as routes

    async def fake_stream(config, description, *, provider=None, **kwargs):
        yield DashboardEvent(stage="planning")
        yield DashboardEvent(stage="running", index=1, total=1, widget_title="w0")
        yield DashboardEvent(stage="validated", index=1, total=1, widget_title="w0")
        yield DashboardEvent(
            stage="done",
            total=1,
            spec=DashboardSpec(
                space_id="test_space",
                description=description,
                dashboard_filters=[],
                widgets=[],
                widget_count=0,
                llm_ms=0,
            ),
        )

    monkeypatch.setattr(routes, "get_space", lambda sid: space)
    monkeypatch.setattr("app.llm.providers.get_provider", lambda: object())
    monkeypatch.setattr("app.llm.dashboard_spec.stream_dashboard_spec", fake_stream)

    from app.main import app

    client = TestClient(app)
    res = client.post(
        "/api/v1/spaces/test_space/dashboard/spec/stream",
        json={"description": "revenue overview"},
    )

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    frames = [f for f in res.text.split("\n\n") if f.strip()]
    assert all(f.startswith("data: ") for f in frames)
    stages = [json.loads(f[len("data: "):])["stage"] for f in frames]
    assert stages == ["planning", "running", "validated", "done"]


# --- widget-floor enforcement (CLI-153) ----------------------------------

class SequenceProvider(LLMProvider):
    """Returns a different canned plan on each successive generate_tool call."""

    def __init__(self, plans: list[dict]):
        self._plans = plans
        self.tool_calls = 0

    async def generate_tool(self, **kwargs) -> dict:
        plan = self._plans[min(self.tool_calls, len(self._plans) - 1)]
        self.tool_calls += 1
        return plan

    async def generate(self, messages, system_prompt=None) -> ChatSQLResponse:
        return ChatSQLResponse(sql=f"SELECT amount FROM {VIEW}", viz="table", title="r", explanation="r")


def test_zero_widget_plan_emits_error_and_no_done(space):
    # An empty plan is a hard failure: a single 'error' event, never a 'done'.
    plan = {"dashboard_filters": [], "widgets": []}
    provider = FakeProvider(plan)

    events = _collect_events(
        lambda: stream_dashboard_spec(space, "x", provider=provider, run_query=FakeRunner())
    )

    assert [e.stage for e in events] == ["planning", "error"]
    assert events[-1].error and "did not return any widgets" in events[-1].error
    assert all(e.stage != "done" for e in events)
    # No re-ask on a zero-widget plan — one planning call only.
    assert provider.tool_calls == 1


def test_zero_widget_plan_raises_in_nonstreaming_wrapper(space):
    plan = {"dashboard_filters": [], "widgets": []}
    with pytest.raises(ValueError, match="did not return any widgets"):
        _run(generate_dashboard_spec(space, "x", provider=FakeProvider(plan), run_query=FakeRunner()))


def test_short_plan_reasks_once_and_recovers(space):
    # First plan is short (2 widgets); the single re-ask returns a full 6-widget
    # plan, which is accepted with no note.
    short = {"dashboard_filters": [], "widgets": [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(2)]}
    full = {"dashboard_filters": [], "widgets": [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(6)]}
    provider = SequenceProvider([short, full])

    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=FakeRunner()))

    assert provider.tool_calls == 2  # exactly one re-ask
    assert spec.widget_count == 6
    assert spec.note is None


def test_short_plan_reask_still_short_is_accepted_with_note(space):
    # Both attempts return fewer than MIN_WIDGETS → accept the best one, set a note.
    short = {"dashboard_filters": [], "widgets": [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(2)]}
    provider = SequenceProvider([short, short])

    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=FakeRunner()))

    assert provider.tool_calls == 2  # bounded to a single re-ask
    assert spec.widget_count == 2
    assert spec.note and "target 6 widgets" in spec.note


def test_reask_never_regresses_widget_count(space):
    # If the re-ask returns fewer widgets than the first plan, keep the first.
    first = {"dashboard_filters": [], "widgets": [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(4)]}
    worse = {"dashboard_filters": [], "widgets": [_widget("w0", f"SELECT amount FROM {VIEW}")]}
    provider = SequenceProvider([first, worse])

    spec = _run(generate_dashboard_spec(space, "x", provider=provider, run_query=FakeRunner()))

    assert spec.widget_count == 4  # first plan retained, not the smaller re-ask


def test_stream_route_404_for_unknown_space(monkeypatch):
    from fastapi.testclient import TestClient

    import app.spaces.routes_dashboards as routes

    monkeypatch.setattr(routes, "get_space", lambda sid: None)

    from app.main import app

    client = TestClient(app)
    res = client.post(
        "/api/v1/spaces/nope/dashboard/spec/stream",
        json={"description": "x"},
    )
    assert res.status_code == 404


# --- per-widget regenerate (CLI-159) -------------------------------------

class SeqProvider(LLMProvider):
    """generate() returns a queued sequence of SQL strings, one per call."""

    def __init__(self, sqls: list[str]):
        self._sqls = list(sqls)
        self.calls: list[list[dict]] = []

    async def generate_tool(self, **kwargs) -> dict:  # not used here
        raise AssertionError("regenerate must not call generate_tool")

    async def generate(self, messages, system_prompt=None) -> ChatSQLResponse:
        self.calls.append(messages)
        sql = self._sqls.pop(0) if self._sqls else f"SELECT amount FROM {VIEW}"
        return ChatSQLResponse(sql=sql, viz="table", title="regen", explanation="")


def test_regenerate_repairs_failed_widget(space):
    # One-click repair: the widget's SQL failed; the model returns valid SQL that
    # runs cleanly. A single LLM call (the regenerate) is enough — no extra repair.
    provider = SeqProvider([f"SELECT amount FROM {VIEW}"])
    runner = FakeRunner(default=[{"amount": 7}])

    result = _run(
        regenerate_widget(
            space,
            intent="total revenue",
            sql=f"SELECT * FROM {VIEW}",
            error="SQL validation failed: SELECT * is not allowed",
            provider=provider,
            run_query=runner,
        )
    )

    assert isinstance(result, WidgetRegenResult)
    assert result.status == "ok"
    assert result.error is None
    assert result.repaired is False  # first regenerate already valid
    assert "SELECT amount" in result.sql
    assert "LIMIT" in result.sql.upper()  # ensure_limit injected
    assert result.columns == ["amount"]
    assert result.row_count == 1
    assert len(provider.calls) == 1
    # The error text was fed back to the model for repair.
    assert "validation failed" in provider.calls[0][-1]["content"]


def test_regenerate_follows_instruction(space):
    # Iteration loop: a user instruction ("make this monthly") is passed through
    # to the model even when there is no error.
    provider = SeqProvider([f"SELECT toStartOfMonth(closedate) AS m, sum(amount) AS amount FROM {VIEW} GROUP BY m"])
    runner = FakeRunner(default=[{"m": "2026-01-01", "amount": 5}])

    result = _run(
        regenerate_widget(
            space,
            intent="revenue trend",
            sql=f"SELECT amount FROM {VIEW}",
            instruction="make this monthly",
            provider=provider,
            run_query=runner,
        )
    )

    assert result.status == "ok"
    assert result.repaired is False
    assert "toStartOfMonth" in result.sql
    feedback = provider.calls[0][-1]["content"]
    assert "make this monthly" in feedback
    assert "failed with this error" not in feedback  # no error signal supplied


def test_regenerate_bounded_self_repair(space):
    # Regenerated SQL still fails the validator → exactly one bounded repair runs.
    # Both attempts are invalid here, so the widget ends in error.
    provider = SeqProvider([f"SELECT * FROM {VIEW}", f"SELECT * FROM {VIEW}"])
    runner = FakeRunner()

    result = _run(
        regenerate_widget(
            space,
            intent="revenue",
            sql=f"SELECT * FROM {VIEW}",
            error="boom",
            provider=provider,
            run_query=runner,
        )
    )

    assert result.status == "error"
    assert result.repaired is True
    assert result.error and "validation" in result.error.lower()
    assert len(provider.calls) == 2  # one regenerate + one bounded repair
    assert runner.calls == []  # invalid SQL is never executed


def test_regenerate_sanitizes_clickhouse_error(space):
    # Both attempts hit a ClickHouse error → the client gets a sanitized message
    # only (no server version / table names leaked).
    ch_exc = Exception(
        "Code: 60. DB::Exception: Table silver.secret doesn't exist. "
        "(UNKNOWN_TABLE) (version 26.2.5.45)"
    )
    provider = SeqProvider([f"SELECT amount FROM {VIEW}", f"SELECT dealstage FROM {VIEW}"])
    runner = FakeRunner(behavior={VIEW: ch_exc})

    result = _run(
        regenerate_widget(
            space,
            intent="revenue",
            sql=f"SELECT amount FROM {VIEW}",
            error="prior failure",
            provider=provider,
            run_query=runner,
        )
    )

    assert result.status == "error"
    assert result.error == "ClickHouse error 60: UNKNOWN_TABLE"
    assert "version" not in result.error and "silver.secret" not in result.error


def test_regenerate_route_wiring(space, monkeypatch):
    from fastapi.testclient import TestClient

    import app.spaces.routes_dashboards as routes

    async def fake_regen(config, intent, sql, *, error=None, instruction=None, provider=None):
        return WidgetRegenResult(
            intent=intent,
            sql=f"SELECT amount FROM {VIEW}",
            status="ok",
            columns=["amount"],
            row_count=3,
        )

    monkeypatch.setattr(routes, "get_space", lambda sid: space)
    monkeypatch.setattr("app.llm.providers.get_provider", lambda: object())
    monkeypatch.setattr("app.llm.dashboard_spec.regenerate_widget", fake_regen)

    from app.main import app

    client = TestClient(app)
    res = client.post(
        "/api/v1/spaces/test_space/dashboard/widget/regenerate",
        json={"intent": "revenue", "sql": f"SELECT * FROM {VIEW}", "error": "boom"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["columns"] == ["amount"]
    assert body["row_count"] == 3


def test_regenerate_route_404_for_unknown_space(monkeypatch):
    from fastapi.testclient import TestClient

    import app.spaces.routes_dashboards as routes

    monkeypatch.setattr(routes, "get_space", lambda sid: None)

    from app.main import app

    client = TestClient(app)
    res = client.post(
        "/api/v1/spaces/nope/dashboard/widget/regenerate",
        json={"intent": "x", "sql": "SELECT 1"},
    )
    assert res.status_code == 404


def test_regenerate_route_validates_input(space, monkeypatch):
    # Empty intent / missing sql → 422 from the request model, before any work.
    from fastapi.testclient import TestClient

    import app.spaces.routes_dashboards as routes

    monkeypatch.setattr(routes, "get_space", lambda sid: space)

    from app.main import app

    client = TestClient(app)
    res = client.post(
        "/api/v1/spaces/test_space/dashboard/widget/regenerate",
        json={"intent": "", "sql": ""},
    )
    assert res.status_code == 422
