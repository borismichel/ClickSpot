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

import asyncio
import logging
import time
from typing import AsyncIterator, Awaitable, Callable, Literal

from pydantic import BaseModel, Field

from app.ch_errors import safe_clickhouse_error
from app.llm.dashboard_lint import (
    cardinality_repair_instruction,
    cardinality_violation,
    composition_warnings,
    find_duplicate_analyses,
    viz_role_warning,
)
from app.llm.providers import LLMProvider, get_provider
from app.llm.sql_validator import ensure_limit, validate_sql
from app.spaces.config import DataSpaceConfig
from app.spaces.space_prompt import _block_space_columns, _block_space_rules

log = logging.getLogger("app.llm.dashboard_spec")

# Board decision (CLI-126): widget cap 6–8.
MIN_WIDGETS = 6
MAX_WIDGETS = 8

# Widgets are validated/executed (and occasionally LLM-repaired) in parallel
# (CLI-152). Cap concurrency so a wide dashboard doesn't fan out a burst of
# ClickHouse queries / provider calls all at once.
MAX_WIDGET_CONCURRENCY = 4

VizType = Literal["number", "table", "bar", "line", "funnel", "comparison"]

# The dashboard composition grammar (CLI-155 / plan C1). Every widget declares
# the *job* it does on the board; the prompt below constrains how many of each
# role a plan may contain, and downstream code (C2 lint, C3 layout) keys off it:
#   kpi       -> a single headline "number" stat tile
#   trend     -> a time series ("line")
#   breakdown -> magnitude across categories ("bar", or "table" when >7 classes)
#   flow      -> a genuinely staged process ("funnel")
#   detail    -> a full-width lookup "table"
WidgetRole = Literal["kpi", "trend", "breakdown", "flow", "detail"]

# ``comparison`` is intentionally absent from the composition grammar above: it is
# a broken viz in the OSD draft renderer (it never receives the context-KPI
# payload it needs), so the prompt no longer asks the model to produce it. Whether
# to fully retire the type from ``VizType`` or repair the renderer is the C4
# renderer-alignment decision (CLI-147 open decision #3); the type is kept in the
# Literal until then so existing specs continue to validate.

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
    compare: str | None = Field(
        default=None,
        description=(
            "Prior-period / baseline value column returned alongside 'value' in the "
            "same single-row query. When set, 'number'/'comparison' widgets render a "
            "delta badge (value vs prior) instead of a bare figure."
        ),
    )


class WidgetPlan(BaseModel):
    """One planned widget as produced by the LLM."""

    title: str = Field(description="Short widget title (max ~10 words).")
    intent: str = Field(description="One sentence: what business question this widget answers.")
    sql: str = Field(description="ClickHouse SELECT against the data space VIEW.")
    role: WidgetRole = Field(
        description=(
            "The job this widget does on the board, per the composition grammar: "
            "'kpi' (headline number), 'trend' (time series), 'breakdown' "
            "(magnitude across categories), 'flow' (staged funnel), 'detail' "
            "(lookup table). Drives layout and composition checks."
        )
    )
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

# Rows carried inline with each widget so the frontend can render the draft
# immediately instead of re-issuing the same SQL (CLI-148). Bounded to keep the
# spec payload sane; the query itself is still limited by ``ensure_limit``. A
# widget whose result exceeds this cap carries the first ``MAX_SPEC_ROWS`` and
# re-queries the full set on demand (filter change / refresh / SQL edit).
MAX_SPEC_ROWS = 500


class WidgetSpec(BaseModel):
    """A widget after validation + execution (and optional self-repair)."""

    title: str
    intent: str
    sql: str
    role: str
    viz_type: str
    encoding: WidgetEncoding
    suggested_filters: list[str]
    status: Literal["ok", "error"]
    error: str | None = None
    columns: list[str] = Field(default_factory=list)
    row_count: int | None = None
    # Bounded result set (<= MAX_SPEC_ROWS) so the draft renders without a
    # second ClickHouse round-trip. Empty for error widgets.
    rows: list[dict] = Field(default_factory=list)
    repaired: bool = False
    # Composition-lint warnings for this widget (CLI-161 / C2): cardinality that
    # self-repair could not fix, viz/role incoherence, duplicate analysis. Empty
    # for a clean widget. Surfaced on the draft card, never silently dropped.
    warnings: list[str] = Field(default_factory=list)


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
    # Board-level composition-lint warnings (CLI-161 / C2): role-count violations
    # (missing/oversized KPI band, >1 detail table, etc.) and duplicate analyses.
    # Per-widget issues live on each ``WidgetSpec.warnings``.
    warnings: list[str] = Field(default_factory=list)


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

