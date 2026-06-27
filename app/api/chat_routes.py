"""Chat API routes — natural language → SQL → ClickHouse results.

LLM provider config, OAuth, and schema-cache endpoints used to live here for
historical reasons; they now live in app/api/llm_routes.py.
"""

import asyncio
import logging
import time
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException

from app.api.chat_models import ChatRequest, ChatResponse, ContextKPIResult
from app.ch_errors import safe_clickhouse_error
from app.db import async_explain, async_query_rows, async_query_value
from app.llm import observability as obs
from app.llm import repair as sql_repair
from app.llm.providers import get_provider
from app.llm.sql_validator import validate_sql, ensure_limit

router = APIRouter(prefix="/api/v1")
log = logging.getLogger("app.chat")

# Cap on context-KPI queries running concurrently. The LLM emits 2-8 KPIs, each
# with an optional previous-period query, so an unbounded gather could fire up
# to ~16 queries at once against the single shared ClickHouse client and the
# default asyncio thread pool. 8 keeps the common case fully parallel while
# bounding the worst case.
_CONTEXT_KPI_CONCURRENCY = 8


def compute_kpi_delta(value, prev_value) -> tuple[float | None, str | None]:
    """Period-over-period delta for a context KPI.

    Returns ``(delta_percent, delta_label)`` — at most one is ever non-None:

    - a signed percentage change when the previous value is a usable, non-zero
      number;
    - the label ``"New"`` when the baseline is zero but the current value is not
      (a percentage change against a zero baseline is undefined — the old code
      reported a meaningless ``+100% vs 0``; see CLI-42).

    Both are None when either value is missing / non-numeric, or when nothing
    changed from a zero baseline.
    """
    if value is None or prev_value is None:
        return None, None
    try:
        cur = float(value)
        prev = float(prev_value)
    except (ValueError, TypeError):
        return None, None
    if prev != 0:
        return round((cur - prev) / abs(prev) * 100, 1), None
    if cur != 0:
        return None, "New"
    return None, None


async def _run_context_kpi(kpi, sem: asyncio.Semaphore) -> ContextKPIResult | None:
    """Execute a single context KPI (and its optional previous-period query).

    Returns a ``ContextKPIResult`` on success, or ``None`` when the KPI SQL is
    invalid (skipped) or the query fails (swallowed with a warning). Errors here
    must never fail the whole chat request — matches the original sequential
    behavior, just runnable concurrently. The semaphore bounds how many KPIs hit
    ClickHouse at once.
    """
    kpi_sql = kpi.sql.strip().rstrip(";")
    is_valid_kpi, _ = validate_sql(kpi_sql)
    if not is_valid_kpi:
        return None
    kpi_sql = ensure_limit(kpi_sql, max_limit=1)
    async with sem:
        try:
            val = await async_query_value(kpi_sql)
            if val is None or val == "\\N":
                val = None

            # Execute previous period SQL if provided
            prev_val = None
            delta_pct = None
            delta_label = None
            if kpi.previous_sql:
                prev_sql = kpi.previous_sql.strip().rstrip(";")
                is_valid_prev, _ = validate_sql(prev_sql)
                if is_valid_prev:
                    prev_sql = ensure_limit(prev_sql, max_limit=1)
                    try:
                        prev_val = await async_query_value(prev_sql)
                        if prev_val is None or prev_val == "\\N":
                            prev_val = None
                    except Exception as e:
                        log.warning(f"Previous KPI failed ({kpi.label}): {e}")

                # Period-over-period delta — a label (not a bogus %) when the
                # baseline is zero (CLI-42).
                delta_pct, delta_label = compute_kpi_delta(val, prev_val)

            return ContextKPIResult(
                label=kpi.label,
                value=val,
                sql=kpi_sql,
                previous_sql=kpi.previous_sql.strip().rstrip(";") if kpi.previous_sql else None,
                previous_value=prev_val,
                delta_percent=delta_pct,
                delta_label=delta_label,
            )
        except Exception as e:
            log.warning(f"Context KPI failed ({kpi.label}): {e}")
            return None


class SqlPipelineError(Exception):
    """A generated query failed at validation, EXPLAIN, or execution (CLI-144).

    Carries the failing ``stage`` (see ``app.llm.repair``), the client-safe
    ``client_message`` we 422 with (sanitized — no server internals), and the
    fuller ``llm_detail`` fed to the repair prompt. ``llm_detail`` is SQL/schema
    level and never contains CRM row data.
    """

    def __init__(self, stage: str, client_message: str, llm_detail: str):
        self.stage = stage
        self.client_message = client_message
        self.llm_detail = llm_detail
        super().__init__(client_message)


@dataclass
class _ResolvedSql:
    """Outcome of resolving a question to runnable SQL + its rows."""

    response: object  # ChatSQLResponse — original, or the repaired one
    sql: str
    rows: list[dict]
    llm_ms: int
    query_ms: int
    repaired: bool


