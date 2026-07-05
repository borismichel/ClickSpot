"""One Shot Dashboard — multi-widget dashboard spec generation (OSD phase 1).

Turns a plain-English analysis case into a validated, ordered multi-widget
dashboard spec scoped to a single Data Space VIEW. Reuses the existing NL→SQL
building blocks:

  * ``app.spaces.space_prompt`` — schema-only prompt blocks for the space VIEW.
  * ``app.llm.providers`` — the active LLM provider (``generate_tool`` for the
    multi-widget plan, ``generate`` for per-widget SQL self-repair).
  * ``app.llm.sql_validator`` — the same safety validator as the chat path.
  * ``app.db.async_query_rows`` — the existing validated query execution path.

Privacy invariant (CLI-126): the LLM only ever sees the schema / semantic layer.
On a failed query we feed back the *error text* (which describes the SQL/schema,
not rows) for self-repair, and surface only the sanitized error to the client.
"""

from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from app.ch_errors import safe_clickhouse_error
from app.llm.providers import LLMProvider, get_provider
from app.llm.sql_validator import ensure_limit, validate_sql
from app.spaces.config import DataSpaceConfig
from app.spaces.space_prompt import _block_space_columns, _block_space_rules

log = logging.getLogger("app.llm.dashboard_spec")

# Board decision (CLI-126): widget cap 6–8.
MIN_WIDGETS = 6
MAX_WIDGETS = 8

VizType = Literal["number", "table", "bar", "line", "funnel", "comparison"]

# Type of the injectable query runner — async SQL -> rows. Defaults to the real
# ClickHouse path; tests inject a fake.
QueryRunner = Callable[[str], Awaitable[list[dict]]]


# ---------------------------------------------------------------------------
# LLM output schema (the shape the model fills in via generate_tool)
# ---------------------------------------------------------------------------

class WidgetEncoding(BaseModel):
    """How result columns map onto the chart — hints for the renderer."""

    x: str | None = Field(default=None, description="Category or time axis column.")
    y: list[str] = Field(default_factory=list, description="Measure column(s) to plot.")
    series: str | None = Field(default=None, description="Optional column to split into series.")
    value: str | None = Field(default=None, description="Single value column (for 'number' viz).")
    label: str | None = Field(default=None, description="Label column (for 'funnel'/'bar').")


class WidgetPlan(BaseModel):
    """One planned widget as produced by the LLM."""

    title: str = Field(description="Short widget title (max ~10 words).")
    intent: str = Field(description="One sentence: what business question this widget answers.")
    sql: str = Field(description="ClickHouse SELECT against the data space VIEW.")
    viz_type: VizType
    encoding: WidgetEncoding = Field(default_factory=WidgetEncoding)
    suggested_filters: list[str] = Field(
        default_factory=list,
        description="Column names that make good per-widget interactive filters.",
    )


class DashboardPlan(BaseModel):
    """The full multi-widget plan returned by the LLM in a single tool call."""

    dashboard_filters: list[str] = Field(
        default_factory=list,
        description="Column names that make sense as dashboard-wide filters across all widgets.",
    )
    widgets: list[WidgetPlan] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Final, validated response shape returned by the endpoint
# ---------------------------------------------------------------------------

class WidgetSpec(BaseModel):
    """A widget after validation + execution (and optional self-repair)."""

    title: str
    intent: str
    sql: str
    viz_type: str
    encoding: WidgetEncoding
    suggested_filters: list[str]
    status: Literal["ok", "error"]
    error: str | None = None
    columns: list[str] = Field(default_factory=list)
    row_count: int | None = None
    repaired: bool = False


class DashboardSpec(BaseModel):
    space_id: str
    description: str
    dashboard_filters: list[str]
    widgets: list[WidgetSpec]
    widget_count: int
    llm_ms: int
    truncated: bool = False
    # Set when the plan (even after a bounded re-ask) returned fewer than the
    # requested MIN_WIDGETS — the board is accepted but the shortfall is surfaced.
    note: str | None = None


# ---------------------------------------------------------------------------
# Streaming progress events (OSD phase 2)
# ---------------------------------------------------------------------------

