"""Space-scoped chat + conversation endpoints.

Lifted out of app/spaces/routes.py. The router declared here is included into
the main spaces router from routes.py's __init__-style composition so the URLs
(/api/v1/spaces/{space_id}/chat etc.) stay the same.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.chat_models import ChatRequest, ChatResponse, ContextKPIResult
from app.spaces.registry import get_space


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

log = logging.getLogger("app.spaces.routes.chat")

router = APIRouter()


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

