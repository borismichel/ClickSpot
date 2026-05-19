"""REST endpoints for the MCP integration tab.

The MCP server itself (`python -m app.mcp.server`) is a separate process that
reads silver_anon / gold_anon from ClickHouse. This module surfaces the
operator-facing config: how to start it, how to wire it into Claude Desktop,
and whether the anon mirrors are populated enough for queries to actually
return useful data.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter

log = logging.getLogger("app.api.mcp")

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


def _project_root() -> str:
    """Best-effort guess of the operator's project root.

    The MCP server is started by running `python -m app.mcp.server` from this
    directory. The Settings UI shows it in the Claude Desktop snippet so the
    operator can copy-paste without thinking.
    """
    return str(Path(__file__).resolve().parent.parent.parent)


def _python_path() -> str:
    """The python interpreter that's currently running this API.

    Claude Desktop spawns the MCP server, so it needs the absolute interpreter
    path (not just `python`) — the venv won't be on its PATH.
    """
    return sys.executable


def _anon_row_count(client, db: str, table: str) -> int | None:
    try:
        rows = client.query(f"SELECT count() FROM {db}.{table}").result_rows
        return int(rows[0][0]) if rows and rows[0] else 0
    except Exception:
        return None


@router.get("/status")
def mcp_status() -> dict[str, Any]:
    """Return MCP readiness — whether the anon mirrors have rows and the env
    vars the MCP process needs are present."""
    project_root = _project_root()
    python_path = _python_path()
    hubspot_token = bool(os.environ.get("HUBSPOT_TOKEN"))
    hubspot_hub_id = os.environ.get("HUBSPOT_HUB_ID", "")

    anon_silver_tables = [
        "dim_contacts", "dim_companies", "dim_deals", "dim_leads", "dim_owners",
        "fact_form_submissions", "fact_stage_history",
    ]
    anon_gold_tables = [
        "agg_deal_health", "agg_rep_performance", "agg_deal_stage_funnel",
        "agg_source_attribution", "agg_lead_health", "agg_deal_cohorts",
        "fact_pipeline_snapshots",
    ]

    silver_anon_counts: dict[str, int | None] = {}
    gold_anon_counts: dict[str, int | None] = {}
    anon_ready = False
    try:
        from app.db import get_client
        client = get_client()
        for t in anon_silver_tables:
            silver_anon_counts[t] = _anon_row_count(client, "silver_anon", t)
        for t in anon_gold_tables:
            gold_anon_counts[t] = _anon_row_count(client, "gold_anon", t)
        # "Ready" = silver_anon.dim_deals has rows (the most common entrypoint)
        anon_ready = bool(silver_anon_counts.get("dim_deals") or 0)
    except Exception as e:
        log.warning("MCP anon-status probe failed: %s", e)

    return {
        "command": [python_path, "-m", "app.mcp.server"],
        "cwd": project_root,
        "env": {
            "HUBSPOT_TOKEN_set": hubspot_token,
            "HUBSPOT_HUB_ID": hubspot_hub_id or None,
            "CLICKHOUSE_HOST": os.environ.get("CLICKHOUSE_HOST"),
            "CLICKHOUSE_PORT": os.environ.get("CLICKHOUSE_PORT"),
            "CLICKHOUSE_USER": os.environ.get("CLICKHOUSE_USER"),
        },
        "anon_ready": anon_ready,
        "silver_anon_row_counts": silver_anon_counts,
        "gold_anon_row_counts": gold_anon_counts,
    }


@router.get("/claude-desktop-config")
def claude_desktop_config() -> dict[str, Any]:
    """Return the JSON snippet to drop into Claude Desktop's mcp config.

    The snippet pins to the operator's local interpreter + project path and
    forwards the env vars the MCP server needs. The UI presents this with a
    copy button.
    """
    project_root = _project_root()
    python_path = _python_path()

    # Pass-through env so the MCP server inherits CH + HubSpot creds when
    # Claude Desktop spawns it. Falsy values are skipped so they show up as
    # placeholders in the UI, not as empty strings in the JSON.
    env_passthrough: dict[str, str] = {}
    for k in ("HUBSPOT_TOKEN", "HUBSPOT_HUB_ID", "CLICKHOUSE_HOST", "CLICKHOUSE_PORT",
              "CLICKHOUSE_USER", "CLICKHOUSE_PASSWORD"):
        v = os.environ.get(k)
        if v:
            env_passthrough[k] = v

    return {
        "config": {
            "mcpServers": {
                "clickspot": {
                    "command": python_path,
                    "args": ["-m", "app.mcp.server"],
                    "cwd": project_root,
                    "env": env_passthrough,
                },
            },
        },
        "claude_desktop_path_hint": {
            "macos": "~/Library/Application Support/Claude/claude_desktop_config.json",
            "windows": "%APPDATA%\\Claude\\claude_desktop_config.json",
        },
    }
