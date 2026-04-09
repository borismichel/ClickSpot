"""REST endpoints for dashboards (replaces localStorage persistence)."""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import get_db

log = logging.getLogger("app.api.dashboards")

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreateDashboardRequest(BaseModel):
    title: str


class UpdateDashboardRequest(BaseModel):
    title: str | None = None
    filters: dict | None = None


class AddItemRequest(BaseModel):
    object_id: str


class LayoutItem(BaseModel):
    object_id: str
    x: int
    y: int
    w: int
    h: int


class UpdateLayoutsRequest(BaseModel):
    layouts: list[LayoutItem]


class BulkImportDashboard(BaseModel):
    id: str
    title: str
    items: list[dict]  # [{objectId, layout: {x,y,w,h}}]
    filters: dict = {}
    created_at: str | None = None
    updated_at: str | None = None


class BulkImportRequest(BaseModel):
    dashboards: list[BulkImportDashboard]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _get_dashboard_with_items(db, dash_id: str) -> dict | None:
    cursor = await db.execute("SELECT * FROM dashboards WHERE id = ?", (dash_id,))
    dash = await cursor.fetchone()
    if not dash:
        return None

    cursor = await db.execute(
        "SELECT di.object_id, di.layout_x, di.layout_y, di.layout_w, di.layout_h, di.sort_order, "
        "so.title, so.sql, so.viz, so.context_kpis "
        "FROM dashboard_items di "
        "JOIN saved_objects so ON di.object_id = so.id "
        "WHERE di.dashboard_id = ? "
        "ORDER BY di.sort_order",
        (dash_id,),
    )
    items = await cursor.fetchall()

    return {
        "id": dash["id"],
        "title": dash["title"],
        "filters": json.loads(dash["filters"]),
        "items": [
            {
                "objectId": item["object_id"],
                "layout": {
                    "x": item["layout_x"],
                    "y": item["layout_y"],
                    "w": item["layout_w"],
                    "h": item["layout_h"],
                },
            }
            for item in items
        ],
        "createdAt": dash["created_at"],
        "updatedAt": dash["updated_at"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_dashboards():
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM dashboards ORDER BY updated_at DESC")
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            data = await _get_dashboard_with_items(db, row["id"])
            if data:
                results.append(data)
        return results
    finally:
        await db.close()


@router.get("/{dash_id}")
async def get_dashboard(dash_id: str):
    db = await get_db()
    try:
        data = await _get_dashboard_with_items(db, dash_id)
        if not data:
            raise HTTPException(404, "Dashboard not found")
        return data
    finally:
        await db.close()


@router.post("", status_code=201)
async def create_dashboard(req: CreateDashboardRequest):
    db = await get_db()
    try:
        now = _now()
        dash_id = f"dash-{uuid4().hex[:12]}"
        await db.execute(
            "INSERT INTO dashboards (id, title, filters, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (dash_id, req.title, "{}", now, now),
        )
        await db.commit()
        return await _get_dashboard_with_items(db, dash_id)
    finally:
        await db.close()


@router.put("/{dash_id}")
async def update_dashboard(dash_id: str, req: UpdateDashboardRequest):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT * FROM dashboards WHERE id = ?", (dash_id,))
        dash = await cursor.fetchone()
        if not dash:
            raise HTTPException(404, "Dashboard not found")

        now = _now()
        new_title = req.title if req.title is not None else dash["title"]
        new_filters = json.dumps(req.filters) if req.filters is not None else dash["filters"]

        await db.execute(
            "UPDATE dashboards SET title = ?, filters = ?, updated_at = ? WHERE id = ?",
            (new_title, new_filters, now, dash_id),
        )
        await db.commit()
        return await _get_dashboard_with_items(db, dash_id)
    finally:
        await db.close()


@router.delete("/{dash_id}")
async def delete_dashboard(dash_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM dashboards WHERE id = ?", (dash_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, "Dashboard not found")
        return {"deleted": dash_id}
    finally:
        await db.close()


@router.post("/{dash_id}/items", status_code=201)
async def add_item(dash_id: str, req: AddItemRequest):
    db = await get_db()
    try:
        # Verify dashboard exists
        cursor = await db.execute("SELECT id FROM dashboards WHERE id = ?", (dash_id,))
        if not await cursor.fetchone():
            raise HTTPException(404, "Dashboard not found")

        # Verify object exists
        cursor = await db.execute("SELECT id FROM saved_objects WHERE id = ?", (req.object_id,))
        if not await cursor.fetchone():
            raise HTTPException(404, "Object not found")

        # Check if already in dashboard
        cursor = await db.execute(
            "SELECT 1 FROM dashboard_items WHERE dashboard_id = ? AND object_id = ?",
            (dash_id, req.object_id),
        )
        if await cursor.fetchone():
            raise HTTPException(409, "Object already in dashboard")

        # Auto-position: next row, 4 cols wide
        cursor = await db.execute(
            "SELECT COALESCE(MAX(layout_y + layout_h), 0) AS max_y, COUNT(*) AS cnt "
            "FROM dashboard_items WHERE dashboard_id = ?",
            (dash_id,),
        )
        row = await cursor.fetchone()
        max_y = row["max_y"]
        cnt = row["cnt"]
        col = (cnt % 3) * 4

        await db.execute(
            "INSERT INTO dashboard_items (dashboard_id, object_id, layout_x, layout_y, layout_w, layout_h, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (dash_id, req.object_id, col, max_y, 4, 4, cnt),
        )
        await db.execute(
            "UPDATE dashboards SET updated_at = ? WHERE id = ?", (_now(), dash_id)
        )
        await db.commit()
        return await _get_dashboard_with_items(db, dash_id)
    finally:
        await db.close()


@router.delete("/{dash_id}/items/{object_id}")
async def remove_item(dash_id: str, object_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "DELETE FROM dashboard_items WHERE dashboard_id = ? AND object_id = ?",
            (dash_id, object_id),
        )
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, "Item not found in dashboard")
        await db.execute(
            "UPDATE dashboards SET updated_at = ? WHERE id = ?", (_now(), dash_id)
        )
        await db.commit()
        return await _get_dashboard_with_items(db, dash_id)
    finally:
        await db.close()


@router.put("/{dash_id}/layouts")
async def update_layouts(dash_id: str, req: UpdateLayoutsRequest):
    db = await get_db()
    try:
        for layout in req.layouts:
            await db.execute(
                "UPDATE dashboard_items SET layout_x = ?, layout_y = ?, layout_w = ?, layout_h = ? "
                "WHERE dashboard_id = ? AND object_id = ?",
                (layout.x, layout.y, layout.w, layout.h, dash_id, layout.object_id),
            )
        await db.execute(
            "UPDATE dashboards SET updated_at = ? WHERE id = ?", (_now(), dash_id)
        )
        await db.commit()
        return await _get_dashboard_with_items(db, dash_id)
    finally:
        await db.close()


@router.post("/import", status_code=200)
async def bulk_import(req: BulkImportRequest):
    """Import dashboards from localStorage migration."""
    db = await get_db()
    try:
        imported = 0
        for dash in req.dashboards:
            # Skip if dashboard ID already exists
            cursor = await db.execute("SELECT id FROM dashboards WHERE id = ?", (dash.id,))
            if await cursor.fetchone():
                continue

            now = _now()
            await db.execute(
                "INSERT INTO dashboards (id, title, filters, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    dash.id,
                    dash.title,
                    json.dumps(dash.filters),
                    dash.created_at or now,
                    dash.updated_at or now,
                ),
            )
            for i, item in enumerate(dash.items):
                obj_id = item.get("objectId")
                layout = item.get("layout", {})
                # Only add item if the referenced object exists
                cursor = await db.execute("SELECT id FROM saved_objects WHERE id = ?", (obj_id,))
                if await cursor.fetchone():
                    await db.execute(
                        "INSERT OR IGNORE INTO dashboard_items "
                        "(dashboard_id, object_id, layout_x, layout_y, layout_w, layout_h, sort_order) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            dash.id,
                            obj_id,
                            layout.get("x", 0),
                            layout.get("y", 0),
                            layout.get("w", 4),
                            layout.get("h", 4),
                            i,
                        ),
                    )
            imported += 1

        await db.commit()
        return {"imported": imported, "skipped": len(req.dashboards) - imported}
    finally:
        await db.close()
