"""REST endpoints for saved objects (chat results saved to the library)."""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import get_db

log = logging.getLogger("app.api.objects")

router = APIRouter(prefix="/api/v1/objects", tags=["objects"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreateObjectRequest(BaseModel):
    title: str
    sql: str
    viz: str
    context_kpis: list[dict] = []


class SavedObjectResponse(BaseModel):
    id: str
    title: str
    sql: str
    viz: str
    context_kpis: list[dict]
    created_at: str
    updated_at: str


class BulkImportRequest(BaseModel):
    objects: list[CreateObjectRequest]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "sql": row["sql"],
        "viz": row["viz"],
        "context_kpis": json.loads(row["context_kpis"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.split()).strip()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_objects():
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM saved_objects ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        await db.close()


@router.get("/{object_id}")
async def get_object(object_id: str):
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM saved_objects WHERE id = ?", (object_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(404, "Object not found")
        return _row_to_dict(row)
    finally:
        await db.close()


@router.post("", status_code=201)
async def create_object(req: CreateObjectRequest):
    db = await get_db()
    try:
        # Deduplicate by normalized SQL
        normalized = _normalize_sql(req.sql)
        cursor = await db.execute("SELECT sql FROM saved_objects")
        existing = await cursor.fetchall()
        for row in existing:
            if _normalize_sql(row["sql"]) == normalized:
                raise HTTPException(409, "An object with identical SQL already exists")

        now = _now()
        obj_id = f"obj-{uuid4().hex[:12]}"
        await db.execute(
            "INSERT INTO saved_objects (id, title, sql, viz, context_kpis, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (obj_id, req.title, req.sql, req.viz, json.dumps(req.context_kpis), now, now),
        )
        await db.commit()

        cursor = await db.execute("SELECT * FROM saved_objects WHERE id = ?", (obj_id,))
        row = await cursor.fetchone()
        return _row_to_dict(row)
    finally:
        await db.close()


@router.delete("/{object_id}")
async def delete_object(object_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM saved_objects WHERE id = ?", (object_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, "Object not found")
        return {"deleted": object_id}
    finally:
        await db.close()


@router.post("/import", status_code=200)
async def bulk_import(req: BulkImportRequest):
    """Import objects from localStorage migration. Skips duplicates."""
    db = await get_db()
    try:
        imported = 0
        cursor = await db.execute("SELECT sql FROM saved_objects")
        existing = await cursor.fetchall()
        existing_sqls = {_normalize_sql(r["sql"]) for r in existing}

        for obj in req.objects:
            normalized = _normalize_sql(obj.sql)
            if normalized in existing_sqls:
                continue
            now = _now()
            obj_id = f"obj-{uuid4().hex[:12]}"
            await db.execute(
                "INSERT INTO saved_objects (id, title, sql, viz, context_kpis, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (obj_id, obj.title, obj.sql, obj.viz, json.dumps(obj.context_kpis), now, now),
            )
            existing_sqls.add(normalized)
            imported += 1

        await db.commit()
        return {"imported": imported, "skipped": len(req.objects) - imported}
    finally:
        await db.close()
