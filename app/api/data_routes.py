"""Data exploration endpoints — table browser and SQL editor."""

import logging
import re
import time
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import async_query_rows, async_query_value
from app.engine.sql_filter import apply_filters, DashboardFilters
from app.spaces.space_filter import apply_space_filters, SpaceFilter

log = logging.getLogger("app.data_routes")

router = APIRouter(prefix="/api/v1")

_ALLOWED_DATABASES = {"bronze", "silver", "gold"}

# Forbidden keywords (same as sql_validator.py)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|SYSTEM|ATTACH|DETACH|RENAME)\b",
    re.IGNORECASE,
)


def _escape_clickhouse_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


# ------------------------------------------------------------------
# Table browser
# ------------------------------------------------------------------

@router.get("/tables")
async def list_tables():
    """List all tables across bronze, silver, gold databases."""
    result = {}
    for db in _ALLOWED_DATABASES:
        try:
            rows = await async_query_rows(f"SHOW TABLES FROM {db}")
            tables = [r[next(iter(r))] for r in rows]
            result[db] = sorted(tables)
        except Exception:
            result[db] = []
    return result


@router.get("/tables/{database}/{table}")
async def describe_table(database: str, table: str):
    """Get column info and sample rows for a table."""
    if database not in _ALLOWED_DATABASES:
        raise HTTPException(400, f"Database must be one of: {_ALLOWED_DATABASES}")

    # Validate table name (alphanumeric + underscores only)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table):
        raise HTTPException(400, "Invalid table name")

    ref = f"{database}.{table}"

    # Get columns
    try:
        cols = await async_query_rows(f"DESCRIBE TABLE {ref}")
    except Exception as e:
        raise HTTPException(404, f"Table not found: {ref}")

    columns = [
        {"name": c.get("name"), "type": c.get("type"), "default_type": c.get("default_type", "")}
        for c in cols
    ]

    # Row count
    try:
        count = int(await async_query_value(f"SELECT count() FROM {ref}"))
    except Exception:
        count = 0

    # Sample rows (first 50)
    try:
        sample = await async_query_rows(f"SELECT * FROM {ref} LIMIT 50")
    except Exception:
        sample = []

    return {
        "database": database,
        "table": table,
        "columns": columns,
        "row_count": count,
        "sample": sample,
    }


# ------------------------------------------------------------------
# SQL editor
# ------------------------------------------------------------------

class SQLFilters(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    owner_ids: list[str] | None = None
    owner_names: list[str] | None = None
    pipeline_ids: list[str] | None = None
    pipeline_labels: list[str] | None = None


class SpaceFilterPayload(BaseModel):
    column: str
    operator: str
    values: list[str]


class SQLRequest(BaseModel):
    sql: str
    filters: SQLFilters | None = None
    space_filters: list[SpaceFilterPayload] | None = None
    space_view: str | None = None


class SQLResponse(BaseModel):
    columns: list[str]
    rows: list[dict]
    row_count: int
    elapsed_ms: int
    error: str | None = None


@router.post("/sql", response_model=SQLResponse)
async def execute_sql(req: SQLRequest):
    """Execute a read-only SQL query."""
    sql = req.sql.strip().rstrip(";").strip()

    if not sql:
        raise HTTPException(400, "Empty query")

    # Must start with SELECT or WITH
    if not re.match(r"^(SELECT|WITH|SHOW|DESCRIBE|DESC)\b", sql, re.IGNORECASE):
        raise HTTPException(400, "Only SELECT, WITH, SHOW, and DESCRIBE queries are allowed")

    # Block mutation keywords
    match = _FORBIDDEN.search(sql)
    if match:
        raise HTTPException(400, f"Forbidden keyword: {match.group(1)}")

    # Block system tables
    if re.search(r"\bsystem\.\w+", sql, re.IGNORECASE):
        raise HTTPException(400, "Access to system tables is not allowed")

    # Apply dashboard filters if provided
    if req.filters:
        df = DashboardFilters(
            date_from=req.filters.date_from,
            date_to=req.filters.date_to,
            owner_ids=req.filters.owner_ids or [],
            owner_names=req.filters.owner_names or [],
            pipeline_ids=req.filters.pipeline_ids or [],
            pipeline_labels=req.filters.pipeline_labels or [],
        )
        sql = apply_filters(sql, df)

    # Apply space filters if provided
    if req.space_filters and req.space_view:
        sf = [SpaceFilter(column=f.column, operator=f.operator, values=f.values) for f in req.space_filters]
        sql = apply_space_filters(sql, sf, req.space_view)

    # Inject LIMIT if missing (for SELECT/WITH only)
    if re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE):
        if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
            sql = sql + " LIMIT 1000"

    t0 = time.time()
    try:
        rows = await async_query_rows(sql)
        elapsed = int((time.time() - t0) * 1000)
        columns = list(rows[0].keys()) if rows else []
        return SQLResponse(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            elapsed_ms=elapsed,
        )
    except Exception as e:
        # Full error goes to the server log; client gets a sanitized message
        # so we don't leak server version / table internals / file paths.
        import logging as _log
        from app.api.chat_routes import _safe_clickhouse_error
        _log.getLogger("app.data").error(f"SQL execution failed: {e}\nSQL: {sql}")
        elapsed = int((time.time() - t0) * 1000)
        return SQLResponse(
            columns=[],
            rows=[],
            row_count=0,
            elapsed_ms=elapsed,
            error=_safe_clickhouse_error(e),
        )


