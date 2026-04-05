"""SQL safety validator — ensures LLM-generated SQL is SELECT-only against allowed tables."""

import re

from app.config import TABLES
from app.engine.sql_builder import _table_ref

# Build allowed table references: {"silver.dim_deals", "gold.agg_rep_performance", ...}
ALLOWED_TABLES = set()
for table_name in TABLES:
    ALLOWED_TABLES.add(_table_ref(table_name))

# Bridge tables are also queryable
_BRIDGE_TABLES = [
    "bridge_contact_company", "bridge_contact_deal", "bridge_deal_company",
    "bridge_lead_contact", "bridge_deal_lead", "bridge_lead_company",
    "bridge_activity_contact", "bridge_activity_company", "bridge_activity_deal",
]
for bt in _BRIDGE_TABLES:
    ALLOWED_TABLES.add(f"silver.{bt}")

# Forbidden keywords (case-insensitive)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|SYSTEM|ATTACH|DETACH|RENAME)\b",
    re.IGNORECASE,
)

# Match table references in FROM/JOIN clauses
_TABLE_REF_PATTERN = re.compile(
    r"(?:FROM|JOIN)\s+(\w+\.\w+)",
    re.IGNORECASE,
)

MAX_LIMIT = 10000


def validate_sql(sql: str) -> tuple[bool, str | None]:
    """Validate LLM-generated SQL.

    Returns (is_valid, error_message). error_message is None if valid.
    """
    stripped = sql.strip().rstrip(";").strip()

    # Must start with SELECT or WITH (for CTEs)
    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False, "Query must start with SELECT or WITH"

    # Check for forbidden mutation keywords
    match = _FORBIDDEN.search(stripped)
    if match:
        return False, f"Forbidden keyword: {match.group(1)}"

    # Check all table references are in the allowed set
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
