"""MCP server that exposes the ClickSpot ClickHouse warehouse with semantic parity.

Reuses the app's schema prompt, SQL validator, and table catalog so Claude
Desktop (or any MCP client) sees the same dict hints, ILIKE guidance, and
table whitelist as the in-app chat. No LLM lives here — the MCP client
drives SQL generation; this server just exposes grounded context and a
guarded execution path.

Run:  python -m app.mcp.server
Wire into Claude Desktop: see config example in README or sketch in chat.
"""

from __future__ import annotations

import json
import os
from typing import Any

import clickhouse_connect
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from app.config import TABLES
from app.llm.schema_prompt import build_schema_prompt
from app.llm.sql_validator import ensure_limit
from app.mcp.guardrails import (
    ACTIVITY_STRIP_RE,
    EXCLUDED_TABLES,
    MCP_ALLOWED_TABLES,
    reject_excluded_tables,
    validate_mcp_sql,
)
from app.mcp.pii import (
    PRIVACY_POLICY_TEXT,
    apply_privacy,
    hubspot_app_host,
)
from app.semantic.layer import load_cache

load_dotenv()

mcp = FastMCP("ClickSpot")


# ---------------------------------------------------------------------------
# ClickHouse client — one shared read-only connection
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = clickhouse_connect.create_client(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.environ.get("CLICKHOUSE_PORT", "8123")),
            username=os.environ["CLICKHOUSE_USER"],
            password=os.environ["CLICKHOUSE_PASSWORD"],
            send_receive_timeout=120,
            # readonly=2 blocks writes + disallows changing settings
            settings={"readonly": "2"},
        )
    return _client


# ---------------------------------------------------------------------------
# Resources — read-only context the client can pull as needed
# ---------------------------------------------------------------------------

_MCP_PREAMBLE = (
    "IMPORTANT — MCP-ONLY ADDENDUM:\n"
    "1. This MCP reads from the ANONYMIZED layer: silver_anon.* and gold_anon.*\n"
    "   (not silver.* / gold.*). Customer PII (names, emails, phones, company\n"
    "   names, deal names, addresses, etc.) is pre-masked at storage time —\n"
    "   every masked token is a fixed-width '***' so length cannot be inferred.\n"
    "   Owner / rep / pipeline labels are copied verbatim and remain readable.\n"
    "   run_sql still appends <id_col>_url columns with HubSpot record links so\n"
    "   the user can click through to the real (unmasked) record in HubSpot.\n"
    "   Ignore any schema passages that say 'silver.' or 'gold.' — treat every\n"
    "   such reference as 'silver_anon.' / 'gold_anon.'. Use schema://allowed_tables\n"
    "   as the authoritative whitelist.\n"
    "2. Activity/engagement tables are BLOCKED on this MCP: fact_activities and\n"
    "   bridge_activity_contact / _company / _deal are not copied to silver_anon.\n"
    "   Their subjects, call dispositions, email bodies, note content and task\n"
    "   descriptions contain unstructured PII that storage-side masking cannot\n"
    "   scrub, so they are physically absent from the anon layer. Do NOT\n"
    "   reference these tables or the ACTIVITIES entity in any query — run_sql\n"
    "   will reject it.\n\n"
)


def _rewrite_schema_prompt_to_anon(prompt: str) -> str:
    """Rewrite every 'silver.' / 'gold.' reference to its anon counterpart.

    Applied only in the MCP wrapper. The underlying schema prompt (used by the
    in-app chat) still references the real silver/gold databases.
    """
    return (
        prompt
        .replace("silver.", "silver_anon.")
        .replace("gold.", "gold_anon.")
    )


@mcp.resource("schema://prompt")
def schema_prompt() -> str:
    """The full semantic prompt with activity references stripped.

    Reuses the app's schema prompt for semantic parity, but removes any line
    mentioning activity tables so the MCP client doesn't see documentation for
    a blocked capability. The MCP preamble announces the exclusion up front.
    """
    base = build_schema_prompt(load_cache())
    stripped = ACTIVITY_STRIP_RE.sub("", base)
    return _MCP_PREAMBLE + _rewrite_schema_prompt_to_anon(stripped)


