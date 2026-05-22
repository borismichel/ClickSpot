"""FastAPI routes for data space CRUD, preview, discovery, dashboards, and chat."""

import json
import logging
import re
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.spaces.config import DataSpaceConfig
from app.spaces.discovery import discover_dimensions, get_available_dicts, get_grain_entities
from app.spaces.routes_dashboards import _get_space_dashboard
from app.spaces.registry import (
    create_space,
    delete_space,
    get_space,
    list_spaces,
    preview_space,
    update_space,
)

log = logging.getLogger("app.spaces.routes")

router = APIRouter(prefix="/api/v1/spaces", tags=["spaces"])

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def _validate_id(space_id: str):
    if not _ID_RE.match(space_id):
        raise HTTPException(
            400,
            "ID must be lowercase alphanumeric + underscores, 2-50 chars, starting with a letter",
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===========================================================================
# Data space CRUD
# ===========================================================================

@router.get("")
def api_list_spaces():
    return [s.model_dump() for s in list_spaces()]


@router.get("/entities")
def api_grain_entities():
    return get_grain_entities()


@router.get("/dimensions/{grain_entity}")
def api_discover_dimensions(grain_entity: str):
    dims = discover_dimensions(grain_entity)
    return [
        {
            "entity": d.entity,
            "display_name": d.display_name,
            "join_type": d.join_type,
            "bridge": d.bridge,
            "bridge_grain_key": d.bridge_grain_key,
            "bridge_dim_key": d.bridge_dim_key,
            "dim_key": d.dim_key,
            "fk_from": d.fk_from,
            "fk_to": d.fk_to,
            "dict_name": d.dict_name,
            "dict_columns": d.dict_columns,
            "columns": d.columns,
        }
        for d in dims
    ]


@router.get("/dicts")
def api_available_dicts():
    return get_available_dicts()


@router.get("/dashboards/all")
async def api_list_all_space_dashboards():
    """List all space dashboards across all data spaces."""
    from app.store import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM space_dashboards ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            data = await _get_space_dashboard(db, row["id"])
            if data:
                # Attach space name for display
                config = get_space(row["space_id"])
                data["space_name"] = config.name if config else row["space_id"]
                results.append(data)
        return results
    finally:
        await db.close()


@router.get("/{space_id}")
def api_get_space(space_id: str):
    space = get_space(space_id)
    if not space:
        raise HTTPException(404, f"Data space '{space_id}' not found")
    return space.model_dump()


@router.post("")
def api_create_space(config: DataSpaceConfig):
    _validate_id(config.id)
    try:
        space = create_space(config)
        return space.model_dump()
    except ValueError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        log.exception(f"Failed to create space '{config.id}'")
        raise HTTPException(500, f"Failed to create data space: {e}")


@router.put("/{space_id}")
def api_update_space(space_id: str, config: DataSpaceConfig):
    _validate_id(space_id)
    try:
        space = update_space(space_id, config)
        return space.model_dump()
    except Exception as e:
        log.exception(f"Failed to update space '{space_id}'")
        raise HTTPException(500, f"Failed to update data space: {e}")


@router.delete("/{space_id}")
def api_delete_space(space_id: str):
    try:
        delete_space(space_id)
        return {"deleted": space_id}
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        log.exception(f"Failed to delete space '{space_id}'")
        raise HTTPException(500, f"Failed to delete data space: {e}")


class TestFilterRequest(BaseModel):
    entity: str
    filter: str


@router.post("/test-filter")
async def api_test_filter(req: TestFilterRequest):
    """Run `SELECT count() FROM silver.{entity} WHERE {filter}` to validate a filter.

    Returns either `{ok: true, count: N}` or `{ok: false, error: "..."}`.
    """
    from app.config import TABLES
    from app.db import async_query_value

    if req.entity not in TABLES:
        raise HTTPException(400, f"Unknown entity '{req.entity}'")
    if not req.filter.strip():
        raise HTTPException(400, "Filter is empty")

    sql = f"SELECT count() FROM silver.{req.entity} WHERE {req.filter.strip()}"
    try:
        count = await async_query_value(sql)
        return {"ok": True, "count": count, "sql": sql}
    except Exception as e:
        return {"ok": False, "error": str(e), "sql": sql}


@router.post("/preview")
def api_preview_space(config: DataSpaceConfig):
    try:
        return preview_space(config)
    except Exception as e:
        log.exception("Failed to preview data space")
        raise HTTPException(500, f"Preview failed: {e}")


# ===========================================================================
# Column metadata
# ===========================================================================

@router.get("/{space_id}/columns")
def api_space_columns(space_id: str):
    """Return column metadata for a data space VIEW."""
    from app.config import TABLES

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    columns = []
    grain_meta = TABLES.get(config.grain.entity, {})
    grain_fields = grain_meta.get("fields", {})

    # PK
    columns.append({"name": config.grain.key, "type": "String", "display": config.grain.key})

    # Grain columns
    for col in config.grain.columns:
        fm = grain_fields.get(col, {})
        columns.append({
            "name": col,
            "type": fm.get("type", "String"),
            "display": fm.get("display", col),
        })

    # Dimension columns
    for dim in config.dimensions:
        dim_meta = TABLES.get(dim.entity, {})
        dim_fields = dim_meta.get("fields", {})
        for col in dim.columns:
            fm = dim_fields.get(col, {})
            columns.append({
                "name": f"{dim.prefix}{col}",
                "type": fm.get("type", "String"),
                "display": f"{fm.get('display', col)} ({dim.prefix.rstrip('_')})",
            })

    # Computed columns
    for comp in config.computed:
        columns.append({"name": comp.alias, "type": "computed", "display": comp.alias})

    return columns


@router.get("/{space_id}/stats")
async def api_space_stats(space_id: str):
    """Return star-schema stats: node-level counts + column samples.

    Used by SpaceOverviewPage to render an interactive map of the space.
    One lightweight count per entity (grain + each dimension), no heavy scans.
    """
    from app.config import TABLES
    from app.db import async_query_rows, async_query_value

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    # Total rows in the VIEW itself
    try:
        view_rows = await async_query_value(f"SELECT count() FROM {config.view_name}")
    except Exception as e:
        view_rows = None
        log.warning(f"Failed to count VIEW rows for '{space_id}': {e}")

    # Grain node
    grain_meta = TABLES.get(config.grain.entity, {})
    grain_fields = grain_meta.get("fields", {})
    try:
        grain_count = await async_query_value(f"SELECT count() FROM silver.{config.grain.entity}")
    except Exception:
        grain_count = None

    nodes = [
        {
            "id": "grain",
            "kind": "grain",
            "entity": config.grain.entity,
            "display_name": grain_meta.get("display_name", config.grain.entity),
            "row_count": grain_count,
            "columns": [
                {
                    "name": col,
                    "type": grain_fields.get(col, {}).get("type", "String"),
                    "display": grain_fields.get(col, {}).get("display", col),
                }
                for col in [config.grain.key, *config.grain.columns]
            ],
        }
    ]

    edges = []

    # Dimension nodes
    for i, dim in enumerate(config.dimensions):
        dim_id = f"dim-{i}"
        dim_meta = TABLES.get(dim.entity, {})
        dim_fields = dim_meta.get("fields", {})

        # Row count: silver dim count for fk/bridge, dict count for dict
        dim_count = None
        try:
            if dim.join_type == "dict":
                dim_count = await async_query_value(
                    f"SELECT count() FROM silver.{dim.entity}"
                )
            else:
                dim_count = await async_query_value(
                    f"SELECT count() FROM silver.{dim.entity}"
                )
        except Exception:
            pass

        # Join label + bridge info
        if dim.join_type == "bridge":
            join_label = f"bridge: {dim.bridge}"
            strategy = dim.strategy.value if hasattr(dim.strategy, "value") else str(dim.strategy)
        elif dim.join_type == "fk":
            join_label = f"fk: {dim.fk_from} → {dim.fk_to}"
            strategy = "fk"
        else:
            join_label = f"dict: {dim.dict_name}"
            strategy = "dict"

        nodes.append({
            "id": dim_id,
            "kind": "dimension",
            "entity": dim.entity,
            "display_name": dim_meta.get("display_name", dim.entity),
            "row_count": dim_count,
            "join_type": dim.join_type,
            "strategy": strategy,
            "join_label": join_label,
            "prefix": dim.prefix,
            "columns": [
                {
                    "name": f"{dim.prefix}{col}",
                    "source": col,
                    "type": dim_fields.get(col, {}).get("type", "String"),
                    "display": dim_fields.get(col, {}).get("display", col),
                }
                for col in dim.columns
            ],
        })

        edges.append({
            "id": f"edge-{i}",
            "source": "grain",
            "target": dim_id,
            "label": strategy,
            "join_type": dim.join_type,
        })

    return {
        "space_id": space_id,
        "name": config.name,
        "view_name": config.view_name,
        "view_row_count": view_rows,
        "computed_count": len(config.computed),
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/{space_id}/columns/{col_name}/values")
async def api_column_values(space_id: str, col_name: str):
    """Return distinct values for a column in a data space VIEW."""
    from app.db import async_query_rows

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    # Validate column name to prevent injection
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col_name):
        raise HTTPException(400, "Invalid column name")

    view = config.view_name
    try:
        rows = await async_query_rows(
            f"SELECT DISTINCT {col_name} AS val FROM {view} "
            f"WHERE toString({col_name}) != '' "
            f"ORDER BY val LIMIT 200"
        )
        return [r["val"] for r in rows if r["val"] is not None]
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch column values: {e}")



# ===========================================================================
# Sub-router composition — chat + dashboard endpoints live in sibling files
# (app/spaces/routes_chat.py and app/spaces/routes_dashboards.py) so this
# file stays focused on CRUD/discovery/stats. The URLs are unchanged.
# ===========================================================================

from app.spaces.routes_chat import router as _chat_router
from app.spaces.routes_dashboards import router as _dashboards_router

router.include_router(_chat_router)
router.include_router(_dashboards_router)
