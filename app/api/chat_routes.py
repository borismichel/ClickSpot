"""Chat API routes — natural language → SQL → ClickHouse results.

LLM provider config, OAuth, and schema-cache endpoints used to live here for
historical reasons; they now live in app/api/llm_routes.py.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException

from app.api.chat_models import ChatRequest, ChatResponse, ContextKPIResult
from app.ch_errors import safe_clickhouse_error
from app.db import async_query_rows, async_query_value
from app.llm import observability as obs
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

    # 3. Call LLM (grouped into a Langfuse session per conversation when tracing is on)
    t0 = time.time()
    try:
        with obs.session(req.conversation_id):
            llm_response = await provider.generate(messages)
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        raise HTTPException(status_code=502, detail="LLM provider error; see server log")
    llm_ms = int((time.time() - t0) * 1000)

    sql = llm_response.sql.strip().rstrip(";")

    # 4. Validate SQL
    is_valid, error = validate_sql(sql)
    if not is_valid:
        raise HTTPException(status_code=422, detail=f"SQL validation failed: {error}")

    sql = ensure_limit(sql)

    # 5. Execute on ClickHouse
    t1 = time.time()
    try:
        rows = await async_query_rows(sql)
    except Exception as e:
        # Full error + SQL go to the server log; client gets a sanitized one-liner
        # so we don't leak server version / table internals / file paths.
        log.error(f"ClickHouse query failed: {e}\nSQL: {sql}")
        raise HTTPException(status_code=422, detail=safe_clickhouse_error(e))
    query_ms = int((time.time() - t1) * 1000)

    columns = list(rows[0].keys()) if rows else []

    # 6. Execute context KPIs concurrently (non-blocking, errors silently
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
        llm_ms=llm_ms,
        query_ms=query_ms,
        context=context_results,
    )