@mcp.resource("schema://privacy_policy")
def privacy_policy() -> str:
    """Explains how PII masking and HubSpot URL injection affect run_sql output."""
    return PRIVACY_POLICY_TEXT


@mcp.resource("schema://tables")
def schema_tables() -> str:
    """JSON catalog of queryable tables with their fields, types, and display labels.

    Rewrites database references to the anon layer (silver → silver_anon,
    gold → gold_anon). Activity tables are excluded — their bridges are in
    ALLOWED_TABLES only, not TABLES, so no filter needed there.
    """
    filtered: dict = {}
    for name, meta in TABLES.items():
        raw_db = meta.get("database", "silver")
        if f"{raw_db}.{name}".lower() in {e.lower() for e in EXCLUDED_TABLES}:
            continue
        meta = dict(meta)
        if raw_db == "silver":
            meta["database"] = "silver_anon"
        elif raw_db == "gold":
            meta["database"] = "gold_anon"
        filtered[name] = meta
    return json.dumps(filtered, indent=2, sort_keys=True)


@mcp.resource("schema://allowed_tables")
def allowed_tables() -> str:
    """Newline-separated list of fully-qualified tables accepted by run_sql."""
    return "\n".join(sorted(MCP_ALLOWED_TABLES))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def get_schema() -> str:
    """Return the full query guide: tables, columns, dicts, rules, examples.

    Call this FIRST in every new conversation before writing SQL. It contains:
      - Table and column catalog (silver_anon.* + gold_anon.* + bridges)
      - DICTIONARIES section with dictGet() examples (all resolved against
        silver_anon dictionaries — masked where appropriate)
      - Relative-date and ILIKE guidance for free-text fields
      - PII masking policy (data is pre-masked at storage) + activity block
      - Few-shot SQL examples
    Same content as the schema://prompt resource; exposed as a tool for
    clients that don't surface resources. One call is enough for a session.
    """
    base = build_schema_prompt(load_cache())
    stripped = ACTIVITY_STRIP_RE.sub("", base)
    return _MCP_PREAMBLE + _rewrite_schema_prompt_to_anon(stripped)


@mcp.tool()
def run_sql(sql: str) -> dict[str, Any]:
    """Execute a SELECT against the hs2ch ClickHouse warehouse.

    IMPORTANT: call `get_schema` once at the start of a conversation to load
    the table/column catalog, dictGet patterns, PII policy, and query rules.

    Enforces:
      - SELECT/WITH only; mutations (INSERT/UPDATE/ALTER/...) are blocked.
      - Table whitelist (silver_anon.* + gold_anon.*; activity tables blocked).
      - system / information_schema access blocked.
      - LIMIT 1000 injected if missing.

    PII is pre-masked at storage time in the anon layer, so query results
    cannot contain raw customer names/emails/phones regardless of how the
    query is written. A column-name masking pass still runs as a backstop for
    the dictGet(...dict_contacts...) aliasing edge case.

    Returns: {sql, columns, rows, row_count} with <id_col>_url columns appended
    (HubSpot record links) when IDs are in SELECT.
    """
    ok, err = validate_mcp_sql(sql)
    if not ok:
        return {"error": err}

    excluded_err = reject_excluded_tables(sql)
    if excluded_err:
        return {"error": excluded_err}

    bounded = ensure_limit(sql)
    try:
        result = _get_client().query(bounded)
    except Exception as exc:  # clickhouse_connect raises many subclasses
        return {"error": str(exc), "sql": bounded}

    hub_id = os.environ.get("HUBSPOT_HUB_ID")
    _warn_once_if_hub_id_missing(hub_id)
    columns, rows = apply_privacy(
        list(result.column_names),
        [list(r) for r in result.result_rows],
        hub_id,
        hubspot_app_host(),
    )

    return {
        "sql": bounded,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
    }


_hub_id_warned = False


def _warn_once_if_hub_id_missing(hub_id: str | None) -> None:
    global _hub_id_warned
    if not hub_id and not _hub_id_warned:
        import logging
        logging.getLogger("app.mcp").warning(
            "HUBSPOT_HUB_ID unset — PII still masked but HubSpot URL columns will be omitted."
        )
        _hub_id_warned = True


if __name__ == "__main__":
    mcp.run()  # stdio transport — what Claude Desktop expects
