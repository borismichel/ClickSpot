"""Per-portal runtime config — loaded from ~/.clickspot/customer.json.

Single source of truth for portal-specific values that the LLM schema prompt,
gold templating, and frontend formatting all consume. Mirrors the pattern of
[app/llm/config.py](../llm/config.py): same ~/.clickspot/ dir, same 0600 perms,
defaults shipped in code so a fresh clone has something usable even before the
file exists.

The config has two filling paths:
1. **Operator-edited** via the onboarding CLI (`python -m app.customer.onboarding`)
   or by hand-editing ~/.clickspot/customer.json.
2. **Auto-discovered** from silver tables on FastAPI startup — only fills keys
   that are still at their default, never overwrites operator choices.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

log = logging.getLogger("app.customer.config")

CONFIG_DIR = Path.home() / ".clickspot"
CONFIG_FILE = CONFIG_DIR / "customer.json"

DEFAULTS: dict[str, Any] = {
    "company_name": "ClickSpot Demo",
    "company_blurb": "",
    "currency": "USD",
    "currency_symbol": "$",
    "main_pipeline": None,
    "all_pipelines": [],
    "stages": [],
    "early_stage": None,
    "late_stage": None,
    "closed_won_stage": None,
    "closed_lost_stage": None,
    "canonical_amount_col": "amount",
    "forecast_categories": ["COMMIT", "BEST_CASE", "MOST_LIKELY", "PIPELINE", "OMIT"],
}


def load() -> dict[str, Any]:
    """Read customer.json, merge over DEFAULTS. Missing file -> DEFAULTS only."""
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open() as f:
                user = json.load(f)
            cfg.update(user)
        except Exception as e:
            log.warning("Failed to read %s: %s; falling back to defaults", CONFIG_FILE, e)
    return cfg


def save(cfg: dict[str, Any]) -> None:
    """Atomically write customer.json with 0600 perms."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, stat.S_IRWXU)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2, default=str))
    os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
    tmp.replace(CONFIG_FILE)


def discover_amount_columns(ch_silver) -> list[str]:
    """Return silver.dim_deals columns that look revenue-shaped.

    Used by the onboarding CLI and the browser onboarding tab so both share one
    detection heuristic. Errors return ['amount'] (the HubSpot default that
    every portal has).
    """
    try:
        rows = ch_silver.query(
            "SELECT name FROM system.columns WHERE database = 'silver' AND table = 'dim_deals' ORDER BY name"
        ).result_rows
        candidates = []
        for (name,) in rows:
            low = name.lower()
            if any(token in low for token in ("amount", "arr", "tcv", "mrr", "revenue", "acv", "value", "price")):
                candidates.append(name)
        candidates.sort(key=lambda n: (n != "amount", n))
        return candidates or ["amount"]
    except Exception as e:
        log.warning("discover_amount_columns failed: %s", e)
        return ["amount"]


def is_complete(cfg: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (complete, missing_keys) — what the onboarding wizard considers required.

    Rules per key:
      - company_name: must be set AND not still at the shipped placeholder
        "ClickSpot Demo" (that placeholder means the operator never customized it).
      - main_pipeline: must be non-empty (default is None, so any truthy value counts).
      - canonical_amount_col: must be non-empty. The default value "amount" is the
        canonical HubSpot field name and is a valid real choice — don't flag it as
        missing just because it matches DEFAULTS.
    """
    missing: list[str] = []
    company_name = (cfg.get("company_name") or "").strip()
    if not company_name or company_name == DEFAULTS["company_name"]:
        missing.append("company_name")
    if not (cfg.get("main_pipeline") or "").strip():
        missing.append("main_pipeline")
    if not (cfg.get("canonical_amount_col") or "").strip():
        missing.append("canonical_amount_col")
    return (len(missing) == 0, missing)


def auto_discover(ch_silver) -> dict[str, Any]:
    """Inspect silver tables to derive portal-specific values.

    Returns a partial dict of keys that could be discovered. Caller is expected
    to merge over the existing config, only filling keys still at their default
    so operator-set values are never overwritten.

    `ch_silver` is a clickhouse_connect client (or anything with `.query_row_block`-
    or `.query`-like behavior). Errors are swallowed and result in an empty dict.
    """
    out: dict[str, Any] = {}
    try:
        # Pipelines: every label in dim_pipelines
        rows = ch_silver.query("SELECT label FROM silver.dim_pipelines WHERE label != '' ORDER BY label").result_rows
        out["all_pipelines"] = [{"label": r[0], "note": ""} for r in rows]

        # Currency: most common deal currency
        rows = ch_silver.query(
            "SELECT topK(1)(deal_currency_code) FROM silver.dim_deals WHERE deal_currency_code != ''"
        ).result_rows
        if rows and rows[0] and rows[0][0]:
            most_common = rows[0][0][0]
            out["currency"] = most_common
            out["currency_symbol"] = {"USD": "$", "EUR": "EUR", "GBP": "GBP"}.get(most_common, most_common)

        # Stages: from the largest pipeline (proxy for "main"), ordered, plus the
        # closed-won / closed-lost detections.
        rows = ch_silver.query("""
            SELECT pipeline, count() AS n FROM silver.dim_deals
            WHERE archived = 0 GROUP BY pipeline ORDER BY n DESC LIMIT 1
        """).result_rows
        biggest_pipeline_id = rows[0][0] if rows else None

        if biggest_pipeline_id:
            stage_rows = ch_silver.query(
                "SELECT label, is_closed, display_order FROM silver.dim_pipeline_stages "
                "WHERE pipeline_id = %(pid)s ORDER BY display_order",
                parameters={"pid": biggest_pipeline_id},
            ).result_rows
            out["stages"] = [r[0] for r in stage_rows]
            non_closed = [r for r in stage_rows if r[1] == 0 or str(r[1]).lower() == "false"]
            if non_closed:
                out["early_stage"] = non_closed[0][0]
                out["late_stage"] = non_closed[-1][0]
            closed_rows = [r for r in stage_rows if r[1] == 1 or str(r[1]).lower() == "true"]
            for r in closed_rows:
                low = r[0].lower()
                if "won" in low or "gewonnen" in low:
                    out["closed_won_stage"] = r[0]
                elif "lost" in low or "verloren" in low:
                    out["closed_lost_stage"] = r[0]
    except Exception as e:
        log.warning("auto_discover failed: %s", e)
    return out


def merge_defaults_only(current: dict[str, Any], discovered: dict[str, Any]) -> dict[str, Any]:
    """Return a new config: discovered values only fill keys still at their default."""
    out = dict(current)
    for key, value in discovered.items():
        if key not in DEFAULTS:
            out[key] = value
            continue
        if out.get(key) == DEFAULTS[key] or out.get(key) in (None, "", []):
            out[key] = value
    return out