# The generation flow is otherwise synchronous; these events let the frontend
# render an honest progress bar instead of a fake timer. Stage names are literal:
# all SQL is authored in the single planning call, so per-widget work is *running*
# the SQL (not generating it) and then reporting it *validated*. Emitted order for
# an M-widget dashboard:
#   planning
#   -> running (1/M) -> validated (1/M)
#   -> ...
#   -> running (M/M) -> validated (M/M)
#   -> done            (carries the full DashboardSpec)
# A fatal failure mid-stream (incl. a zero-widget plan) emits a single ``error``
# event instead of ``done``.
EventStage = Literal["planning", "running", "validated", "done", "error"]


class DashboardEvent(BaseModel):
    """One progress event in the dashboard generation stream."""

    stage: EventStage
    index: int | None = None  # 1-based widget index (running/validated only)
    total: int | None = None  # total widget count, known once planning completes
    widget_title: str | None = None
    error: str | None = None  # per-widget sanitized error, or a fatal stream error
    spec: DashboardSpec | None = None  # populated only on the final ``done`` event


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

_GEN_TOOL_NAME = "generate_dashboard"
_GEN_TOOL_DESCRIPTION = (
    "Return an ordered set of complementary dashboard widgets (each with its own "
    "ClickHouse SQL) plus dashboard-wide filters for the requested analysis case."
)


def _block_dashboard_instructions(min_widgets: int, max_widgets: int) -> str:
    return f"""DASHBOARD DESIGN TASK:
You are designing a complete analytics dashboard, not a single chart. Produce
between {min_widgets} and {max_widgets} complementary widgets that together answer
the analysis case from several angles.

Guidelines:
- Lead with 1–2 headline "number" KPIs for the most important metrics.
- Include a time trend ("line"), one or more breakdowns ("bar"/"table"), and a
  "funnel" or "comparison" widget where the data supports it.
- Each widget MUST have its own valid ClickHouse SELECT against the VIEW and obey
  every rule in the CRITICAL RULES section above.
- Do not repeat the same analysis — each widget adds a distinct perspective.
- For each widget set the encoding hints, naming the VIEW columns used for the
  x axis / y measures / series / value / label as appropriate for its viz_type.
- suggested_filters: VIEW column names that make good per-widget interactive filters.
- dashboard_filters: VIEW column names that make sense as dashboard-wide filters
  applied across all widgets (e.g. a date column, owner, pipeline).

Return your answer ONLY via the {_GEN_TOOL_NAME} tool."""


def build_dashboard_prompt(
    config: DataSpaceConfig,
    min_widgets: int = MIN_WIDGETS,
    max_widgets: int = MAX_WIDGETS,
) -> str:
    """Schema-only system prompt for multi-widget generation against one space."""
    return "\n\n".join(
        [
            _block_space_rules(config),
            _block_space_columns(config),
            _block_dashboard_instructions(min_widgets, max_widgets),
        ]
    )


def _build_user_prompt(description: str, min_widgets: int, max_widgets: int) -> str:
    return (
        f"Design a dashboard of {min_widgets} to {max_widgets} complementary widgets "
        f"for this analysis case:\n\n{description}"
    )


def _build_reask_prompt(
    description: str, min_widgets: int, max_widgets: int, got: int
) -> str:
    """Nudge prompt used once when the first plan fell short of ``min_widgets``."""
    return (
        f"The previous attempt returned only {got} widget(s), but a useful dashboard "
        f"needs at least {min_widgets}. Design a fuller dashboard of {min_widgets} to "
        f"{max_widgets} complementary widgets — each adding a distinct perspective "
        f"(headline KPIs, a time trend, breakdowns, and a funnel/comparison where the "
        f"data supports it) — for this analysis case:\n\n{description}"
    )


# ---------------------------------------------------------------------------
# Validation + execution + self-repair
# ---------------------------------------------------------------------------

class _RunResult(BaseModel):
    sql: str
    ok: bool
    columns: list[str] = Field(default_factory=list)
    row_count: int | None = None
    raw_error: str | None = None  # full error — safe to feed the model (no rows)
    safe_error: str | None = None  # sanitized error — safe to return to client


