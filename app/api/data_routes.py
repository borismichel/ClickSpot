"""Data exploration endpoints — table browser and SQL editor."""

import re
import time
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import async_query_rows, async_query_value

router = APIRouter(prefix="/api/v1")

_ALLOWED_DATABASES = {"bronze", "silver", "gold"}

# Forbidden keywords (same as sql_validator.py)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|SYSTEM|ATTACH|DETACH|RENAME)\b",
    re.IGNORECASE,
)


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

class SQLRequest(BaseModel):
    sql: str


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
        elapsed = int((time.time() - t0) * 1000)
        return SQLResponse(
            columns=[],
            rows=[],
            row_count=0,
            elapsed_ms=elapsed,
            error=str(e),
        )
