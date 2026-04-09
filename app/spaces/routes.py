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
# Space-scoped chat
# ===========================================================================

from app.api.chat_models import ChatRequest, ChatResponse, ContextKPIResult


@router.post("/{space_id}/chat", response_model=ChatResponse)
async def api_space_chat(space_id: str, req: ChatRequest):
    """Chat scoped to a data space — LLM sees only this VIEW's schema."""
    from app.db import async_query_rows, async_query_value
    from app.llm.providers import get_provider
    from app.llm.sql_validator import validate_sql, ensure_limit
    from app.spaces.space_prompt import build_space_prompt

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    # Build focused prompt for this space
    prompt = build_space_prompt(config)

    # Get LLM provider
    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(503, str(e))

    # Build messages
    messages = [m.model_dump() for m in req.history]
    messages.append({"role": "user", "content": req.message})

    # Call LLM with space-scoped prompt
    t0 = time.time()
    try:
        llm_response = await provider.generate(messages, system_prompt=prompt)
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        raise HTTPException(502, f"LLM error: {e}")
    llm_ms = int((time.time() - t0) * 1000)

    sql = llm_response.sql.strip().rstrip(";")

    # Validate SQL
    is_valid, error = validate_sql(sql)
    if not is_valid:
        raise HTTPException(422, f"SQL validation failed: {error}")
    sql = ensure_limit(sql)

    # Execute on ClickHouse
    t1 = time.time()
    try:
        rows = await async_query_rows(sql)
    except Exception as e:
        log.error(f"ClickHouse query failed: {e}\nSQL: {sql}")
        raise HTTPException(422, f"ClickHouse error: {e}\n\nSQL: {sql}")
    query_ms = int((time.time() - t1) * 1000)

    columns = list(rows[0].keys()) if rows else []

    # Execute context KPIs
    context_results = []
    for kpi in llm_response.context:
        kpi_sql = kpi.sql.strip().rstrip(";")
        is_valid_kpi, _ = validate_sql(kpi_sql)
        if not is_valid_kpi:
            continue
        kpi_sql = ensure_limit(kpi_sql, max_limit=1)
        try:
            val = await async_query_value(kpi_sql)
            if val is None or val == "\\N":
                val = None

            prev_val = None
            delta_pct = None
            if kpi.previous_sql:
                prev_sql = kpi.previous_sql.strip().rstrip(";")
                is_valid_prev, _ = validate_sql(prev_sql)
                if is_valid_prev:
                    prev_sql = ensure_limit(prev_sql, max_limit=1)
                    try:
                        prev_val = await async_query_value(prev_sql)
                        if prev_val is None or prev_val == "\\N":
                            prev_val = None
                    except Exception:
                        pass

                if val is not None and prev_val is not None:
                    try:
                        cur = float(val)
                        prev = float(prev_val)
                        if prev != 0:
                            delta_pct = round((cur - prev) / abs(prev) * 100, 1)
                        elif cur != 0:
                            delta_pct = 100.0
                    except (ValueError, TypeError):
                        pass

            context_results.append(ContextKPIResult(
                label=kpi.label, value=val, sql=kpi_sql,
                previous_sql=kpi.previous_sql,
                previous_value=prev_val, delta_percent=delta_pct,
            ))
        except Exception as e:
            log.warning(f"Context KPI failed ({kpi.label}): {e}")

    return ChatResponse(
        explanation=llm_response.explanation,
        sql=sql, results=rows, columns=columns,
        row_count=len(rows), viz=llm_response.viz,
        title=llm_response.title, llm_ms=llm_ms,
        query_ms=query_ms, context=context_results,
    )


# ===========================================================================
# Space conversation persistence
# ===========================================================================


@router.get("/{space_id}/conversation")
async def api_get_space_conversation(space_id: str):
    """Get or create the conversation for a data space. One per space."""
    from app.store import get_db

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM conversations WHERE space_id = ? ORDER BY updated_at DESC LIMIT 1",
            (space_id,),
        )
        row = await cursor.fetchone()
        if row:
            conv_id = row["id"]
        else:
            # Auto-create conversation for this space
            now = _now()
            conv_id = f"conv-{uuid4().hex[:12]}"
            await db.execute(
                "INSERT INTO conversations (id, space_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, space_id, f"{config.name} Chat", now, now),
            )
            await db.commit()

        # Fetch messages
        cursor = await db.execute(
            "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY sort_order",
            (conv_id,),
        )
        messages = await cursor.fetchall()

        return {
            "id": conv_id,
            "space_id": space_id,
            "messages": [
                {
                    "id": m["id"],
                    "role": m["role"],
                    "content": m["content"],
                    "sql": m["sql"],
                    "viz": m["viz"],
                    "title": m["title"],
                    "context_kpis": json.loads(m["context_kpis"]) if m["context_kpis"] else None,
                }
                for m in messages
            ],
        }
    finally:
        await db.close()