async def _validate_and_run(sql: str, run_query: QueryRunner) -> _RunResult:
    """Validate the SQL then execute it through the existing validated path."""
    cleaned = sql.strip().rstrip(";").strip()

    is_valid, verr = validate_sql(cleaned)
    if not is_valid:
        msg = f"SQL validation failed: {verr}"
        # Validation messages describe the query only — safe both ways.
        return _RunResult(sql=cleaned, ok=False, raw_error=msg, safe_error=msg)

    limited = ensure_limit(cleaned)
    try:
        rows = await run_query(limited)
    except Exception as exc:  # noqa: BLE001 — surface sanitized, log full upstream
        return _RunResult(
            sql=limited,
            ok=False,
            raw_error=str(exc),
            safe_error=safe_clickhouse_error(exc),
        )

    columns = list(rows[0].keys()) if rows else []
    return _RunResult(sql=limited, ok=True, columns=columns, row_count=len(rows))


async def _repair_sql(
    provider: LLMProvider,
    system_prompt: str,
    plan: WidgetPlan,
    raw_error: str,
) -> str | None:
    """Ask the model to fix one widget's SQL given the error. Reuses generate().

    Feeds the error text (describes SQL/schema, never row data) back through the
    standard chat-style turn so the existing provider path does the work.
    """
    messages = [
        {"role": "user", "content": f"Generate a ClickHouse SQL query for this analysis: {plan.intent}"},
        {"role": "assistant", "content": "", "sql": plan.sql},
        {
            "role": "user",
            "content": (
                f"That query failed with this error:\n{raw_error}\n\n"
                "Return a corrected ClickHouse SQL query for the same analysis. "
                "Only reference columns that exist in the VIEW and follow all the rules."
            ),
        },
    ]
    try:
        resp = await provider.generate(messages, system_prompt=system_prompt)
    except Exception as exc:  # noqa: BLE001
        log.warning("Self-repair LLM call failed for widget '%s': %s", plan.title, exc)
        return None
    return resp.sql


async def _finalize_widget(
    provider: LLMProvider,
    system_prompt: str,
    plan: WidgetPlan,
    run_query: QueryRunner,
) -> WidgetSpec:
    """Validate + execute a widget, with a single bounded self-repair attempt."""
    result = await _validate_and_run(plan.sql, run_query)
    repaired = False

    if not result.ok:
        new_sql = await _repair_sql(provider, system_prompt, plan, result.raw_error or "")
        if new_sql:
            repaired = True
            retry = await _validate_and_run(new_sql, run_query)
            # Keep the repaired SQL regardless; adopt its outcome.
            result = retry

    return WidgetSpec(
        title=plan.title,
        intent=plan.intent,
        sql=result.sql,
        viz_type=plan.viz_type,
        encoding=plan.encoding,
        suggested_filters=plan.suggested_filters,
        status="ok" if result.ok else "error",
        error=None if result.ok else result.safe_error,
        columns=result.columns,
        row_count=result.row_count,
        repaired=repaired,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

async def _request_plan(
    provider: LLMProvider,
    system_prompt: str,
    user_prompt: str,
) -> tuple[DashboardPlan, int]:
    """Run one structured planning call, returning the plan and its wall-clock ms."""
    t0 = time.time()
    raw = await provider.generate_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_name=_GEN_TOOL_NAME,
        tool_description=_GEN_TOOL_DESCRIPTION,
        input_schema=DashboardPlan.model_json_schema(),
    )
    ms = int((time.time() - t0) * 1000)
    return DashboardPlan.model_validate(raw), ms


