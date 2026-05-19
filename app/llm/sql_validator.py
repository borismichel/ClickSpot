"""SQL safety validator — ensures LLM-generated SQL is SELECT-only against allowed tables."""

import re

from app.config import TABLES
from app.engine.sql_builder import _table_ref
from silver_config import BRIDGE_TABLES as _SILVER_BRIDGE_TABLES

# Build allowed table references: {"silver.dim_deals", "gold.agg_rep_performance", ...}
ALLOWED_TABLES = set()
for table_name in TABLES:
    ALLOWED_TABLES.add(_table_ref(table_name))

# Bridge tables are also queryable. The simple CRM↔CRM and Lists↔CRM bridges
# live in silver_config.BRIDGE_TABLES — derive from there so new bridges show
# up automatically. The three activity bridges are hand-rolled UNION assets
# (see assets/silver/bridges.py) and not in BRIDGE_TABLES, so list them here.
_HANDROLLED_BRIDGES = [
    "bridge_activity_contact", "bridge_activity_company", "bridge_activity_deal",
]
for silver_table, *_ in _SILVER_BRIDGE_TABLES:
    ALLOWED_TABLES.add(f"silver.{silver_table}")
for bt in _HANDROLLED_BRIDGES:
    ALLOWED_TABLES.add(f"silver.{bt}")

# Forbidden keywords (case-insensitive) — mutation, DDL, server control, batch ingest.
_FORBIDDEN = re.compile(
    r"\b("
    r"INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|"
    r"ATTACH|DETACH|RENAME|"
    r"SYSTEM|OPTIMIZE|KILL|EXCHANGE|FREEZE|UNFREEZE"
    r")\b",
    re.IGNORECASE,
)

# UNION can bypass table whitelisting by piggy-backing a SELECT off a permitted
# table. Block it outright — analytics queries from the chat path don't need UNION.
_UNION_PATTERN = re.compile(r"\bUNION\b", re.IGNORECASE)

# `INTO OUTFILE` / `FORMAT` exfiltration sinks
_OUTFILE_PATTERN = re.compile(r"\bINTO\s+(OUTFILE|DUMPFILE)\b", re.IGNORECASE)

# ClickHouse table functions that bypass the static table whitelist entirely:
# url(), remote(), file(), s3(), hdfs(), mysql(), postgresql(), input(), merge(),
# generateRandom(), cluster(), etc. Any of these in a FROM/JOIN can read external
# data or system internals.
_TABLE_FUNCTIONS = re.compile(
    r"\b("
    r"url|remote|remoteSecure|cluster|clusterAllReplicas|"
    r"file|s3|s3Cluster|hdfs|hdfsCluster|"
    r"mysql|postgresql|mongodb|jdbc|odbc|sqlite|"
    r"input|merge|view"
    r")\s*\(",
    re.IGNORECASE,
)

# Match table references in FROM/JOIN clauses anywhere in the query (including
# subqueries). The regex finds ALL occurrences, so subquery-embedded refs are caught.
_TABLE_REF_PATTERN = re.compile(
    r"(?:FROM|JOIN)\s+(\w+\.\w+)",
    re.IGNORECASE,
)

MAX_LIMIT = 1000


def validate_sql(sql: str) -> tuple[bool, str | None]:
    """Validate LLM-generated SQL.

    Returns (is_valid, error_message). error_message is None if valid.
    """
    stripped = sql.strip().rstrip(";").strip()

    # Must start with SELECT or WITH (for CTEs)
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False, "Query must start with SELECT or WITH"

    # Reject SELECT * — ClickHouse is columnar, enumerate columns explicitly
    if re.search(r"\bSELECT\s+\*\s+FROM\b", stripped, re.IGNORECASE):
        return False, "SELECT * is not allowed — enumerate columns explicitly"

    # Check for forbidden mutation / control keywords
    match = _FORBIDDEN.search(stripped)
    if match:
        return False, f"Forbidden keyword: {match.group(1)}"

    # UNION can bypass the table whitelist
    if _UNION_PATTERN.search(stripped):
        return False, "UNION is not allowed (bypasses table whitelist)"

    # Exfiltration sinks
    if _OUTFILE_PATTERN.search(stripped):
        return False, "INTO OUTFILE / DUMPFILE is not allowed"

    # ClickHouse table functions that read arbitrary external data
    tf = _TABLE_FUNCTIONS.search(stripped)
    if tf:
        return False, f"Table function {tf.group(1)}() is not allowed"

    # Check all table references are in the allowed set (subqueries included)
    table_refs = _TABLE_REF_PATTERN.findall(stripped)
    for ref in table_refs:
        if ref.lower() not in {t.lower() for t in ALLOWED_TABLES}:
            return False, f"Table not allowed: {ref}"

    # Block system tables
    if re.search(r"\bsystem\.\w+", stripped, re.IGNORECASE):
        return False, "Access to system tables is not allowed"
    if re.search(r"\binformation_schema\.\w+", stripped, re.IGNORECASE):
        return False, "Access to information_schema is not allowed"

    return True, None


def ensure_limit(sql: str, max_limit: int = MAX_LIMIT) -> str:
    """Inject LIMIT if not present in the SQL."""
    if re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        return sql
    return sql.rstrip().rstrip(";") + f" LIMIT {max_limit}"
