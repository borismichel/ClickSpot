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


class WidgetRegenResult(BaseModel):
    """Result of regenerating a single widget's SQL (OSD phase 3, CLI-159).

    Returned by the per-widget regenerate endpoint. Mirrors the SQL-outcome
    fields of :class:`WidgetSpec` (the caller already holds the widget's
    title/viz/encoding), plus the AI-produced ``sql`` and how the model was
    steered (``repaired`` when a bounded self-repair retry ran).
    """

    intent: str
    sql: str
    status: Literal["ok", "error"]
    error: str | None = None
    columns: list[str] = Field(default_factory=list)
    row_count: int | None = None
    repaired: bool = False
    llm_ms: int = 0


# ---------------------------------------------------------------------------
# Streaming progress events (OSD phase 2)
# ---------------------------------------------------------------------------

# The generation flow is otherwise synchronous; these events let the frontend
# render an honest progress bar instead of a fake timer. Emitted order for an
# M-widget dashboard:
#   planning
#   -> generating (1/M) -> validating (1/M)
#   -> ...
#   -> generating (M/M) -> validating (M/M)
#   -> done            (carries the full DashboardSpec)
# A fatal failure mid-stream emits a single ``error`` event instead of ``done``.
EventStage = Literal["planning", "generating", "validating", "done", "error"]


class DashboardEvent(BaseModel):
    """One progress event in the dashboard generation stream."""

    stage: EventStage
    index: int | None = None  # 1-based widget index (generating/validating only)
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
# Per-widget regenerate (OSD phase 3, CLI-159)
# ---------------------------------------------------------------------------

async def _regenerate_sql(
    provider: LLMProvider,
    system_prompt: str,
    intent: str,
    sql: str,
    *,
    error: str | None = None,
    instruction: str | None = None,
) -> str | None:
    """Ask the model to produce a new SQL query for one widget.

    Reuses the same schema-only chat turn as :func:`_repair_sql` but is steered
    by two optional signals: ``error`` (the widget failed — fix it) and
    ``instruction`` (the user wants a change, e.g. "make this monthly"). Either,
    both, or neither may be given; with neither it simply re-derives the query
    for the same intent. Only the error *text* is fed back (it describes the
    SQL/schema, never row data — the CLI-126 privacy invariant).
    """
    feedback: list[str] = []
    if error:
        feedback.append(f"That query failed with this error:\n{error}")
    if instruction:
        feedback.append(f"Revise the query to satisfy this instruction: {instruction}")
    if not feedback:
        feedback.append("Regenerate the query for the same analysis, improving it.")

    messages = [
        {"role": "user", "content": f"Generate a ClickHouse SQL query for this analysis: {intent}"},
        {"role": "assistant", "content": "", "sql": sql},
        {
            "role": "user",
            "content": (
                "\n\n".join(feedback)
                + "\n\nReturn a corrected ClickHouse SQL query for the same analysis. "
                "Only reference columns that exist in the VIEW and follow all the rules."
            ),
        },
    ]
    try:
        resp = await provider.generate(messages, system_prompt=system_prompt)
    except Exception as exc:  # noqa: BLE001
        log.warning("Widget regenerate LLM call failed for intent '%s': %s", intent[:60], exc)
        return None
    return resp.sql


async def regenerate_widget(
    config: DataSpaceConfig,
    intent: str,
    sql: str,
    *,
    error: str | None = None,
    instruction: str | None = None,
    provider: LLMProvider | None = None,
    run_query: QueryRunner | None = None,
) -> WidgetRegenResult:
    """Regenerate one widget's SQL, then validate/execute it (CLI-159).

    The backend for the OSD iteration loop (Plan B3) and one-click repair of a
    failed widget. Reuses the existing pipeline: an LLM turn produces new SQL
    (steered by ``error`` and/or ``instruction``), then :func:`_validate_and_run`
    runs it through the same validator/limit path as the chat path, with a single
    bounded :func:`_repair_sql` retry if it still fails — exactly the guarantee
    :func:`_finalize_widget` gives during generation.
    """
    if provider is None:
        provider = get_provider()
    if run_query is None:
        from app.db import async_query_rows

        run_query = async_query_rows

    system_prompt = build_dashboard_prompt(config)

    t0 = time.time()
    new_sql = await _regenerate_sql(
        provider, system_prompt, intent, sql, error=error, instruction=instruction
    )
    llm_ms = int((time.time() - t0) * 1000)

    # If the model returned nothing, fall back to validating the original SQL so
    # the caller still gets a real status instead of a hard failure.
    result = await _validate_and_run(new_sql or sql, run_query)
    repaired = False

    if not result.ok:
        plan = WidgetPlan(
            title=(intent[:80] or "widget"),
            intent=intent,
            sql=result.sql,
            viz_type="table",
        )
        fixed = await _repair_sql(provider, system_prompt, plan, result.raw_error or "")
        if fixed:
            repaired = True
            result = await _validate_and_run(fixed, run_query)

    return WidgetRegenResult(
        intent=intent,
        sql=result.sql,
        status="ok" if result.ok else "error",
        error=None if result.ok else result.safe_error,
        columns=result.columns,
        row_count=result.row_count,
        repaired=repaired,
        llm_ms=llm_ms,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

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
    the LLM plan call, ``generating`` before a widget is finalized); the
    ``validating`` event fires *after* a widget is validated/executed and carries
    that widget's sanitized error if it failed.
    """
    if provider is None:
        provider = get_provider()
    if run_query is None:
        from app.db import async_query_rows

        run_query = async_query_rows

    system_prompt = build_dashboard_prompt(config, min_widgets, max_widgets)
    user_prompt = _build_user_prompt(description, min_widgets, max_widgets)

    yield DashboardEvent(stage="planning")

    t0 = time.time()
    raw = await provider.generate_tool(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        tool_name=_GEN_TOOL_NAME,
        tool_description=_GEN_TOOL_DESCRIPTION,
        input_schema=DashboardPlan.model_json_schema(),
    )
    llm_ms = int((time.time() - t0) * 1000)

    plan = DashboardPlan.model_validate(raw)

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
            stage="generating", index=index, total=total, widget_title=w.title
        )
        spec_widget = await _finalize_widget(provider, system_prompt, w, run_query)
        finalized.append(spec_widget)
        yield DashboardEvent(
            stage="validating",
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
    at ``max_widgets``. Non-streaming wrapper over :func:`stream_dashboard_spec`.
    """
    spec: DashboardSpec | None = None
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
    assert spec is not None, "stream_dashboard_spec must end with a 'done' event"
    return spec
