"""Chat API routes — natural language → SQL → ClickHouse results.

LLM provider config, OAuth, and schema-cache endpoints used to live here for
historical reasons; they now live in app/api/llm_routes.py.
"""

import logging
import re
import time

from fastapi import APIRouter, HTTPException


# ClickHouse error messages look like:
#   "Code: 60. DB::Exception: Received from localhost:9000. DB::Exception: Table
#    silver.dim_foo doesn't exist. (UNKNOWN_TABLE) (version 26.2.5.45 ...)"
# We surface the user-meaningful error class (UNKNOWN_TABLE) and Code: N, but
# strip the full message (which can leak server version, file paths, internal
# table names) before returning to the client.
_CH_ERROR_CODE_RE = re.compile(r"Code:\s*(\d+)")
_CH_ERROR_CLASS_RE = re.compile(r"\(([A-Z_][A-Z0-9_]*)\)")


def _safe_clickhouse_error(exc: Exception) -> str:
    """Convert a clickhouse_connect exception into a short client-safe message.

    Falls back to a generic message if nothing useful can be extracted —
    full details remain in the server-side log.
    """
    msg = str(exc)
    code = _CH_ERROR_CODE_RE.search(msg)
    klass = _CH_ERROR_CLASS_RE.search(msg)
    if code and klass:
        return f"ClickHouse error {code.group(1)}: {klass.group(1)}"
    if klass:
        return f"ClickHouse error: {klass.group(1)}"
    return "Query execution failed"

from app.api.chat_models import ChatRequest, ChatResponse, ContextKPIResult
from app.db import async_query_rows, async_query_value
from app.llm.providers import get_provider
from app.llm.sql_validator import validate_sql, ensure_limit

router = APIRouter(prefix="/api/v1")
log = logging.getLogger("app.chat")


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

    # 3. Call LLM
    t0 = time.time()
    try:
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
        raise HTTPException(status_code=422, detail=_safe_clickhouse_error(e))
    query_ms = int((time.time() - t1) * 1000)

    columns = list(rows[0].keys()) if rows else []

    # 6. Execute context KPIs (non-blocking, errors silently skipped)
    context_results = []
    for kpi in llm_response.context:
        kpi_sql = kpi.sql.strip().rstrip(";")
        is_valid_kpi, _ = validate_sql(kpi_sql)
        if not is_valid_kpi:
            continue
        kpi_sql = ensure_limit(kpi_sql, max_limit=1)
        try:
            val = await async_query_value(kpi_sql)
            if val is None or val == "\\N":
                val = None

            # Execute previous period SQL if provided
            prev_val = None
            delta_pct = None
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

                # Compute delta percent
                if val is not None and prev_val is not None:
                    try:
                        cur = float(val)
                        prev = float(prev_val)
                        if prev != 0:
                            delta_pct = round((cur - prev) / abs(prev) * 100, 1)
                        elif cur != 0:
                            delta_pct = 100.0
                    except (ValueError, TypeError):
                        pass

            context_results.append(ContextKPIResult(
                label=kpi.label,
                value=val,
                sql=kpi_sql,
                previous_sql=kpi.previous_sql.strip().rstrip(";") if kpi.previous_sql else None,
                previous_value=prev_val,
                delta_percent=delta_pct,
            ))
        except Exception as e:
            log.warning(f"Context KPI failed ({kpi.label}): {e}")

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


