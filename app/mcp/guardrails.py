"""MCP-specific table-level guardrails.

The MCP surface queries the anonymized layer (`silver_anon.*` / `gold_anon.*`)
instead of the raw `silver.*` / `gold.*` databases. PII is masked at storage
time, so the MCP client (Claude Desktop) physically cannot retrieve raw PII
regardless of what query it writes.

Lives in its own module (not server.py) so it's importable without the optional
`mcp` runtime package installed. The in-app chat path keeps using
`app/llm/sql_validator.py` against the raw silver/gold databases.
"""

from __future__ import annotations

import re

from app.llm.sql_validator import ALLOWED_TABLES

# ---------------------------------------------------------------------------
# Rewrite ALLOWED_TABLES → MCP_ALLOWED_TABLES (silver → silver_anon, etc.)
# ---------------------------------------------------------------------------
# Activity/engagement tables (fact_activities, bridge_activity_*) are NOT
# copied to silver_anon because their free-text subjects, dispositions, email
# bodies and note content cannot be safely masked. Excluding them from the
# anon source also removes them from the MCP surface.

_ACTIVITY_TABLES = {
    "fact_activities",
    "bridge_activity_contact",
    "bridge_activity_company",
    "bridge_activity_deal",
}


def _rewrite_to_anon(t: str) -> str | None:
    """Rewrite 'silver.foo' → 'silver_anon.foo' / 'gold.foo' → 'gold_anon.foo'.

    Returns None if the table is excluded (activity tables).
    """
    if "." not in t:
        return None
    db, name = t.split(".", 1)
    if name in _ACTIVITY_TABLES:
        return None
    if db == "silver":
        return f"silver_anon.{name}"
    if db == "gold":
        return f"gold_anon.{name}"
    return None


MCP_ALLOWED_TABLES: frozenset[str] = frozenset(
    rewritten for rewritten in (_rewrite_to_anon(t) for t in ALLOWED_TABLES)
    if rewritten is not None
)

# Tables that are explicitly blocked even if referenced under the raw silver.*
# namespace. Kept for error messaging — any non-anon reference will fail the
# whitelist check anyway.
EXCLUDED_TABLES: frozenset[str] = frozenset({
    f"silver.{t}" for t in _ACTIVITY_TABLES
})


_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|SYSTEM|ATTACH|DETACH|RENAME)\b",
    re.IGNORECASE,
)

_TABLE_REF_RE = re.compile(r"(?:FROM|JOIN)\s+(\w+\.\w+)", re.IGNORECASE)

# Catches raw silver/gold references anywhere in the query — including inside
# function calls like dictGet('silver.dict_contacts', ...) that the FROM/JOIN
# regex misses. `\b` word boundary excludes `silver_anon.` / `gold_anon.` since
# `_` is a word character.
_RAW_NAMESPACE_RE = re.compile(r"\b(silver|gold)\.\w+", re.IGNORECASE)

# Strip any line from the app schema prompt that mentions activity content,
# so the MCP client isn't tempted by documentation for a blocked capability.
ACTIVITY_STRIP_RE = re.compile(
    r"(?mi)^.*(fact_activities|bridge_activity_|activity_id|ACTIVITIES).*$\n?"
)


def validate_mcp_sql(sql: str) -> tuple[bool, str | None]:
    """Validate an MCP-supplied SQL string against the anon whitelist.

    Mirrors `app.llm.sql_validator.validate_sql` but swaps ALLOWED_TABLES for
    MCP_ALLOWED_TABLES (silver_anon.* + gold_anon.* only).
    """
    stripped = sql.strip().rstrip(";").strip()

    if not re.match(r"^(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False, "Query must start with SELECT or WITH"

    if re.search(r"\bSELECT\s+\*\s+FROM\b", stripped, re.IGNORECASE):
        return False, "SELECT * is not allowed — enumerate columns explicitly"

    match = _FORBIDDEN.search(stripped)
    if match:
        return False, f"Forbidden keyword: {match.group(1)}"

    raw_ref = _RAW_NAMESPACE_RE.search(stripped)
    if raw_ref:
        return False, (
            f"Raw namespace reference not allowed: {raw_ref.group(0)}. MCP reads "
            "from the anonymized layer only — use silver_anon.* / gold_anon.* "
            "(this also blocks dictGet/function-call access to raw silver/gold)."
        )

    allowed_lower = {t.lower() for t in MCP_ALLOWED_TABLES}
    for ref in _TABLE_REF_RE.findall(stripped):
        if ref.lower() not in allowed_lower:
            return False, (
                f"Table not allowed: {ref}. MCP reads from the anonymized layer "
                "only — use silver_anon.* and gold_anon.* (activity tables are "
                "unavailable)."
            )

    if re.search(r"\bsystem\.\w+", stripped, re.IGNORECASE):
        return False, "Access to system tables is not allowed"
    if re.search(r"\binformation_schema\.\w+", stripped, re.IGNORECASE):
        return False, "Access to information_schema is not allowed"

    return True, None


def reject_excluded_tables(sql: str) -> str | None:
    """Return an error message if `sql` references an activity table, else None.

    Kept as a separate pass so the error message is specific (tells the client
    *why* activity tables aren't available). The whitelist check in
    `validate_mcp_sql` would also catch it, but with a generic message.
    """
    refs = _TABLE_REF_RE.findall(sql)
    for ref in refs:
        _, _, name = ref.partition(".")
        if name.lower() in _ACTIVITY_TABLES:
            return (
                f"Table '{ref}' is not available via MCP. Activity/engagement "
                "content (fact_activities and bridge_activity_*) is blocked "
                "because subjects, dispositions, and note/email bodies can "
                "contain unstructured PII that server-side masking cannot scrub."
            )
    return None