async def stream_dashboard_spec(
    config: DataSpaceConfig,
    description: str,
    *,
    provider: LLMProvider | None = None,
    run_query: QueryRunner | None = None,
    min_widgets: int = MIN_WIDGETS,
    max_widgets: int = MAX_WIDGETS,
) -> AsyncIterator[DashboardEvent]:
    """Generate a dashboard spec, yielding progress events as the work proceeds.

    Same pipeline as :func:`generate_dashboard_spec` — one structured LLM call
    plans the dashboard, then each widget's SQL is validated/executed with a
    bounded self-repair retry — but emits ``DashboardEvent``s so callers can show
    real progress. The final ``done`` event carries the complete ``DashboardSpec``.

    Events are emitted *before* the slow step they describe (``planning`` before
    the LLM plan call, ``running`` before a widget's SQL is executed); the
    ``validated`` event fires *after* a widget is validated/executed and carries
    that widget's sanitized error if it failed.

    Widget-floor enforcement (CLI-153): the ``MIN_WIDGETS`` floor is enforced in
    code, not just in the prompt. A plan that returns **zero** widgets ends the
    stream with an ``error`` event (never an empty board). A plan that returns
    *fewer than* ``min_widgets`` triggers one bounded re-ask for a fuller plan;
    whatever the re-ask yields is then accepted, with ``DashboardSpec.note`` set
    if it is still short.
    """
    if provider is None:
        provider = get_provider()
    if run_query is None:
        from app.db import async_query_rows

        run_query = async_query_rows

    system_prompt = build_dashboard_prompt(config, min_widgets, max_widgets)
    user_prompt = _build_user_prompt(description, min_widgets, max_widgets)

    yield DashboardEvent(stage="planning")

    plan, llm_ms = await _request_plan(provider, system_prompt, user_prompt)

    # Widget-floor enforcement. A completely empty plan is a hard failure — end
    # the stream with an error rather than streaming a full progress bar to an
    # empty grid. A short-but-non-empty plan gets one bounded re-ask.
    if not plan.widgets:
        yield DashboardEvent(
            stage="error",
            error=(
                "The model did not return any widgets for this analysis case. "
                "Try rephrasing the request or narrowing the scope."
            ),
        )
        return

    note: str | None = None
    if len(plan.widgets) < min_widgets:
        log.info(
            "Dashboard plan returned %d widgets (< MIN %d); re-asking once",
            len(plan.widgets),
            min_widgets,
        )
        reask_prompt = _build_reask_prompt(
            description, min_widgets, max_widgets, len(plan.widgets)
        )
        reask_plan, reask_ms = await _request_plan(provider, system_prompt, reask_prompt)
        llm_ms += reask_ms
        # Keep whichever attempt produced more widgets — never regress below the
        # first plan's count.
        if len(reask_plan.widgets) > len(plan.widgets):
            plan = reask_plan
        if len(plan.widgets) < min_widgets:
            note = (
                f"Generated {len(plan.widgets)} of the target {min_widgets} widgets — "
                "the analysis case may be too narrow for a fuller dashboard."
            )

    widgets = plan.widgets
    truncated = False
    if len(widgets) > max_widgets:
        log.info("Dashboard plan returned %d widgets; capping to %d", len(widgets), max_widgets)
        widgets = widgets[:max_widgets]
        truncated = True
    total = len(widgets)

    finalized: list[WidgetSpec] = []
    for index, w in enumerate(widgets, start=1):
        yield DashboardEvent(
            stage="running", index=index, total=total, widget_title=w.title
        )
        spec_widget = await _finalize_widget(provider, system_prompt, w, run_query)
        finalized.append(spec_widget)
        yield DashboardEvent(
            stage="validated",
            index=index,
            total=total,
            widget_title=w.title,
            error=spec_widget.error,
        )

    spec = DashboardSpec(
        space_id=config.id,
        description=description,
        dashboard_filters=plan.dashboard_filters,
        widgets=finalized,
        widget_count=len(finalized),
        llm_ms=llm_ms,
        truncated=truncated,
        note=note,
    )
    yield DashboardEvent(stage="done", total=total, spec=spec)


async def generate_dashboard_spec(
    config: DataSpaceConfig,
    description: str,
    *,
    provider: LLMProvider | None = None,
    run_query: QueryRunner | None = None,
    min_widgets: int = MIN_WIDGETS,
    max_widgets: int = MAX_WIDGETS,
) -> DashboardSpec:
    """Generate a validated multi-widget dashboard spec for one data space.

    Flow: one structured LLM call plans the whole dashboard, then each widget's
    SQL is run through the existing validated query path with a single bounded
    self-repair retry on validator/ClickHouse failure. The widget count is capped
    at ``max_widgets`` and floored at ``min_widgets`` (one bounded re-ask; a
    zero-widget plan raises). Non-streaming wrapper over
    :func:`stream_dashboard_spec`.
    """
    spec: DashboardSpec | None = None
    stream_error: str | None = None
    async for event in stream_dashboard_spec(
        config,
        description,
        provider=provider,
        run_query=run_query,
        min_widgets=min_widgets,
        max_widgets=max_widgets,
    ):
        if event.stage == "done":
            spec = event.spec
        elif event.stage == "error":
            stream_error = event.error
    if spec is None:
        # The only non-``done`` terminal state is a zero-widget plan.
        raise ValueError(stream_error or "Dashboard generation produced no widgets")
    return spec
