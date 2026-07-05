"""OSD phase 5 — guardrail and eval tests (CLI-131).

Covers three requirements:

1. **Widget-cap surfacing** (guardrail): the `truncated` flag is always set when the
   LLM over-produces, and `widget_count` always equals `len(widgets)` — no silent
   truncation regardless of how many widgets the model returned.

2. **Schema-only invariant** (guardrail): the LLM context for generation never
   contains row-data values.  This is enforced structurally by the implementation
   (the runner's results are used only for `columns` / `row_count`, never fed back to
   the model), but these tests make it explicit and will catch future regressions.

3. **Eval set** (regression): a small parametrised set of
   (description → expected widget shapes / viz types) that exercises the full
   ``generate_dashboard_spec`` pipeline with realistic-looking plans.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.llm.dashboard_spec import (
    MAX_WIDGETS,
    MIN_WIDGETS,
    DashboardSpec,
    build_dashboard_prompt,
    generate_dashboard_spec,
)
from app.llm.providers import LLMProvider
from app.llm.response_schema import ChatSQLResponse
from app.spaces.config import DataSpaceConfig, GrainConfig

# All test queries target this view — registered in the allow_view fixture.
VIEW = "gold.ds_test_space"

# Sentinel value that represents private row data.  If this string appears in any
# prompt or message captured from the LLM provider, the schema-only invariant has
# been broken.
_SENTINEL = "PRIVATE_ROW_DATA_7a3f9b2e"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def space() -> DataSpaceConfig:
    return DataSpaceConfig(
        id="test_space",
        name="Test Space",
        grain=GrainConfig(entity="dim_deals", key="deal_id", columns=["amount", "dealstage"]),
    )


@pytest.fixture(autouse=True)
def allow_view():
    """Register the test space VIEW with the SQL validator (mirrors prod behaviour)."""
    from app.llm.sql_validator import ALLOWED_TABLES

    added = VIEW not in ALLOWED_TABLES
    ALLOWED_TABLES.add(VIEW)
    yield
    if added:
        ALLOWED_TABLES.discard(VIEW)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

# Default widget role per viz type — matches the composition grammar (CLI-155).
_ROLE_FOR_VIZ = {
    "number": "kpi",
    "line": "trend",
    "bar": "breakdown",
    "funnel": "flow",
    "table": "detail",
    "comparison": "breakdown",
}


def _widget(title: str, sql: str, viz: str = "table", role: str | None = None) -> dict:
    return {
        "title": title,
        "intent": f"answer {title}",
        "sql": sql,
        "role": role or _ROLE_FOR_VIZ.get(viz, "breakdown"),
        "viz_type": viz,
        "encoding": {"x": "dealstage", "y": ["amount"]},
    }


def _plan(n: int, viz: str = "table") -> dict:
    return {
        "dashboard_filters": ["dealstage"],
        "widgets": [
            _widget(f"w{i}", f"SELECT amount FROM {VIEW} WHERE deal_id = '{i}'", viz)
            for i in range(n)
        ],
    }


class FakeProvider(LLMProvider):
    def __init__(self, plan: dict, repair_sql: str | None = None):
        self._plan = plan
        self._repair_sql = repair_sql

    async def generate_tool(self, **kwargs: Any) -> dict:
        return self._plan

    async def generate(self, messages: list[dict], system_prompt: str | None = None) -> ChatSQLResponse:
        return ChatSQLResponse(
            sql=self._repair_sql or f"SELECT amount FROM {VIEW}",
            viz="table",
            title="repaired",
            explanation="repaired",
        )


class FakeRunner:
    def __init__(
        self,
        behavior: dict | None = None,
        default: list[dict] | None = None,
    ):
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


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Widget-cap surfacing
# ---------------------------------------------------------------------------

def test_cap_at_min_widgets_no_truncation(space):
    """Exactly MIN_WIDGETS (6) returned by LLM → no truncation, correct count."""
    spec = _run(generate_dashboard_spec(
        space, "overview",
        provider=FakeProvider(_plan(MIN_WIDGETS)),
        run_query=FakeRunner(),
    ))
    assert spec.widget_count == MIN_WIDGETS
    assert len(spec.widgets) == MIN_WIDGETS
    assert spec.truncated is False


def test_cap_at_max_widgets_no_truncation(space):
    """Exactly MAX_WIDGETS (8) returned by LLM → no truncation, correct count."""
    spec = _run(generate_dashboard_spec(
        space, "overview",
        provider=FakeProvider(_plan(MAX_WIDGETS)),
        run_query=FakeRunner(),
    ))
    assert spec.widget_count == MAX_WIDGETS
    assert spec.truncated is False


def test_cap_over_max_truncates_and_surfaces_flag(space):
    """LLM returns 10 widgets → capped to MAX_WIDGETS, truncated=True, count correct."""
    spec = _run(generate_dashboard_spec(
        space, "overview",
        provider=FakeProvider(_plan(10)),
        run_query=FakeRunner(),
    ))
    assert spec.widget_count == MAX_WIDGETS
    assert len(spec.widgets) == MAX_WIDGETS
    assert spec.truncated is True


@pytest.mark.parametrize("n", [MIN_WIDGETS, 7, MAX_WIDGETS, 9, 12])
def test_widget_count_always_consistent_with_widgets_list(space, n):
    """widget_count == len(widgets) for any plan size — no mismatch."""
    spec = _run(generate_dashboard_spec(
        space, "overview",
        provider=FakeProvider(_plan(n)),
        run_query=FakeRunner(),
    ))
    assert spec.widget_count == len(spec.widgets), (
        f"widget_count ({spec.widget_count}) != len(widgets) ({len(spec.widgets)}) for n={n}"
    )
    if n > MAX_WIDGETS:
        assert spec.truncated is True, f"Expected truncated=True for n={n}"
    else:
        assert spec.truncated is False, f"Expected truncated=False for n={n}"


# ---------------------------------------------------------------------------
# 2. Schema-only invariant
# ---------------------------------------------------------------------------

class _CapturingProvider(LLMProvider):
    """Records every prompt/message passed to generate_tool and generate."""

    def __init__(self, plan: dict, repair_sql: str | None = None):
        self._plan = plan
        self._repair_sql = repair_sql
        self.generate_tool_calls: list[dict] = []
        self.generate_calls: list[dict] = []

    async def generate_tool(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        **kwargs: Any,
    ) -> dict:
        self.generate_tool_calls.append({
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        })
        return self._plan

    async def generate(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
    ) -> ChatSQLResponse:
        self.generate_calls.append({
            "messages": messages,
            "system_prompt": system_prompt,
        })
        return ChatSQLResponse(
            sql=self._repair_sql or f"SELECT amount FROM {VIEW}",
            viz="table",
            title="repaired",
            explanation="repaired",
        )


def test_schema_only_invariant_row_data_never_in_generate_tool_context(space):
    """Row values returned by the query runner must never appear in the LLM context.

    The runner returns the sentinel as a *value* in result rows.  Those rows are
    used only for ``columns`` / ``row_count`` in the final spec; the sentinel must
    not propagate into either the system prompt or user prompt passed to the model.
    """
    # Successful run: runner returns rows whose VALUES contain the sentinel.
    runner = FakeRunner(default=[{"amount": _SENTINEL, "dealstage": _SENTINEL}])
    provider = _CapturingProvider(_plan(6))

    _run(generate_dashboard_spec(
        space, "revenue overview",
        provider=provider, run_query=runner,
    ))

    assert provider.generate_tool_calls, "generate_tool was never called"
    for call in provider.generate_tool_calls:
        assert _SENTINEL not in call["system_prompt"], (
            "Row data appeared in generate_tool system_prompt"
        )
        assert _SENTINEL not in call["user_prompt"], (
            "Row data appeared in generate_tool user_prompt"
        )
    # Confirm the runner was actually used (rows existed but stayed out of LLM)
    assert runner.calls, "FakeRunner was never called — test did not exercise the query path"


def test_schema_only_invariant_row_data_never_in_repair_context(space):
    """Self-repair messages must never contain row-data values — only error text.

    Flow: initial SQL hits a ClickHouse error → ``_repair_sql`` is called with the
    raw error string (schema/SQL info, never row content) → the repaired SQL runs
    and returns rows containing the sentinel.  The sentinel must not appear in the
    messages captured during the repair call.
    """
    bad_sql = f"SELECT bad_col FROM {VIEW}"
    ch_exc = Exception(
        "Code: 47. DB::Exception: Unknown identifier 'bad_col' "
        "(UNKNOWN_IDENTIFIER) (version 26.2)"
    )
    # Repaired query succeeds, runner returns sentinel as a *value*.
    repair_sql = f"SELECT amount FROM {VIEW}"
    runner = FakeRunner(
        behavior={
            "bad_col": ch_exc,
            "amount": [{"amount": _SENTINEL}],
        },
    )

    plan = {"dashboard_filters": [], "widgets": [_widget("revenue", bad_sql)]}
    provider = _CapturingProvider(plan, repair_sql=repair_sql)

    _run(generate_dashboard_spec(
        space, "revenue overview",
        provider=provider, run_query=runner,
    ))

    assert provider.generate_calls, "Self-repair generate was never called"
    for call in provider.generate_calls:
        sp = call.get("system_prompt") or ""
        assert _SENTINEL not in sp, "Row data leaked into repair system_prompt"
        for msg in call["messages"]:
            content = str(msg.get("content", ""))
            assert _SENTINEL not in content, (
                f"Row data appeared in repair message: {content[:200]!r}"
            )


def test_schema_only_invariant_build_prompt_uses_config_metadata_only(space):
    """build_dashboard_prompt output contains schema metadata and no data values.

    This test documents the structural guarantee: the function is a pure transform
    of the DataSpaceConfig — it never queries the database.
    """
    prompt = build_dashboard_prompt(space)

    # Schema metadata is present
    assert "deal_id" in prompt, "Grain key must appear in prompt"
    assert "amount" in prompt, "Grain column must appear in prompt"
    assert "dealstage" in prompt, "Grain column must appear in prompt"
    assert VIEW in prompt, "Space VIEW name must appear in prompt"

    # Prompt is bounded (sanity check — a runaway prompt would dwarf schema info)
    assert len(prompt) < 20_000, f"Prompt unexpectedly large ({len(prompt)} chars)"

    # No sentinel row data can appear (structural: config carries no DB values)
    assert _SENTINEL not in prompt


# ---------------------------------------------------------------------------
# 2b. Composition contract (CLI-155 / plan C1)
# ---------------------------------------------------------------------------

def test_widget_plan_requires_role():
    """`role` is a required field on WidgetPlan — a plan without it is rejected."""
    from pydantic import ValidationError

    from app.llm.dashboard_spec import WidgetPlan

    with pytest.raises(ValidationError):
        WidgetPlan(title="t", intent="i", sql="SELECT 1", viz_type="number")

    # A valid role validates fine.
    w = WidgetPlan(title="t", intent="i", sql="SELECT 1", viz_type="number", role="kpi")
    assert w.role == "kpi"


def test_widget_plan_rejects_unknown_role():
    """The role enum is closed to the five composition roles."""
    from pydantic import ValidationError

    from app.llm.dashboard_spec import WidgetPlan

    with pytest.raises(ValidationError):
        WidgetPlan(title="t", intent="i", sql="SELECT 1", viz_type="bar", role="chart")


def test_role_propagates_to_widget_spec(space):
    """The planned `role` survives validation/execution onto the output WidgetSpec."""
    plan = {
        "dashboard_filters": [],
        "widgets": [
            _widget("KPI", f"SELECT count(*) FROM {VIEW}", "number", role="kpi"),
            _widget("Stages", f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage", "bar", role="breakdown"),
        ],
    }
    spec = _run(generate_dashboard_spec(
        space, "overview", provider=FakeProvider(plan), run_query=FakeRunner(),
    ))
    assert [w.role for w in spec.widgets] == ["kpi", "breakdown"]


def test_prompt_encodes_composition_grammar_and_drops_comparison(space):
    """The dashboard prompt states the role grammar and no longer solicits comparison."""
    prompt = build_dashboard_prompt(space)

    # The five composition roles are named.
    for role in ("kpi", "trend", "breakdown", "flow", "detail"):
        assert f'"{role}"' in prompt, f"role '{role}' missing from prompt grammar"

    # Per-viz SQL shape contracts are embedded (bar top-N, line series cap).
    assert "ORDER BY" in prompt and "LIMIT 12" in prompt, "bar top-N contract missing"
    assert "5 series" in prompt, "line series cap missing"

    # comparison is retired from the OSD vocabulary: the prompt explicitly tells
    # the model NOT to emit it rather than encouraging it (as the old prose did).
    assert 'Do NOT emit a "comparison"' in prompt, "prompt should forbid comparison widgets"


# ---------------------------------------------------------------------------
# 3. Eval set: description → expected widget shapes / viz types
# ---------------------------------------------------------------------------

_EVAL_CASES = [
    {
        "id": "sales_pipeline_overview",
        "description": "Sales pipeline health — KPIs, stage funnel, and revenue trend",
        "plan": {
            "dashboard_filters": ["dealstage", "pipeline"],
            "widgets": [
                _widget("Total ARR", f"SELECT sum(amount) FROM {VIEW}", "number"),
                _widget("Open Deal Count", f"SELECT count(*) FROM {VIEW} WHERE dealstage != 'closedwon'", "number"),
                _widget("Deals by Stage", f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage", "bar"),
                _widget("Stage Funnel", f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage ORDER BY count(*) DESC", "funnel"),
                _widget("Monthly ARR Trend", f"SELECT toStartOfMonth(today()) AS mo, sum(amount) FROM {VIEW} GROUP BY mo ORDER BY mo", "line"),
                _widget("Pipeline Table", f"SELECT dealstage, sum(amount), count(*) FROM {VIEW} GROUP BY dealstage", "table"),
            ],
        },
        "expected_viz_types": {"number", "bar", "funnel", "line", "table"},
        "expected_truncated": False,
        "min_number_widgets": 1,
    },
    {
        "id": "revenue_breakdown_with_comparison",
        "description": "Revenue breakdown by owner with won-vs-lost comparison and trend",
        "plan": {
            "dashboard_filters": ["dealstage"],
            "widgets": [
                _widget("Total Revenue", f"SELECT sum(amount) FROM {VIEW}", "number"),
                _widget("Avg Deal Size", f"SELECT avg(amount) FROM {VIEW}", "number"),
                _widget("Revenue by Stage", f"SELECT dealstage, sum(amount) FROM {VIEW} GROUP BY dealstage", "bar"),
                _widget("Won vs Lost", f"SELECT dealstage, count(*) FROM {VIEW} WHERE dealstage IN ('closedwon','closedlost') GROUP BY dealstage", "comparison"),
                _widget("Monthly Trend", f"SELECT toStartOfMonth(today()) AS mo, sum(amount) FROM {VIEW} GROUP BY mo", "line"),
                _widget("Deal Count KPI", f"SELECT count(*) FROM {VIEW}", "number"),
                _widget("Top Deals", f"SELECT dealstage, amount FROM {VIEW} ORDER BY amount DESC", "table"),
                _widget("Win Rate Trend", f"SELECT toStartOfMonth(today()) AS mo, countIf(dealstage = 'closedwon') FROM {VIEW} GROUP BY mo", "line"),
            ],
        },
        "expected_viz_types": {"number", "bar", "comparison", "line", "table"},
        "expected_truncated": False,
        "min_number_widgets": 2,
    },
    {
        "id": "over_cap_plan_must_truncate",
        "description": "Multi-angle overview that the LLM over-plans with 10 widgets",
        "plan": {
            "dashboard_filters": ["dealstage"],
            "widgets": [
                _widget(f"KPI {i}", f"SELECT count(*) FROM {VIEW} WHERE deal_id = '{i}'", "number")
                for i in range(10)
            ],
        },
        "expected_viz_types": {"number"},
        "expected_truncated": True,
        "min_number_widgets": MAX_WIDGETS,  # all 8 surviving widgets are numbers
    },
    {
        "id": "all_six_viz_types",
        "description": "Showcase dashboard exercising all six supported viz types",
        "plan": {
            "dashboard_filters": [],
            "widgets": [
                _widget("Headline KPI", f"SELECT sum(amount) FROM {VIEW}", "number"),
                _widget("Stage Bar", f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage", "bar"),
                _widget("Revenue Trend", f"SELECT toStartOfMonth(today()) AS mo, sum(amount) FROM {VIEW} GROUP BY mo", "line"),
                _widget("Stage Funnel", f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage", "funnel"),
                _widget("Won vs Lost", f"SELECT dealstage, count(*) FROM {VIEW} WHERE dealstage IN ('closedwon','closedlost') GROUP BY dealstage", "comparison"),
                _widget("Detail Table", f"SELECT dealstage, amount FROM {VIEW}", "table"),
            ],
        },
        "expected_viz_types": {"number", "bar", "line", "funnel", "comparison", "table"},
        "expected_truncated": False,
        "min_number_widgets": 1,
    },
]


@pytest.mark.parametrize("case", _EVAL_CASES, ids=[c["id"] for c in _EVAL_CASES])
def test_eval_spec_shape(space, case):
    """Eval: for each (description, plan) pair verify the output spec is well-formed."""
    provider = FakeProvider(case["plan"])
    runner = FakeRunner(default=[{"amount": 42, "dealstage": "won"}])

    spec = _run(generate_dashboard_spec(
        space, case["description"],
        provider=provider, run_query=runner,
    ))

    # Output type
    assert isinstance(spec, DashboardSpec)
    assert spec.description == case["description"]

    # Widget count in allowed range
    assert MIN_WIDGETS <= spec.widget_count <= MAX_WIDGETS, (
        f"widget_count {spec.widget_count} outside [{MIN_WIDGETS}, {MAX_WIDGETS}]"
    )

    # Truncation
    assert spec.truncated is case["expected_truncated"], (
        f"Expected truncated={case['expected_truncated']}, got {spec.truncated}"
    )

    # viz_type coverage
    actual_viz = {w.viz_type for w in spec.widgets}
    for viz in case["expected_viz_types"]:
        assert viz in actual_viz, (
            f"[{case['id']}] Expected viz_type '{viz}' missing. Got: {actual_viz}"
        )

    # KPI (number) widget minimum
    number_count = sum(1 for w in spec.widgets if w.viz_type == "number")
    assert number_count >= case["min_number_widgets"], (
        f"[{case['id']}] Expected >= {case['min_number_widgets']} 'number' widgets, got {number_count}"
    )

    # Every widget has required fields and valid viz_type
    valid_viz = {"number", "table", "bar", "line", "funnel", "comparison"}
    for w in spec.widgets:
        assert w.title, f"Widget missing title in case {case['id']}"
        assert w.intent, f"Widget missing intent in case {case['id']}"
        assert w.sql, f"Widget missing sql in case {case['id']}"
        assert w.viz_type in valid_viz, (
            f"Invalid viz_type '{w.viz_type}' in case {case['id']}"
        )
        assert w.status in {"ok", "error"}, (
            f"Invalid status '{w.status}' in case {case['id']}"
        )
        assert isinstance(w.columns, list), f"columns must be list in case {case['id']}"
        if w.status == "ok":
            assert w.row_count is not None, (
                f"row_count must be set for ok widget in case {case['id']}"
            )


# ---------------------------------------------------------------------------
# 4. C2 — deterministic post-plan composition lint (CLI-161)
# ---------------------------------------------------------------------------

from app.llm.dashboard_lint import (  # noqa: E402
    MAX_BAR_ROWS,
    analysis_signature,
    cardinality_repair_instruction,
    cardinality_violation,
    composition_warnings,
    find_duplicate_analyses,
    viz_role_warning,
)


# -- pure lint functions ----------------------------------------------------

@pytest.mark.parametrize(
    "role,viz,expect_warn",
    [
        ("kpi", "number", False),
        ("kpi", "bar", True),          # a headline number must be a number tile
        ("trend", "line", False),
        ("trend", "bar", True),
        ("breakdown", "bar", False),
        ("breakdown", "table", False),  # many-category fallback is legitimate
        ("breakdown", "number", True),
        ("flow", "funnel", False),
        ("detail", "table", False),
    ],
)
def test_viz_role_coherence(role, viz, expect_warn):
    w = viz_role_warning(role, viz)
    assert (w is not None) is expect_warn
    if expect_warn:
        # Plain-language copy (UX review): no quoted enum tokens (e.g. 'kpi',
        # 'number') leak to the user, and the raw viz enum is humanised.
        assert "'" not in w
        assert f"'{role}'" not in w and f"'{viz}'" not in w


def test_cardinality_instruction_and_violation():
    # bar over the cap → repair instruction + residual warning
    assert cardinality_repair_instruction("bar", MAX_BAR_ROWS + 1) is not None
    assert cardinality_violation("bar", MAX_BAR_ROWS + 1) is not None
    # bar exactly at the cap → fine
    assert cardinality_repair_instruction("bar", MAX_BAR_ROWS) is None
    assert cardinality_violation("bar", MAX_BAR_ROWS) is None
    # number must be exactly one row
    assert cardinality_repair_instruction("number", 3) is not None
    assert cardinality_repair_instruction("number", 1) is None
    assert cardinality_violation("number", 0) is not None
    # unknown row count (query failed) → no false positive
    assert cardinality_repair_instruction("bar", None) is None
    assert cardinality_violation("number", None) is None
    # other viz types are never cardinality-flagged here
    assert cardinality_repair_instruction("table", 500) is None
    assert cardinality_violation("line", 999) is None


def test_analysis_signature_ignores_ungrouped_queries():
    assert analysis_signature(f"SELECT sum(amount) FROM {VIEW}") is None
    sig = analysis_signature(
        f"SELECT dealstage, sum(amount) FROM {VIEW} GROUP BY dealstage ORDER BY 2 DESC LIMIT 12"
    )
    assert sig is not None
    cols, measures = sig
    assert "dealstage" in cols
    assert any("sum(amount)" == m for m in measures)


def test_find_duplicate_analyses():
    sqls = [
        f"SELECT sum(amount) FROM {VIEW}",                                            # 0: ungrouped KPI
        f"SELECT dealstage, sum(amount) FROM {VIEW} GROUP BY dealstage",              # 1
        f"SELECT dealstage, SUM(amount) FROM {VIEW}  GROUP  BY  dealstage LIMIT 12",  # 2: dup of 1 (norm)
        f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage",                 # 3: different measure
    ]
    groups = find_duplicate_analyses(sqls)
    assert groups == [[1, 2]], groups


def test_composition_warnings_role_counts():
    # healthy board: 3 KPI band + trend + 2 breakdowns + 1 detail → no warnings
    assert composition_warnings(
        ["kpi", "kpi", "kpi", "trend", "breakdown", "breakdown", "detail"]
    ) == []
    # missing KPI band
    assert any("KPI band" in w for w in composition_warnings(["breakdown", "detail"]))
    # oversized KPI band + too many tables + funnels + trends
    warns = composition_warnings(
        ["kpi"] * 5 + ["detail", "detail", "flow", "flow", "trend", "trend"]
    )
    assert any("KPI" in w for w in warns)
    assert any("detail tables" in w for w in warns)
    assert any("funnel" in w for w in warns)
    assert any("trend" in w for w in warns)


def test_composition_warnings_breakdown_count():
    # A board with a KPI band but no breakdowns explains nothing → warned.
    assert any(
        "breakdown" in w.lower()
        for w in composition_warnings(["kpi", "kpi", "trend"])
    )
    # Too many breakdowns is noise → warned.
    assert any(
        "breakdown" in w.lower()
        for w in composition_warnings(["kpi", "kpi"] + ["breakdown"] * 8)
    )
    # 2–4 breakdowns is the sanctioned range → no breakdown warning.
    for n in (2, 3, 4):
        warns = composition_warnings(["kpi", "kpi", "trend"] + ["breakdown"] * n)
        assert not any("breakdown" in w.lower() for w in warns), (n, warns)
    # A single breakdown is under the band → warned.
    assert any(
        "breakdown" in w.lower()
        for w in composition_warnings(["kpi", "kpi", "breakdown"])
    )


# -- integration through generate_dashboard_spec ----------------------------

def _one_widget_plan(sql: str, viz: str, role: str) -> dict:
    return {"dashboard_filters": [], "widgets": [_widget("w", sql, viz, role=role)]}


def test_over_wide_bar_repaired_to_top_n(space):
    """A bar returning > 12 rows is repaired via the bounded loop; the fixed SQL
    (top-N) yields <= 12 rows, so the widget stays a bar with no residual warning."""
    original = f"SELECT dealstage, count(*) AS c FROM {VIEW} GROUP BY dealstage"
    repaired = original + " ORDER BY c DESC LIMIT 12"
    provider = FakeProvider(_one_widget_plan(original, "bar", "breakdown"), repair_sql=repaired)
    runner = FakeRunner(
        behavior={"LIMIT 12": [{"dealstage": str(i), "c": i} for i in range(8)]},
        default=[{"dealstage": str(i), "c": i} for i in range(20)],
    )
    spec = _run(generate_dashboard_spec(space, "overview", provider=provider, run_query=runner))
    w = spec.widgets[0]
    assert w.viz_type == "bar"
    assert w.repaired is True
    assert w.row_count == 8
    assert w.warnings == []


def test_over_wide_bar_demoted_to_table_when_unrepairable(space):
    """When the repair still returns > 12 rows, the bar is deterministically demoted
    to a table and the widget carries a warning — never a silently-unreadable bar."""
    provider = FakeProvider(_one_widget_plan(f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage", "bar", "breakdown"))
    runner = FakeRunner(default=[{"dealstage": str(i), "c": i} for i in range(20)])
    spec = _run(generate_dashboard_spec(space, "overview", provider=provider, run_query=runner))
    w = spec.widgets[0]
    assert w.viz_type == "table", "over-wide bar should be demoted to a table"
    assert any("table" in warn for warn in w.warnings)


def test_multi_row_number_surfaces_warning(space):
    """A `number` KPI whose query returns != 1 row surfaces a warning after the
    bounded repair fails to reduce it to a single row."""
    provider = FakeProvider(_one_widget_plan(f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage", "number", "kpi"))
    runner = FakeRunner(default=[{"dealstage": "a", "c": 1}, {"dealstage": "b", "c": 2}, {"dealstage": "c", "c": 3}])
    spec = _run(generate_dashboard_spec(space, "overview", provider=provider, run_query=runner))
    w = spec.widgets[0]
    assert w.viz_type == "number"
    assert any("KPI" in warn and "3 rows" in warn for warn in w.warnings)


def test_viz_role_incoherence_surfaces_widget_warning(space):
    """A widget whose viz contradicts its role is flagged even when it runs fine."""
    provider = FakeProvider(_one_widget_plan(f"SELECT sum(amount) FROM {VIEW}", "bar", "kpi"))
    spec = _run(generate_dashboard_spec(space, "overview", provider=provider, run_query=FakeRunner()))
    # Plain-language coherence copy — the KPI/bar mismatch is surfaced without enum tokens.
    assert any("KPI" in warn and "bar chart" in warn for warn in spec.widgets[0].warnings)


def test_duplicate_analysis_surfaces_board_and_widget_warning(space):
    """Two widgets with the same GROUP BY + measure → a board warning plus a
    per-widget tag on the redundant one."""
    dup_sql = f"SELECT dealstage, sum(amount) FROM {VIEW} GROUP BY dealstage"
    plan = {
        "dashboard_filters": [],
        "widgets": [
            _widget("Rev by stage", dup_sql, "bar", role="breakdown"),
            _widget("Revenue per stage", dup_sql, "bar", role="breakdown"),
        ],
    }
    spec = _run(generate_dashboard_spec(space, "overview", provider=FakeProvider(plan), run_query=FakeRunner()))
    assert any("Duplicate analysis" in w for w in spec.warnings)
    # the second (redundant) widget is tagged; the first is left clean
    assert any("same breakdown" in w for w in spec.widgets[1].warnings)
    assert spec.widgets[0].warnings == []


def test_clean_board_has_no_warnings(space):
    """A well-composed board (KPI band + trend + breakdowns + detail) lints clean."""
    plan = {
        "dashboard_filters": [],
        "widgets": [
            _widget("Total ARR", f"SELECT sum(amount) FROM {VIEW}", "number", role="kpi"),
            _widget("Deal Count", f"SELECT count(*) FROM {VIEW}", "number", role="kpi"),
            _widget("Monthly Trend", f"SELECT toStartOfMonth(today()) AS mo, sum(amount) AS s FROM {VIEW} GROUP BY mo ORDER BY mo", "line", role="trend"),
            _widget("By Stage", f"SELECT dealstage, sum(amount) AS s FROM {VIEW} GROUP BY dealstage ORDER BY s DESC LIMIT 12", "bar", role="breakdown"),
            _widget("By Owner", f"SELECT owner, count(*) AS c FROM {VIEW} GROUP BY owner ORDER BY c DESC LIMIT 12", "bar", role="breakdown"),
            _widget("Detail", f"SELECT dealstage, amount FROM {VIEW} LIMIT 100", "table", role="detail"),
        ],
    }
    # single-row default keeps every number a valid KPI and every bar under the cap
    spec = _run(generate_dashboard_spec(space, "overview", provider=FakeProvider(plan), run_query=FakeRunner()))
    assert spec.warnings == [], spec.warnings
    assert all(w.warnings == [] for w in spec.widgets), [w.warnings for w in spec.widgets]


# ---------------------------------------------------------------------------
# 5. C5 — plan-quality composition assertions (CLI-168)
# ---------------------------------------------------------------------------
#
# The C2 tests above unit-check the pure lint functions and a few targeted flows.
# These add the four canonical *plan-quality* scenarios from the CLI-147 Plan C
# spec, asserted end-to-end through the fake-provider/fake-runner seams, so a
# regression in the wiring between the lint module and ``generate_dashboard_spec``
# (not just the pure functions) is caught: an 8-table plan is rejected, a
# 200-category bar is demoted, and the KPI band is enforced. The fourth scenario —
# the band-layout template for a canonical plan — lives in the frontend layout
# unit test (``frontend/tests/bandLayout.node.test.ts``), since layout is a pure
# frontend function (plan C3 / CLI-156).


def test_c5_lint_rejects_eight_table_plan(space):
    """An 8-widget board that is *all* detail tables violates the grammar on three
    counts — no KPI band, no breakdowns, and a pile of tables — and every one of
    those is surfaced as a board warning rather than silently accepted."""
    plan = {
        "dashboard_filters": [],
        "widgets": [
            _widget(f"Table {i}", f"SELECT dealstage, amount FROM {VIEW} WHERE deal_id = '{i}' LIMIT 100", "table", role="detail")
            for i in range(8)
        ],
    }
    spec = _run(generate_dashboard_spec(space, "everything as a table", provider=FakeProvider(plan), run_query=FakeRunner()))

    # All eight survive execution (they are valid tables) — the rejection is the
    # composition verdict, not a truncation or a per-widget failure.
    assert spec.widget_count == 8
    assert spec.truncated is False
    assert any("KPI band" in w for w in spec.warnings), spec.warnings
    assert any("breakdown" in w.lower() for w in spec.warnings), spec.warnings
    assert any("detail table" in w for w in spec.warnings), spec.warnings


def test_c5_two_hundred_category_bar_demoted_to_table(space):
    """A breakdown bar whose query returns 200 categories is unreadable; with no
    top-N repair available it is deterministically demoted to a table and the
    residual cardinality is named in the widget warning."""
    provider = FakeProvider(_one_widget_plan(f"SELECT dealstage, count(*) FROM {VIEW} GROUP BY dealstage", "bar", "breakdown"))
    runner = FakeRunner(default=[{"dealstage": str(i), "c": i} for i in range(200)])
    spec = _run(generate_dashboard_spec(space, "overview", provider=provider, run_query=runner))
    w = spec.widgets[0]
    assert w.viz_type == "table", "a 200-category bar must be demoted to a table"
    assert w.row_count == 200
    assert any("200 categories" in warn and "table" in warn for warn in w.warnings), w.warnings


def test_c5_kpi_band_enforced(space):
    """The KPI band (2–4 headline tiles) is enforced end-to-end: a board with no
    KPI tile and one over-stuffed with five are both flagged, while a proper
    3-tile band lints clean on the KPI dimension."""
    def _board_warnings(kpi_n: int) -> list[str]:
        widgets = [
            _widget(f"KPI {i}", f"SELECT count(*) FROM {VIEW} WHERE deal_id = '{i}'", "number", role="kpi")
            for i in range(kpi_n)
        ]
        # A breakdown pair keeps the *only* complaint about the KPI band, not the
        # rest of the grammar (so the assertions below isolate the band rule).
        widgets += [
            _widget("By Stage", f"SELECT dealstage, sum(amount) AS s FROM {VIEW} GROUP BY dealstage ORDER BY s DESC LIMIT 12", "bar", role="breakdown"),
            _widget("By Owner", f"SELECT owner, count(*) AS c FROM {VIEW} GROUP BY owner ORDER BY c DESC LIMIT 12", "bar", role="breakdown"),
        ]
        plan = {"dashboard_filters": [], "widgets": widgets}
        spec = _run(generate_dashboard_spec(space, "overview", provider=FakeProvider(plan), run_query=FakeRunner()))
        return spec.warnings

    # No KPI band → flagged.
    assert any("KPI band" in w for w in _board_warnings(0))
    # Over-stuffed band (5 tiles) → flagged.
    assert any("KPI" in w for w in _board_warnings(5))
    # A sanctioned 3-tile band → no KPI complaint.
    assert not any("KPI" in w for w in _board_warnings(3))