# These events let the frontend render an honest progress bar instead of a fake
# timer. Stage names are literal: all SQL is authored in the single planning call,
# so per-widget work is *running* the SQL (not generating it) and then reporting it
# *validated*. Widget finalization runs in parallel (CLI-152), so progress is
# completion-counted rather than sequential — a single bulk ``running`` tick follows
# ``planning``, then one ``validated`` event fires as each widget lands, carrying
# the finished widget's 1-based ``index`` (so the frontend needs no ordering) and a
# running ``completed`` tally. Emitted order for an M-widget dashboard:
#   planning
#   -> running   (completed=0, total=M)   # one bulk "widgets are being built" tick
#   -> validated (index=i, completed=k)   # M of these, in completion order
#   -> done                               # carries the full DashboardSpec
# A fatal failure mid-stream (incl. a zero-widget plan) emits a single ``error``
# event instead of ``done``.
EventStage = Literal["planning", "running", "validated", "done", "error"]


class DashboardEvent(BaseModel):
    """One progress event in the dashboard generation stream."""

    stage: EventStage
    index: int | None = None  # 1-based widget index (validated only)
    total: int | None = None  # total widget count, known once planning completes
    completed: int | None = None  # widgets finalized so far (generating/validating)
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
the analysis case following the inverted-pyramid layout: the headline answer must
be readable in ~5 seconds at the top, with supporting detail below.

COMPOSITION GRAMMAR (set the `role` field on every widget and respect these counts):
- role "kpi" — a single headline metric as a "number" stat tile. Include EXACTLY
  ONE band of 2–4 kpi widgets (never a one-bar chart for a single value).
- role "trend" — change over time as a "line". Include exactly ONE trend widget
  WHEN the VIEW has a usable date/timestamp column; omit it when it has none.
- role "breakdown" — magnitude across categories as a "bar" (or "table" only when
  there are more than ~7 categories that all matter). Include 2–4 breakdowns.
- role "detail" — a full-width lookup "table". At most ONE, placed last.
- role "flow" — a "funnel" ONLY for a genuinely staged, monotonic process (e.g. a
  sales pipeline). If the data is not a real ordered pipeline, use a breakdown bar
  instead. Zero or one flow widget.
Do NOT emit a "comparison" widget — it is not supported here; express period
comparisons as a kpi (single number) or a trend line instead.

PER-VIZ SQL SHAPE CONTRACTS (in addition to the CRITICAL RULES section above):
- number (kpi): return EXACTLY ONE ROW with a single value column (optionally a
  second prior-period column for a delta). Never GROUP BY.
- bar (breakdown): sort descending and cap the tail —
  `... GROUP BY <category> ORDER BY <measure> DESC LIMIT 12`. Fold the long tail
  into "Other" rather than returning hundreds of categories.
- line (trend): bucket by time (`toStartOfMonth(...)`, `toStartOfWeek(...)`, etc.),
  `ORDER BY` the time bucket ascending, and keep it to AT MOST 5 series — 6+ series
  must be folded or split into separate widgets.
- funnel (flow): one row per ordered stage, stages in pipeline order.
- table (breakdown/detail): at most ~8 explicit columns; no `SELECT *`.

OTHER RULES:
- Each widget MUST have its own valid ClickHouse SELECT against the VIEW and obey
  every rule in the CRITICAL RULES section above.
- Do not repeat the same analysis — two widgets grouping by the same column on the
  same measure is a duplicate; each widget adds a distinct perspective.
- For each widget set the encoding hints, naming the VIEW columns used for the
  x axis / y measures / series / value / label as appropriate for its viz_type.
- "bar" widgets: rank the categories — ORDER BY the measure DESC and LIMIT ~12 so
  the chart stays legible (the renderer folds any tail into an "Other" bar).
- "number" and "comparison" widgets: return exactly ONE row. For a comparison,
  select the current value AND the prior-period value as two columns in that row,
  name the current column in encoding.value and the prior column in encoding.compare
  so the tile can show a value + delta. A plain "number" needs only encoding.value.
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
        f"{max_widgets} complementary widgets — each with a distinct `role` per the "
        f"composition grammar (headline 'kpi' numbers, a 'trend' line, 'breakdown' "
        f"bars, a 'detail' table, and a 'flow' funnel only for a genuinely staged "
        f"process). Do NOT emit a 'comparison' widget; express period comparisons as a "
        f"kpi or a trend line — for this analysis case:\n\n{description}"
    )


# ---------------------------------------------------------------------------
# Validation + execution + self-repair
# ---------------------------------------------------------------------------

