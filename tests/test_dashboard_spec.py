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
    MAX_WIDGETS,
    DashboardEvent,
    DashboardSpec,
    generate_dashboard_spec,
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
    assert "LIMIT" in w.sql.upper()  # ensure_limit injected


def test_no_truncation_when_within_cap(space):
    widgets = [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(6)]
    plan = {"dashboard_filters": [], "widgets": widgets}
    spec = _run(
        generate_dashboard_spec(space, "x", provider=FakeProvider(plan), run_query=FakeRunner())
    )
    assert spec.widget_count == 6
    assert spec.truncated is False


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
    # Three valid widgets → planning, generating/validating per widget, done.
    widgets = [_widget(f"w{i}", f"SELECT amount FROM {VIEW}") for i in range(3)]
    plan = {"dashboard_filters": ["dealstage"], "widgets": widgets}
    provider = FakeProvider(plan)
    runner = FakeRunner(default=[{"amount": 1}])

    events = _collect_events(
        lambda: stream_dashboard_spec(space, "x", provider=provider, run_query=runner)
    )

    assert [(e.stage, e.index, e.total) for e in events] == [
        ("planning", None, None),
        ("generating", 1, 3),
        ("validating", 1, 3),
        ("generating", 2, 3),
        ("validating", 2, 3),
        ("generating", 3, 3),
        ("validating", 3, 3),
        ("done", None, 3),
    ]

    # Per-widget events carry the widget title; no errors on the happy path.
    assert events[1].widget_title == "w0" and events[2].widget_title == "w0"
    assert all(e.error is None for e in events)

    # The terminal event carries the full validated spec.
    done = events[-1]
    assert done.spec is not None
    assert done.spec.widget_count == 3
    assert [w.status for w in done.spec.widgets] == ["ok", "ok", "ok"]
    assert done.spec.dashboard_filters == ["dealstage"]


def test_stream_surfaces_widget_error(space):
    # A widget whose SQL fails validation and whose repair also fails surfaces a
    # sanitized error on its 'validating' event (and status 'error' in the spec).
    bad = _widget("revenue", f"SELECT * FROM {VIEW}")
    plan = {"dashboard_filters": [], "widgets": [bad]}
    provider = FakeProvider(plan, repair_sql=f"SELECT * FROM {VIEW}")  # still invalid
    runner = FakeRunner()

    events = _collect_events(
        lambda: stream_dashboard_spec(space, "x", provider=provider, run_query=runner)
    )

    validating = [e for e in events if e.stage == "validating"]
    assert len(validating) == 1
    assert validating[0].error and "validation" in validating[0].error.lower()

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
        yield DashboardEvent(stage="generating", index=1, total=1, widget_title="w0")
        yield DashboardEvent(stage="validating", index=1, total=1, widget_title="w0")
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
    assert stages == ["planning", "generating", "validating", "done"]


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