async def _prepare_and_run(sql: str) -> tuple[str, list[dict]]:
    """Validate -> EXPLAIN dry-run -> execute. Raises ``SqlPipelineError`` on failure.

    Returns the (limit-enforced) SQL actually executed and its rows. The EXPLAIN
    dry-run (CLI-144) is a few-ms plan build that catches runtime errors which
    pass static validation but would fail real execution; gate it off with
    ``CLICKSPOT_SQL_EXPLAIN_DRYRUN=0``.
    """
    is_valid, error = validate_sql(sql)
    if not is_valid:
        raise SqlPipelineError(
            sql_repair.STAGE_VALIDATION,
            f"SQL validation failed: {error}",
            error or "SQL validation failed",
        )

    sql = ensure_limit(sql)

    if sql_repair.explain_enabled():
        try:
            await async_explain(sql)
        except Exception as e:
            # Plan-build failure: log full detail, hand the client a sanitized line.
            log.error(f"EXPLAIN dry-run failed: {e}\nSQL: {sql}")
            raise SqlPipelineError(
                sql_repair.STAGE_EXPLAIN, safe_clickhouse_error(e), str(e)
            ) from e

    try:
        rows = await async_query_rows(sql)
    except Exception as e:
        # Full error + SQL go to the server log; client gets a sanitized one-liner
        # so we don't leak server version / table internals / file paths.
        log.error(f"ClickHouse query failed: {e}\nSQL: {sql}")
        raise SqlPipelineError(
            sql_repair.STAGE_EXECUTION, safe_clickhouse_error(e), str(e)
        ) from e

    return sql, rows


async def resolve_sql(provider, messages: list[dict]) -> _ResolvedSql:
    """Generate SQL, run it, and on failure attempt **one** LLM repair (CLI-144).

    Happy path: generate -> validate -> EXPLAIN -> execute, no extra LLM call.
    On any pipeline failure (and when repair is enabled), feed the failing SQL +
    error back to the provider once, then re-validate/EXPLAIN/execute the
    correction. A single attempt bounds latency: the cost is one extra LLM
    round-trip, paid only on the failure path.

    Emits Langfuse scores so repair rate / success rate are queryable:
    ``sql_repair_attempted`` (0/1) always, ``sql_repair_succeeded`` (0/1) when a
    repair was attempted. Raises ``SqlPipelineError`` if the query still fails;
    propagates provider/transport errors unchanged (the caller maps them to 502).
    """
    t = time.time()
    response = await provider.generate(messages)
    llm_ms = int((time.time() - t) * 1000)
    sql = response.sql.strip().rstrip(";")

    try:
        t = time.time()
        sql, rows = await _prepare_and_run(sql)
        obs.score("sql_repair_attempted", 0)
        return _ResolvedSql(response, sql, rows, llm_ms, int((time.time() - t) * 1000), False)
    except SqlPipelineError as first_err:
        if not sql_repair.repair_enabled():
            obs.score("sql_repair_attempted", 0)
            raise
        obs.score("sql_repair_attempted", 1, comment=f"stage={first_err.stage}")

        repair_messages = messages + [
            sql_repair.build_repair_message(sql, first_err.llm_detail, first_err.stage)
        ]
        try:
            t = time.time()
            repaired = await provider.generate(repair_messages)
            llm_ms += int((time.time() - t) * 1000)
            repaired_sql = repaired.sql.strip().rstrip(";")
            t = time.time()
            repaired_sql, rows = await _prepare_and_run(repaired_sql)
            query_ms = int((time.time() - t) * 1000)
        except Exception as repair_err:
            # Repair didn't land — surface the *original* failure (that's the
            # query the user asked for). Provider/transport errors during repair
            # also fall back here rather than masking the real cause.
            obs.score("sql_repair_succeeded", 0)
            log.warning(f"SQL repair failed (stage={first_err.stage}): {repair_err}")
            raise first_err

        obs.score("sql_repair_succeeded", 1)
        return _ResolvedSql(repaired, repaired_sql, rows, llm_ms, query_ms, True)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # 1. Get LLM provider
    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 2. Build messages for LLM
    messages = [m.model_dump() for m in req.history]
    messages.append({"role": "user", "content": req.message})

    # 3. Generate SQL and run it, with a single EXPLAIN-guarded repair attempt on
    #    failure (CLI-144). Grouped into a Langfuse session per conversation; the
    #    span lets repair-rate/success-rate scores attach to the trace.
    try:
        with obs.session(req.conversation_id), obs.span("sql-pipeline"):
            resolved = await resolve_sql(provider, messages)
    except SqlPipelineError as e:
        # Validation / EXPLAIN / execution failure that survived the repair attempt.
        raise HTTPException(status_code=422, detail=e.client_message)
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        raise HTTPException(status_code=502, detail="LLM provider error; see server log")

    llm_response = resolved.response
    sql, rows = resolved.sql, resolved.rows
    columns = list(rows[0].keys()) if rows else []

    # 4. Execute context KPIs concurrently (non-blocking, errors silently
    # skipped). The KPIs are independent read-only queries, so we fan them out
    # with asyncio.gather instead of a sequential loop (CLI-143). gather
    # preserves input order, so output order is stable; invalid/failed KPIs come
    # back as None and are filtered out.
    sem = asyncio.Semaphore(_CONTEXT_KPI_CONCURRENCY)
    kpi_results = await asyncio.gather(
        *(_run_context_kpi(kpi, sem) for kpi in llm_response.context)
    )
    context_results = [r for r in kpi_results if r is not None]

    return ChatResponse(
        explanation=llm_response.explanation,
        sql=sql,
        results=rows,
        columns=columns,
        row_count=len(rows),
        viz=llm_response.viz,
        title=llm_response.title,
        llm_ms=resolved.llm_ms,
        query_ms=resolved.query_ms,
        context=context_results,
    )


