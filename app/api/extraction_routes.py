"""REST endpoints for HubSpot extraction settings.

  GET  /api/v1/extraction                 — current config + resolved enabled tables
  PUT  /api/v1/extraction                 — validate + cascade + write
  GET  /api/v1/extraction/properties/...  — bronze property introspection (Phase C)
  POST /api/v1/extraction/reload          — Dagster GraphQL code-location reload (Phase D)
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.customer import extraction
from app.customer.extraction_rules import OBJECT_GROUPS, describe_cascade

log = logging.getLogger("app.api.extraction")

router = APIRouter(prefix="/api/v1/extraction", tags=["extraction"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ExtraColumn(BaseModel):
    column: str
    property: str
    type: str


class SilverPropOverride(BaseModel):
    extra: list[ExtraColumn] = []
    removed: list[str] = []


class ActivitiesToggles(BaseModel):
    calls: bool = True
    meetings: bool = True
    emails: bool = True
    notes: bool = True
    tasks: bool = True


class ObjectToggles(BaseModel):
    contacts: bool = True
    companies: bool = True
    deals: bool = True
    leads: bool = True
    owners: bool = True
    deal_pipelines: bool = True
    lead_pipelines: bool = True
    activities: ActivitiesToggles = ActivitiesToggles()
    campaigns: bool = True
    forms: bool = True
    form_submissions: bool = True


class ExtractionConfigBody(BaseModel):
    objects: ObjectToggles
    silver_properties: dict[str, SilverPropOverride] = {}


class ReloadRequest(BaseModel):
    run_bronze: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _resolved_view() -> dict[str, Any]:
    block = extraction.load()
    return {
        "config": block,
        "groups": OBJECT_GROUPS,
        "cascade": describe_cascade(block["objects"]),
        "enabled_bronze_tables": sorted(extraction.get_enabled_bronze_tables()),
        "enabled_assoc_tables": sorted(extraction.get_enabled_assoc_tables()),
        "enabled_silver_tables": sorted(extraction.get_enabled_silver_tables()),
        "enabled_gold_tables": sorted(extraction.get_enabled_gold_tables()),
    }


@router.get("")
def get_extraction() -> dict[str, Any]:
    return _resolved_view()


@router.put("")
def put_extraction(body: ExtractionConfigBody) -> dict[str, Any]:
    """Save the extraction block. Re-applies the cascade so disabled
    dependencies are forced-off even if the client sent them as True."""
    incoming = body.model_dump()
    # Validate that the user isn't trying to remove a locked core column.
    for dim, override in incoming.get("silver_properties", {}).items():
        removed = override.get("removed") or []
        locked = LOCKED_CORE_COLUMNS.get(dim, set())
        bad = [r for r in removed if r in locked]
        if bad:
            raise HTTPException(
                400,
                f"Cannot remove locked core column(s) {bad} from {dim} — these are required "
                "by gold aggregates. Add new columns instead.",
            )
    extraction.save(incoming)

    # Phase B: invalidate the LLM schema cache so the next chat call rebuilds
    # the prompt without the disabled tables.
    try:
        from pathlib import Path
        cache = Path.home() / ".clickspot" / "schema_cache.json"
        if cache.exists():
            cache.unlink()
    except Exception as e:
        log.warning("Failed to invalidate schema cache: %s", e)

    return _resolved_view()


# Columns we refuse to let the user remove via the Properties tab. These are
# referenced by gold aggregates — removing them would break agg_rep_performance,
# agg_deal_health, etc.
LOCKED_CORE_COLUMNS: dict[str, set[str]] = {
    "dim_deals": {
        "dealname", "amount", "pipeline", "dealstage",
        "hubspot_owner_id", "createdate", "closedate",
        "hs_is_closed", "hs_is_closed_won", "deal_currency_code",
        "hs_deal_stage_probability", "hs_manual_forecast_category",
        "days_to_close",
    },
    "dim_contacts": {
        "email", "full_name", "createdate", "lifecyclestage", "hubspot_owner_id",
        "hs_analytics_source", "hs_analytics_source_data_1",
    },
    "dim_companies": {"name", "domain", "createdate"},
    "dim_leads": {
        "hs_lead_name", "hubspot_owner_id", "hs_pipeline", "hs_pipeline_stage",
        "createdate", "associated_deals", "first_outreach_date",
    },
}


@router.get("/locked-columns")
def get_locked_columns() -> dict[str, list[str]]:
    return {dim: sorted(cols) for dim, cols in LOCKED_CORE_COLUMNS.items()}


# ---------------------------------------------------------------------------
# Bronze property introspection (Phase C)
# ---------------------------------------------------------------------------

# Map from extraction object keys → bronze table name. Used so the frontend can
# request /extraction/properties/contacts and we look up hs_contacts.
_PROPERTY_OBJECT_MAP: dict[str, str] = {
    "contacts": "hs_contacts",
    "companies": "hs_companies",
    "deals": "hs_deals",
    "leads": "hs_leads",
}

# HubSpot v3 object-type names (different from our bronze keys for activities).
_HUBSPOT_OBJECT_NAMES: dict[str, str] = {
    "contacts": "contacts",
    "companies": "companies",
    "deals": "deals",
    "leads": "leads",
}


@router.get("/properties/{object_type}")
def get_properties(object_type: str) -> dict[str, Any]:
    """Enumerate bronze properties (from ClickHouse mapKeys) and merge with
    HubSpot property metadata (label/description/type/fieldType) so the
    Property picker can show informed choices."""
    bronze_table = _PROPERTY_OBJECT_MAP.get(object_type)
    if not bronze_table:
        raise HTTPException(404, f"Unknown object_type '{object_type}'. Supported: {sorted(_PROPERTY_OBJECT_MAP)}")

    # Bronze keys with frequency
    bronze_keys: dict[str, int] = {}
    try:
        from app.db import get_client
        client = get_client()
        rows = client.query(
            f"""
            SELECT name, count() AS n
            FROM (
                SELECT arrayJoin(mapKeys(properties)) AS name
                FROM bronze.{bronze_table}
                LIMIT 5000
            )
            GROUP BY name
            ORDER BY n DESC
            """
        ).result_rows
        bronze_keys = {r[0]: int(r[1]) for r in rows}
    except Exception as e:
        log.warning("Bronze introspection failed for %s: %s", bronze_table, e)

    # HubSpot metadata (label, description, type, fieldType)
    hubspot_meta: dict[str, dict[str, str]] = {}
    try:
        token = os.environ.get("HUBSPOT_TOKEN", "").strip()
        if token:
            hs_name = _HUBSPOT_OBJECT_NAMES[object_type]
            resp = requests.get(
                f"https://api.hubapi.com/crm/v3/properties/{hs_name}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            if resp.ok:
                for p in resp.json().get("results", []):
                    hubspot_meta[p["name"]] = {
                        "label": p.get("label") or "",
                        "description": p.get("description") or "",
                        "type": p.get("type") or "",
                        "fieldType": p.get("fieldType") or "",
                    }
    except Exception as e:
        log.warning("HubSpot property fetch failed for %s: %s", object_type, e)

    # Current silver column → bronze property mapping
    dim_name = f"dim_{object_type}"
    locked_cols = LOCKED_CORE_COLUMNS.get(dim_name, set())
    locked_property_keys = set()
    core_property_keys = set()
    try:
        from silver_config import DIM_CONTACTS, DIM_COMPANIES, DIM_DEALS, DIM_LEADS
        _dim_lookup = {
            "dim_contacts": DIM_CONTACTS,
            "dim_companies": DIM_COMPANIES,
            "dim_deals": DIM_DEALS,
            "dim_leads": DIM_LEADS,
        }
        dim_cfg = _dim_lookup.get(dim_name)
        if dim_cfg:
            for col_name, prop_key, _ch_type in dim_cfg["columns"]:
                core_property_keys.add(prop_key)
                if col_name in locked_cols:
                    locked_property_keys.add(prop_key)
    except Exception as e:
        log.warning("Could not load dim config for %s: %s", dim_name, e)

    # User-added extras / removed-keys overrides
    extras, removed = extraction.get_silver_column_overrides(dim_name)
    extra_property_keys = {row[1] for row in extras}

    # Union of all known keys to surface to the picker
    all_keys = set(bronze_keys.keys()) | set(hubspot_meta.keys()) | core_property_keys | extra_property_keys

    rows = []
    for key in sorted(all_keys):
        meta = hubspot_meta.get(key, {})
        bronze_count = bronze_keys.get(key, 0)
        in_bronze = key in bronze_keys
        in_hubspot = key in hubspot_meta
        is_core = key in core_property_keys
        is_extra = key in extra_property_keys
        is_locked = key in locked_property_keys

        # Source classification
        if is_core:
            source = "locked-core" if is_locked else "core"
        elif is_extra:
            source = "extra"
        elif in_bronze and not in_hubspot:
            source = "bronze-only"
        elif in_hubspot and not in_bronze:
            source = "hubspot-only"
        else:
            source = "available"

        from app.customer.hs_type_map import hubspot_to_clickhouse
        suggested_ch_type = hubspot_to_clickhouse(meta.get("type") or "", meta.get("fieldType") or "")

        rows.append({
            "property": key,
            "label": meta.get("label") or key,
            "description": meta.get("description") or "",
            "hubspot_type": meta.get("type") or "",
            "hubspot_field_type": meta.get("fieldType") or "",
            "suggested_ch_type": suggested_ch_type,
            "bronze_count": bronze_count,
            "in_bronze": in_bronze,
            "in_hubspot": in_hubspot,
            "source": source,
            "removed": key in removed,
        })

    return {
        "object_type": object_type,
        "bronze_table": bronze_table,
        "dim_name": dim_name,
        "properties": rows,
    }


# ---------------------------------------------------------------------------
# Dagster reload (Phase D)
# ---------------------------------------------------------------------------


DAGSTER_GRAPHQL_URL = os.environ.get("DAGSTER_GRAPHQL_URL", "http://localhost:8194/graphql")

_LIST_LOCATIONS_QUERY = """
{
  workspaceOrError {
    ... on Workspace {
      locationEntries {
        name
        loadStatus
        locationOrLoadError {
          __typename
          ... on RepositoryLocation {
            repositories { name }
          }
          ... on PythonError {
            message
          }
        }
      }
    }
    ... on PythonError { message }
  }
}
""".strip()

_RELOAD_MUTATION = """
mutation($name: String!) {
  reloadRepositoryLocation(repositoryLocationName: $name) {
    __typename
    ... on WorkspaceLocationEntry { name loadStatus }
    ... on ReloadNotSupported { message }
    ... on RepositoryLocationNotFound { message }
    ... on PythonError { message }
  }
}
""".strip()

_LAUNCH_RUN_MUTATION = """
mutation($selector: JobOrPipelineSelector!, $runConfigData: RunConfigData) {
  launchPipelineExecution(
    executionParams: { selector: $selector, runConfigData: $runConfigData, mode: "default" }
  ) {
    __typename
    ... on LaunchRunSuccess { run { runId status } }
    ... on PythonError { message }
    ... on InvalidStepError { invalidStepKey }
    ... on InvalidOutputError { stepKey invalidOutputName }
    ... on RunConfigValidationInvalid { errors { message } }
    ... on RunConflict { message }
    ... on PresetNotFoundError { message }
    ... on ConflictingExecutionParamsError { message }
  }
}
""".strip()


def _dagster_post(query: str, variables: dict | None = None, timeout: int = 30) -> dict:
    """POST to Dagster GraphQL, surfacing both transport and GraphQL errors."""
    try:
        resp = requests.post(
            DAGSTER_GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            timeout=timeout,
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(503, f"Dagster GraphQL unreachable at {DAGSTER_GRAPHQL_URL}: {e}")
    if resp.status_code >= 500:
        raise HTTPException(502, f"Dagster GraphQL {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except Exception:
        raise HTTPException(502, f"Dagster GraphQL returned non-JSON: {resp.text[:300]}")
    if data.get("errors"):
        # GraphQL query/mutation errors come back as 200 + an `errors` array OR
        # 400 + an `errors` array. Either way, surface the first message.
        msgs = "; ".join(e.get("message", str(e)) for e in data["errors"])
        raise HTTPException(500, f"Dagster GraphQL error: {msgs}")
    return data.get("data") or {}


@router.post("/reload")
def reload_pipeline(body: ReloadRequest) -> dict[str, Any]:
    """Reload Dagster code location, optionally launching bronze_job after."""
    data = _dagster_post(_LIST_LOCATIONS_QUERY)
    workspace = data.get("workspaceOrError") or {}
    entries = workspace.get("locationEntries") or []
    if not entries:
        raise HTTPException(500, "No Dagster code locations found")

    location_names = [e["name"] for e in entries]
    # Pick a (location, repo) pair for the bronze launch.
    primary_loc = entries[0]["name"]
    primary_repo = None
    loc_or_err = entries[0].get("locationOrLoadError") or {}
    repos = loc_or_err.get("repositories") or []
    if repos:
        primary_repo = repos[0]["name"]

    reload_results: list[dict[str, Any]] = []
    for loc in location_names:
        rdata = _dagster_post(_RELOAD_MUTATION, {"name": loc})
        result = rdata.get("reloadRepositoryLocation") or {}
        tn = result.get("__typename")
        if tn in ("ReloadNotSupported", "RepositoryLocationNotFound", "PythonError"):
            raise HTTPException(
                500,
                f"Reload of '{loc}' failed: {tn} — {result.get('message', '')}",
            )
        reload_results.append({"name": loc, "load_status": result.get("loadStatus", "UNKNOWN")})

    run_launched = False
    run_id: str | None = None
    if body.run_bronze:
        if not primary_repo:
            log.warning("Skipping bronze launch — could not determine repository name")
        else:
            try:
                ldata = _dagster_post(
                    _LAUNCH_RUN_MUTATION,
                    {
                        "selector": {
                            "repositoryLocationName": primary_loc,
                            "repositoryName": primary_repo,
                            "jobName": "bronze_job",
                        },
                        "runConfigData": {},
                    },
                )
                lres = ldata.get("launchPipelineExecution") or {}
                if lres.get("__typename") == "LaunchRunSuccess":
                    run_launched = True
                    run_id = (lres.get("run") or {}).get("runId")
                else:
                    log.warning("Bronze launch returned %s: %s", lres.get("__typename"), lres)
            except HTTPException as e:
                log.warning("Bronze launch failed: %s", e.detail)

    return {
        "reloaded": reload_results,
        "run_launched": run_launched,
        "run_id": run_id,
    }