class SpaceMessageRequest(BaseModel):
    role: str
    content: str
    sql: str | None = None
    viz: str | None = None
    title: str | None = None
    context_kpis: list[dict] | None = None
    results: list[dict] | None = None
    columns: list[str] | None = None
    error: str | None = None


@router.post("/{space_id}/conversation/messages", status_code=201)
async def api_add_space_message(space_id: str, req: SpaceMessageRequest):
    """Append a message to the space conversation (auto-creates if needed)."""
    from app.store import get_db

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    db = await get_db()
    try:
        # Get or create conversation
        cursor = await db.execute(
            "SELECT id FROM conversations WHERE space_id = ? ORDER BY updated_at DESC LIMIT 1",
            (space_id,),
        )
        row = await cursor.fetchone()
        if row:
            conv_id = row["id"]
        else:
            now = _now()
            conv_id = f"conv-{uuid4().hex[:12]}"
            await db.execute(
                "INSERT INTO conversations (id, space_id, title, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (conv_id, space_id, f"{config.name} Chat", now, now),
            )

        # Get next sort_order
        cursor = await db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order "
            "FROM conversation_messages WHERE conversation_id = ?",
            (conv_id,),
        )
        sort_row = await cursor.fetchone()
        sort_order = sort_row["next_order"]

        now = _now()
        msg_id = f"msg-{uuid4().hex[:12]}"
        await db.execute(
            "INSERT INTO conversation_messages "
            "(id, conversation_id, role, content, sql, viz, title, context_kpis, created_at, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                msg_id, conv_id, req.role, req.content,
                req.sql, req.viz, req.title,
                json.dumps(req.context_kpis) if req.context_kpis else None,
                now, sort_order,
            ),
        )
        await db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id)
        )
        await db.commit()

        return {"id": msg_id, "conversation_id": conv_id}
    finally:
        await db.close()


@router.delete("/{space_id}/conversation")
async def api_clear_space_conversation(space_id: str):
    """Clear all messages in the space conversation."""
    from app.store import get_db

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM conversations WHERE space_id = ?", (space_id,)
        )
        rows = await cursor.fetchall()
        for row in rows:
            await db.execute(
                "DELETE FROM conversation_messages WHERE conversation_id = ?",
                (row["id"],),
            )
        await db.commit()
        return {"cleared": space_id}
    finally:
        await db.close()


# ===========================================================================
# Space dashboards
# ===========================================================================

class CreateSpaceDashboardRequest(BaseModel):
    title: str


class UpdateSpaceDashboardRequest(BaseModel):
    title: str | None = None
    pinned_columns: list[str] | None = None
    filters: list[dict] | None = None


class AddSpaceDashItemRequest(BaseModel):
    title: str
    sql: str
    viz: str
    context_kpis: list[dict] = []


class SpaceLayoutItem(BaseModel):
    item_id: str
    x: int
    y: int
    w: int
    h: int


class UpdateSpaceLayoutsRequest(BaseModel):
    layouts: list[SpaceLayoutItem]


async def _get_space_dashboard(db, dash_id: str) -> dict | None:
    cursor = await db.execute("SELECT * FROM space_dashboards WHERE id = ?", (dash_id,))
    dash = await cursor.fetchone()
    if not dash:
        return None

    cursor = await db.execute(
        "SELECT * FROM space_dashboard_items WHERE dashboard_id = ? ORDER BY sort_order",
        (dash_id,),
    )
    items = await cursor.fetchall()

    return {
        "id": dash["id"],
        "space_id": dash["space_id"],
        "title": dash["title"],
        "pinned_columns": json.loads(dash["pinned_columns"]),
        "filters": json.loads(dash["filters"]),
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "sql": item["sql"],
                "viz": item["viz"],
                "contextKPIs": json.loads(item["context_kpis"]),
                "layout": {
                    "x": item["layout_x"],
                    "y": item["layout_y"],
                    "w": item["layout_w"],
                    "h": item["layout_h"],
                },
            }
            for item in items
        ],
        "created_at": dash["created_at"],
        "updated_at": dash["updated_at"],
    }


@router.get("/{space_id}/dashboards")
async def api_list_space_dashboards(space_id: str):
    from app.store import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM space_dashboards WHERE space_id = ? ORDER BY updated_at DESC",
            (space_id,),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            data = await _get_space_dashboard(db, row["id"])
            if data:
                results.append(data)
        return results
    finally:
        await db.close()