# ------------------------------------------------------------------
# Dashboard filter options
# ------------------------------------------------------------------

@router.get("/filters/options")
async def filter_options():
    """Return dropdown options for dashboard global filters."""
    owners = []
    pipelines = []
    try:
        owner_rows = await async_query_rows(
            "SELECT owner_id, first_name, last_name "
            "FROM silver.dim_owners WHERE archived = 0 "
            "ORDER BY last_name, first_name"
        )
        owners = [
            {
                "id": r["owner_id"],
                "name": f"{r.get('first_name', '')} {r.get('last_name', '')}".strip(),
            }
            for r in owner_rows
            if r.get("first_name") or r.get("last_name")
        ]
    except Exception as e:
        log.warning(f"Failed to fetch owners for filter options: {e}")

    try:
        pipeline_rows = await async_query_rows(
            "SELECT pipeline_id, label "
            "FROM silver.dim_pipelines WHERE archived = 0 "
            "ORDER BY label"
        )
        pipelines = [
            {"id": r["pipeline_id"], "label": r.get("label", "")}
            for r in pipeline_rows
            if r.get("label")
        ]
    except Exception as e:
        log.warning(f"Failed to fetch pipelines for filter options: {e}")

    return {"owners": owners, "pipelines": pipelines}


@router.get("/filters/values/{filter_name}")
async def filter_values(
    filter_name: str,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Return typeahead values for dashboard global filters."""
    search = _escape_clickhouse_string((q or "").strip())
    search_owner = (
        f"AND positionCaseInsensitive(concat(toString(owner_id), ' ', ifNull(first_name, ''), ' ', ifNull(last_name, '')), '{search}') > 0 "
        if search
        else ""
    )
    search_pipeline = (
        f"AND positionCaseInsensitive(concat(toString(pipeline_id), ' ', ifNull(label, '')), '{search}') > 0 "
        if search
        else ""
    )

    if filter_name == "owner":
        try:
            rows = await async_query_rows(
                "SELECT owner_id AS value, trim(concat(ifNull(first_name, ''), ' ', ifNull(last_name, ''))) AS label "
                "FROM silver.dim_owners WHERE archived = 0 "
                f"{search_owner}"
                "AND toString(owner_id) != '' "
                f"ORDER BY label LIMIT {limit}"
            )
            return [
                {"value": str(row["value"]), "label": row.get("label") or str(row["value"])}
                for row in rows
                if row.get("value") is not None
            ]
        except Exception as e:
            log.warning(f"Failed to fetch owner filter values: {e}")
            return []

    if filter_name == "pipeline":
        try:
            rows = await async_query_rows(
                "SELECT pipeline_id AS value, label "
                "FROM silver.dim_pipelines WHERE archived = 0 "
                f"{search_pipeline}"
                "AND toString(pipeline_id) != '' "
                f"ORDER BY label LIMIT {limit}"
            )
            return [
                {"value": str(row["value"]), "label": row.get("label") or str(row["value"])}
                for row in rows
                if row.get("value") is not None
            ]
        except Exception as e:
            log.warning(f"Failed to fetch pipeline filter values: {e}")
            return []

    raise HTTPException(404, f"Unknown filter '{filter_name}'")
