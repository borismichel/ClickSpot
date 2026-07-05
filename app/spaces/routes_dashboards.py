"""Space-scoped dashboard CRUD, items, and layouts.

Lifted out of app/spaces/routes.py.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.spaces.registry import get_space

log = logging.getLogger("app.spaces.routes.dashboards")

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GenerateDashboardSpecRequest(BaseModel):
    description: str = Field(min_length=1, max_length=2000)


@router.post("/{space_id}/dashboard/spec")
async def api_generate_dashboard_spec(space_id: str, req: GenerateDashboardSpecRequest):
    """One Shot Dashboard (CLI-127): generate a validated multi-widget spec.

    Turns a plain-English analysis case into an ordered dashboard spec scoped to
    this data space's schema. The LLM sees only the space's schema/semantic layer
    (never row data); each widget's SQL is validated and run through the existing
    query path with a bounded self-repair retry.
    """
    from app.llm.dashboard_spec import generate_dashboard_spec
    from app.llm.providers import get_provider

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(503, str(e))

    try:
        spec = await generate_dashboard_spec(config, req.description, provider=provider)
    except Exception as e:  # noqa: BLE001
        log.error(f"Dashboard spec generation failed for space '{space_id}': {e}")
        raise HTTPException(502, f"Dashboard generation error: {e}")

    return spec.model_dump()


@router.post("/{space_id}/dashboard/spec/stream")
async def api_stream_dashboard_spec(space_id: str, req: GenerateDashboardSpecRequest):
    """Streaming variant of the One Shot Dashboard generator (CLI-128).

    Same work as ``POST .../dashboard/spec`` but returns Server-Sent Events so the
    frontend can render an honest progress bar. Each SSE ``data:`` line is a JSON
    ``DashboardEvent`` (``planning`` -> per-widget ``running``/``validated``
    -> ``done``); the terminal ``done`` event carries the full spec. A failure
    after the stream opens — including a zero-widget plan — is reported as an
    ``error`` event rather than an HTTP status, since the 200 response has
    already started.
    """
    from app.llm.dashboard_spec import DashboardEvent, stream_dashboard_spec
    from app.llm.providers import get_provider

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(503, str(e))

    async def event_stream():
        try:
            async for event in stream_dashboard_spec(config, req.description, provider=provider):
                yield f"data: {event.model_dump_json()}\n\n"
        except Exception as e:  # noqa: BLE001 — stream already open, can't raise HTTP
            log.error(f"Dashboard spec stream failed for space '{space_id}': {e}")
            err = DashboardEvent(stage="error", error=f"Dashboard generation error: {e}")
            yield f"data: {err.model_dump_json()}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable proxy buffering so events flush live
        },
    )


class RegenerateWidgetRequest(BaseModel):
    """Per-widget regenerate input (CLI-159).

    ``intent``/``sql`` describe the widget to regenerate; ``error`` (when the
    widget failed) and ``instruction`` (a user tweak, e.g. "make this monthly")
    steer the model. Both are optional and may be combined.
    """

    intent: str = Field(min_length=1, max_length=2000)
    sql: str = Field(min_length=1, max_length=20000)
    error: str | None = Field(default=None, max_length=8000)
    instruction: str | None = Field(default=None, max_length=2000)


@router.post("/{space_id}/dashboard/widget/regenerate")
async def api_regenerate_widget(space_id: str, req: RegenerateWidgetRequest):
    """One Shot Dashboard (CLI-159): regenerate a single widget's SQL.

    The non-streaming backend for the iteration loop (B3) and one-click repair of
    a failed widget. Produces new SQL via the LLM — steered by an optional error
    (fix it) and/or instruction (change it) — then runs it through the same
    validator/limit/query path as generation with a bounded self-repair retry.
    The LLM only ever sees the space schema and the error *text* (never rows),
    preserving the CLI-126 privacy invariant.
    """
    from app.llm.dashboard_spec import regenerate_widget
    from app.llm.providers import get_provider

    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(503, str(e))

    try:
        result = await regenerate_widget(
            config,
            req.intent,
            req.sql,
            error=req.error,
            instruction=req.instruction,
            provider=provider,
        )
    except Exception as e:  # noqa: BLE001 — log full, return sanitized (no provider internals)
        log.error(f"Widget regeneration failed for space '{space_id}': {e}")
        raise HTTPException(502, "Widget regeneration error")

    return result.model_dump()


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


class DraftWidgetLayout(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 4
    h: int = 4


class SaveDraftWidget(BaseModel):
    title: str
    intent: str = ""
    sql: str
    viz: str
    status: str = "ok"
    layout: DraftWidgetLayout = Field(default_factory=DraftWidgetLayout)
    context_kpis: list[dict] = []


class SaveDraftDashboardRequest(BaseModel):
    """Promote a transient One Shot Dashboard draft into a saved space dashboard.

    Carries the whole draft so the create happens in one transaction, preserving
    each widget's (possibly user-edited) SQL, viz type, and grid layout, plus the
    dashboard-level filters. Provenance (CLI-164/A5) rides along too: the
    originating prompt (``source_description``) and each widget's business-question
    ``intent`` are persisted rather than dropped at save time.
    """

    title: str = Field(min_length=1, max_length=200)
    source_description: str = ""
    filters: list[dict] = []
    widgets: list[SaveDraftWidget] = []
    # Guard against silently saving broken widgets (A5): a draft carrying any
    # error-status widget is rejected unless the caller explicitly opts in after
    # being warned.
    allow_error_widgets: bool = False


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
        "source_description": dash["source_description"],
        "pinned_columns": json.loads(dash["pinned_columns"]),
        "filters": json.loads(dash["filters"]),
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "intent": item["intent"],
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


@router.post("/{space_id}/dashboards/draft", status_code=201)
async def api_save_draft_dashboard(space_id: str, req: SaveDraftDashboardRequest):
    """One Shot Dashboard (CLI-130): promote a transient draft to a saved dashboard.

    The whole draft is persisted in a single transaction so the saved dashboard is
    a faithful snapshot of what the user saw: widget order, each widget's
    (generated or hand-edited) SQL and viz type, the grid layout, and the
    dashboard-level filters all round-trip on the subsequent reload. SQL is stored
    verbatim — it was already validated during generation and is run live in the
    draft — matching the existing add-item path.
    """
    from app.store import get_db
    config = get_space(space_id)
    if not config:
        raise HTTPException(404, f"Data space '{space_id}' not found")

    # Don't silently save broken widgets (A5): a draft carrying error-status
    # widgets would error on every load. Reject with the offending titles so the
    # UI can warn; the caller re-sends with allow_error_widgets to save anyway.
    broken = [w.title for w in req.widgets if w.status == "error"]
    if broken and not req.allow_error_widgets:
        raise HTTPException(
            409,
            detail={
                "error": "error_widgets",
                "message": (
                    f"{len(broken)} widget(s) failed to generate and will error on "
                    "every load. Fix or remove them, or save anyway."
                ),
                "widgets": broken,
            },
        )

    db = await get_db()
    try:
        now = _now()
        dash_id = f"sdash-{uuid4().hex[:12]}"
        await db.execute(
            "INSERT INTO space_dashboards "
            "(id, space_id, title, source_description, pinned_columns, filters, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (dash_id, space_id, req.title, req.source_description, "[]", json.dumps(req.filters), now, now),
        )
        for sort_order, widget in enumerate(req.widgets):
            item_id = f"sitem-{uuid4().hex[:12]}"
            await db.execute(
                "INSERT INTO space_dashboard_items "
                "(id, dashboard_id, title, intent, sql, viz, context_kpis, layout_x, layout_y, layout_w, layout_h, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id,
                    dash_id,
                    widget.title,
                    widget.intent,
                    widget.sql,
                    widget.viz,
                    json.dumps(widget.context_kpis),
                    widget.layout.x,
                    widget.layout.y,
                    widget.layout.w,
                    widget.layout.h,
                    sort_order,
                ),
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
