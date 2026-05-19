"""REST endpoints for the browser onboarding flow.

Mirrors the CLI wizard at app/customer/onboarding.py — preflight status, silver
auto-discovery, amount-column candidates, and read/write of customer.json (the
extraction block is owned by extraction_routes.py).
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.customer import config as customer_config

log = logging.getLogger("app.api.onboarding")

router = APIRouter(prefix="/api/v1", tags=["onboarding"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CustomerConfigPatch(BaseModel):
    """Partial-update body for /customer-config. Any subset of keys is allowed."""

    company_name: str | None = None
    company_blurb: str | None = None
    currency: str | None = None
    currency_symbol: str | None = None
    main_pipeline: str | None = None
    all_pipelines: list[dict] | None = None
    stages: list[str] | None = None
    early_stage: str | None = None
    late_stage: str | None = None
    closed_won_stage: str | None = None
    closed_lost_stage: str | None = None
    canonical_amount_col: str | None = None
    forecast_categories: list[str] | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mask_token(tok: str) -> str:
    if not tok:
        return ""
    if len(tok) <= 8:
        return "***"
    return f"{tok[:4]}…{tok[-4:]}"


def _hub_link(hub_id: str) -> str | None:
    if not hub_id:
        return None
    return f"https://app-eu1.hubspot.com/contacts/{hub_id}"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/onboarding/status")
def onboarding_status() -> dict[str, Any]:
    """Preflight checks for the Onboarding tab — env, ClickHouse, silver, config."""
    token = os.environ.get("HUBSPOT_TOKEN", "").strip()
    hub_id = os.environ.get("HUBSPOT_HUB_ID", "").strip()

    ch_reachable = False
    ch_error: str | None = None
    silver_populated = False
    pipeline_count = 0
    try:
        from app.db import get_client
        client = get_client()
        client.command("SELECT 1")
        ch_reachable = True
        try:
            rows = client.query(
                "SELECT count() FROM silver.dim_pipelines WHERE label != ''"
            ).result_rows
            pipeline_count = int(rows[0][0]) if rows and rows[0] else 0
            silver_populated = pipeline_count > 0
        except Exception as e:
            ch_error = f"silver.dim_pipelines not reachable: {e}"
    except Exception as e:
        ch_error = str(e)

    cfg = customer_config.load()
    complete, missing = customer_config.is_complete(cfg)

    return {
        "env": {
            "hubspot_token": bool(token),
            "hubspot_token_preview": _mask_token(token),
            "hubspot_hub_id": hub_id or None,
            "hub_id_link": _hub_link(hub_id),
        },
        "clickhouse": {
            "reachable": ch_reachable,
            "error": ch_error,
        },
        "silver": {
            "populated": silver_populated,
            "pipeline_count": pipeline_count,
        },
        "customer_config": {
            "complete": complete,
            "missing_keys": missing,
        },
    }


@router.post("/onboarding/discover")
def onboarding_discover() -> dict[str, Any]:
    """Re-run silver auto-discovery and return the discovered dict WITHOUT saving.

    UI shows the diff against current customer.json; the user applies per-row.
    """
    try:
        from app.db import get_client
        client = get_client()
    except Exception as e:
        raise HTTPException(503, f"ClickHouse unreachable: {e}")

    discovered = customer_config.auto_discover(client)
    current = customer_config.load()
    return {
        "current": current,
        "discovered": discovered,
        "merge_preview": customer_config.merge_defaults_only(current, discovered),
    }


@router.get("/onboarding/amount-columns")
def onboarding_amount_columns() -> dict[str, list[str]]:
    """List silver.dim_deals columns that look revenue-shaped."""
    try:
        from app.db import get_client
        client = get_client()
    except Exception as e:
        raise HTTPException(503, f"ClickHouse unreachable: {e}")
    return {"columns": customer_config.discover_amount_columns(client)}


@router.get("/onboarding/pipelines")
def onboarding_pipelines() -> dict[str, list[str]]:
    """List pipeline labels from silver.dim_pipelines. Used to populate the main-pipeline dropdown."""
    try:
        from app.db import get_client
        rows = get_client().query(
            "SELECT label FROM silver.dim_pipelines WHERE label != '' ORDER BY label"
        ).result_rows
        return {"pipelines": [r[0] for r in rows]}
    except Exception as e:
        log.warning("onboarding_pipelines: %s", e)
        return {"pipelines": []}


@router.get("/customer-config")
def get_customer_config() -> dict[str, Any]:
    """Return the full customer.json including the `extraction` block if present.

    Extraction block is read-only here; PUT goes through /extraction.
    """
    return customer_config.load()


@router.put("/customer-config")
def update_customer_config(patch: CustomerConfigPatch) -> dict[str, Any]:
    """Merge-patch update of customer.json. Validates main_pipeline and
    canonical_amount_col against the discovered options when possible."""
    current = customer_config.load()
    updates = {k: v for k, v in patch.model_dump().items() if v is not None}

    # Validate main_pipeline against discovered labels when ClickHouse is up
    if "main_pipeline" in updates:
        try:
            from app.db import get_client
            rows = get_client().query(
                "SELECT label FROM silver.dim_pipelines WHERE label != ''"
            ).result_rows
            labels = {r[0] for r in rows}
            if labels and updates["main_pipeline"] not in labels:
                raise HTTPException(
                    400,
                    f"main_pipeline '{updates['main_pipeline']}' not in silver.dim_pipelines. "
                    f"Available: {sorted(labels)}",
                )
        except HTTPException:
            raise
        except Exception:
            # CH down — skip validation, let the operator save anyway
            pass

    if "canonical_amount_col" in updates:
        try:
            from app.db import get_client
            candidates = set(customer_config.discover_amount_columns(get_client()))
            if candidates and updates["canonical_amount_col"] not in candidates:
                raise HTTPException(
                    400,
                    f"canonical_amount_col '{updates['canonical_amount_col']}' not in dim_deals revenue columns. "
                    f"Available: {sorted(candidates)}",
                )
        except HTTPException:
            raise
        except Exception:
            pass

    current.update(updates)
    customer_config.save(current)
    return current