@router.post("/{space_id}/dashboards", status_code=201)
async def api_create_space_dashboard(space_id: str, req: CreateSpaceDashboardRequest):
    from app.store import get_db
    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    db = await get_db()
    try:
        now = _now()
        dash_id = f"sdash-{uuid4().hex[:12]}"
        await db.execute(
            "INSERT INTO space_dashboards (id, space_id, title, pinned_columns, filters, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (dash_id, space_id, req.title, "[]", "[]", now, now),
        )
        await db.commit()
        return await _get_space_dashboard(db, dash_id)
    finally:
        await db.close()


@router.get("/{space_id}/dashboards/{dash_id}")
async def api_get_space_dashboard(space_id: str, dash_id: str):
    from app.store import get_db
    db = await get_db()
    try:
        data = await _get_space_dashboard(db, dash_id)
        if not data or data["space_id"] != space_id:
            raise HTTPException(404, "Dashboard not found")
        return data
    finally:
        await db.close()


@router.put("/{space_id}/dashboards/{dash_id}")
async def api_update_space_dashboard(space_id: str, dash_id: str, req: UpdateSpaceDashboardRequest):
    from app.store import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM space_dashboards WHERE id = ? AND space_id = ?",
            (dash_id, space_id),
        )
        dash = await cursor.fetchone()
        if not dash:
            raise HTTPException(404, "Dashboard not found")

        now = _now()
        title = req.title if req.title is not None else dash["title"]
        pinned = json.dumps(req.pinned_columns) if req.pinned_columns is not None else dash["pinned_columns"]
        filters = json.dumps(req.filters) if req.filters is not None else dash["filters"]

        await db.execute(
            "UPDATE space_dashboards SET title = ?, pinned_columns = ?, filters = ?, updated_at = ? WHERE id = ?",
            (title, pinned, filters, now, dash_id),
        )
        await db.commit()
        return await _get_space_dashboard(db, dash_id)
    finally:
        await db.close()


@router.delete("/{space_id}/dashboards/{dash_id}")
async def api_delete_space_dashboard(space_id: str, dash_id: str):
    from app.store import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM space_dashboards WHERE id = ? AND space_id = ?",
            (dash_id, space_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, "Dashboard not found")
        return {"deleted": dash_id}
    finally:
        await db.close()


@router.post("/{space_id}/dashboards/{dash_id}/items", status_code=201)
async def api_add_space_dash_item(space_id: str, dash_id: str, req: AddSpaceDashItemRequest):
    from app.store import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id FROM space_dashboards WHERE id = ? AND space_id = ?",
            (dash_id, space_id),
        )
        if not await cursor.fetchone():
            raise HTTPException(404, "Dashboard not found")

        # Auto-position
        cursor = await db.execute(
            "SELECT COALESCE(MAX(layout_y + layout_h), 0) AS max_y, COUNT(*) AS cnt "
            "FROM space_dashboard_items WHERE dashboard_id = ?",
            (dash_id,),
        )
        row = await cursor.fetchone()
        max_y = row["max_y"]
        cnt = row["cnt"]
        col = (cnt % 3) * 4

        now = _now()
        item_id = f"sitem-{uuid4().hex[:12]}"
        await db.execute(
            "INSERT INTO space_dashboard_items "
            "(id, dashboard_id, title, sql, viz, context_kpis, layout_x, layout_y, layout_w, layout_h, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, dash_id, req.title, req.sql, req.viz, json.dumps(req.context_kpis), col, max_y, 4, 4, cnt),
        )
        await db.execute(
            "UPDATE space_dashboards SET updated_at = ? WHERE id = ?", (now, dash_id)
        )
        await db.commit()
        return await _get_space_dashboard(db, dash_id)
    finally:
        await db.close()


@router.delete("/{space_id}/dashboards/{dash_id}/items/{item_id}")
async def api_remove_space_dash_item(space_id: str, dash_id: str, item_id: str):
    from app.store import get_db
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM space_dashboard_items WHERE id = ? AND dashboard_id = ?",
            (item_id, dash_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, "Item not found")
        await db.execute(
            "UPDATE space_dashboards SET updated_at = ? WHERE id = ?", (_now(), dash_id)
        )
        await db.commit()
        return await _get_space_dashboard(db, dash_id)
    finally:
        await db.close()


@router.put("/{space_id}/dashboards/{dash_id}/layouts")
async def api_update_space_layouts(space_id: str, dash_id: str, req: UpdateSpaceLayoutsRequest):
    from app.store import get_db
    db = await get_db()
    try:
        for layout in req.layouts:
            await db.execute(
                "UPDATE space_dashboard_items SET layout_x = ?, layout_y = ?, layout_w = ?, layout_h = ? "
                "WHERE id = ? AND dashboard_id = ?",
                (layout.x, layout.y, layout.w, layout.h, layout.item_id, dash_id),
            )
        await db.execute(
            "UPDATE space_dashboards SET updated_at = ? WHERE id = ?", (_now(), dash_id)
        )
        await db.commit()
        return await _get_space_dashboard(db, dash_id)
    finally:
        await db.close()