class _RunResult(BaseModel):
    sql: str
    ok: bool
    columns: list[str] = Field(default_factory=list)
    row_count: int | None = None
    rows: list[dict] = Field(default_factory=list)  # bounded to MAX_SPEC_ROWS
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
    return _RunResult(
        sql=limited,
        ok=True,
        columns=columns,
        row_count=len(rows),
        rows=rows[:MAX_SPEC_ROWS],
    )


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
    """Validate + execute a widget, with a single bounded self-repair attempt.

    The one repair attempt serves whichever fires first: a SQL failure, or a C2
    cardinality violation on an otherwise-valid result (an over-wide ``bar`` or a
    multi-row ``number``). Anything still out of shape after that is handled
    deterministically — an unreadable bar is demoted to a table — and surfaced as a
    widget ``warning`` rather than rendered as a silently-bad chart (CLI-161).
    """
    result = await _validate_and_run(plan.sql, run_query)
    repaired = False
    viz_type = plan.viz_type
    warnings: list[str] = []

    if not result.ok:
        new_sql = await _repair_sql(provider, system_prompt, plan, result.raw_error or "")
        if new_sql:
            repaired = True
            retry = await _validate_and_run(new_sql, run_query)
            # Keep the repaired SQL regardless; adopt its outcome.
            result = retry

    # C2 post-plan cardinality lint. Only meaningful once the query actually ran.
    if result.ok:
        instruction = cardinality_repair_instruction(viz_type, result.row_count)
        # Feed the shape violation into the same bounded self-repair budget — but
        # only if we haven't already spent it fixing a SQL failure.
        if instruction and not repaired:
            new_sql = await _regenerate_sql(
                provider, system_prompt, plan.intent, result.sql, instruction=instruction
            )
            if new_sql:
                repaired = True
                retry = await _validate_and_run(new_sql, run_query)
                if retry.ok:
                    result = retry

        residual = cardinality_violation(viz_type, result.row_count)
        if residual:
            if viz_type == "bar":
                # An over-wide bar is unreadable; a table is the honest fallback the
                # grammar already sanctions for many-category breakdowns.
                viz_type = "table"
                warnings.append(f"Breakdown {residual}; shown as a table instead of a bar.")
            else:
                warnings.append(f"KPI {residual}.")

    # Viz/role coherence — checked on the *final* viz (post-demotion).
    coherence = viz_role_warning(plan.role, viz_type)
    if coherence:
        warnings.append(coherence)

    return WidgetSpec(
        title=plan.title,
        intent=plan.intent,
        sql=result.sql,
        role=plan.role,
        viz_type=viz_type,
        encoding=plan.encoding,
        suggested_filters=plan.suggested_filters,
        status="ok" if result.ok else "error",
        error=None if result.ok else result.safe_error,
        columns=result.columns,
        row_count=result.row_count,
        rows=result.rows,
        repaired=repaired,
        warnings=warnings,
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
            role="detail",  # required since C1; transient plan, only intent/sql are used by _repair_sql
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
    max_concurrency: int = MAX_WIDGET_CONCURRENCY,
) -> AsyncIterator[DashboardEvent]:
    """Generate a dashboard spec, yielding progress events as the work proceeds.

    Same pipeline as :func:`generate_dashboard_spec` — one structured LLM call
    plans the dashboard, then each widget's SQL is validated/executed with a
    bounded self-repair retry — but emits ``DashboardEvent``s so callers can show
    real progress. The final ``done`` event carries the complete ``DashboardSpec``.

    Widget finalization runs concurrently with bounded fan-out
    (``max_concurrency``), so progress is completion-counted: a single bulk
    ``running`` tick follows ``planning``, then one ``validated`` event fires
    as *each* widget lands (in completion order, carrying its original 1-based
    ``index`` and a running ``completed`` tally, plus a sanitized error if it
    failed). Widgets are still assembled into the spec in their planned order.

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

    # One bulk tick so the UI flips into "building widgets" mode; per-widget
    # progress then arrives as completion-counted ``validated`` events.
    yield DashboardEvent(stage="running", total=total, completed=0)

    finalized: dict[int, WidgetSpec] = {}
    sem = asyncio.Semaphore(max(1, max_concurrency))

    async def _run(idx: int, plan_widget: WidgetPlan) -> tuple[int, WidgetSpec]:
        async with sem:
            spec_widget = await _finalize_widget(
                provider, system_prompt, plan_widget, run_query
            )
        return idx, spec_widget

    tasks = [
        asyncio.create_task(_run(index, w))
        for index, w in enumerate(widgets, start=1)
    ]
    completed = 0
    try:
        for coro in asyncio.as_completed(tasks):
            index, spec_widget = await coro
            finalized[index] = spec_widget
            completed += 1
            yield DashboardEvent(
                stage="validated",
                index=index,
                total=total,
                completed=completed,
                widget_title=spec_widget.title,
                error=spec_widget.error,
            )
    finally:
        # If the consumer disconnects mid-stream, don't leak in-flight work.
        for t in tasks:
            if not t.done():
                t.cancel()

    ordered = [finalized[i] for i in range(1, total + 1)]

    # C2 board-level composition lint (role counts + duplicate analyses). Per-widget
    # cardinality/coherence warnings were already attached during finalization.
    board_warnings = composition_warnings([w.role for w in ordered])
    for group in find_duplicate_analyses([w.sql for w in ordered]):
        titles = ", ".join(f"'{ordered[i].title}'" for i in group)
        board_warnings.append(
            f"Duplicate analysis: {titles} group by the same column(s) on the same measure."
        )
        # Tag the redundant widgets (all but the first) so the warning is also
        # visible on the chart itself, not just the board summary.
        for i in group[1:]:
            ordered[i].warnings.append(
                "Duplicates another widget's analysis (same GROUP BY + measure)."
            )

    spec = DashboardSpec(
        space_id=config.id,
        description=description,
        dashboard_filters=plan.dashboard_filters,
        widgets=ordered,
        widget_count=len(ordered),
        llm_ms=llm_ms,
        truncated=truncated,
        note=note,
        warnings=board_warnings,
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
