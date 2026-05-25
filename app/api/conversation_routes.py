"""REST endpoints for chat conversations (replaces localStorage persistence)."""

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.store import get_db

log = logging.getLogger("app.api.conversations")

router = APIRouter(prefix="/api/v1/conversations", tags=["conversations"])


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class CreateConversationRequest(BaseModel):
    title: str = "New Conversation"


class UpdateConversationRequest(BaseModel):
    title: str


class AddMessageRequest(BaseModel):
    # Client-stable id. The sidebar re-saves a conversation by diffing the
    # messages it holds against the ones already stored (by id), so the id the
    # client assigned must survive the round-trip — otherwise every re-save
    # looks "new" and re-inserts the whole conversation (CLI-84). Optional so
    # older callers still work; we mint one when it's absent.
    id: str | None = None
    role: str  # "user" or "assistant"
    content: str
    sql: str | None = None
    viz: str | None = None
    title: str | None = None
    context_kpis: list[dict] | None = None


class BulkImportConversation(BaseModel):
    id: str
    title: str
    messages: list[dict]
    created_at: str | None = None
    updated_at: str | None = None


class BulkImportRequest(BaseModel):
    conversations: list[BulkImportConversation]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _msg_to_dict(row) -> dict:
    result = {
        "id": row["id"],
        "role": row["role"],
        "content": row["content"],
    }
    if row["sql"]:
        result["sql"] = row["sql"]
    if row["viz"]:
        result["viz"] = row["viz"]
    if row["title"]:
        result["title"] = row["title"]
    if row["context_kpis"]:
        result["context_kpis"] = json.loads(row["context_kpis"])
    return result


async def _get_conversation_with_messages(db, conv_id: str) -> dict | None:
    cursor = await db.execute("SELECT * FROM conversations WHERE id = ?", (conv_id,))
    conv = await cursor.fetchone()
    if not conv:
        return None

    cursor = await db.execute(
        "SELECT * FROM conversation_messages WHERE conversation_id = ? ORDER BY sort_order",
        (conv_id,),
    )
    messages = await cursor.fetchall()

    return {
        "id": conv["id"],
        "title": conv["title"],
        "messages": [_msg_to_dict(m) for m in messages],
        "createdAt": conv["created_at"],
        "updatedAt": conv["updated_at"],
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("")
async def list_conversations(q: str | None = Query(default=None)):
    """List global (non-space) conversations, newest first.

    When ``q`` is provided, return only conversations whose title OR any
    message body matches the term (case-insensitive substring). This powers
    the sidebar search box (title + content match).
    """
    db = await get_db()
    try:
        term = (q or "").strip()
        if term:
            # Escape LIKE wildcards so user input is matched literally.
            escaped = (
                term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            like = f"%{escaped}%"
            cursor = await db.execute(
                "SELECT c.id, c.title, c.created_at, c.updated_at "
                "FROM conversations c "
                "WHERE c.space_id IS NULL AND ("
                "  c.title LIKE ? ESCAPE '\\' "
                "  OR EXISTS ("
                "    SELECT 1 FROM conversation_messages m "
                "    WHERE m.conversation_id = c.id "
                "    AND m.content LIKE ? ESCAPE '\\'"
                "  )"
                ") "
                "ORDER BY c.updated_at DESC",
                (like, like),
            )
        else:
            cursor = await db.execute(
                "SELECT id, title, created_at, updated_at FROM conversations "
                "WHERE space_id IS NULL ORDER BY updated_at DESC"
            )
        rows = await cursor.fetchall()
        return [
            {
                "id": r["id"],
                "title": r["title"],
                "createdAt": r["created_at"],
                "updatedAt": r["updated_at"],
            }
            for r in rows
        ]
    finally:
        await db.close()


@router.get("/{conv_id}")
async def get_conversation(conv_id: str):
    db = await get_db()
    try:
        data = await _get_conversation_with_messages(db, conv_id)
        if not data:
            raise HTTPException(404, "Conversation not found")
        return data
    finally:
        await db.close()


@router.post("", status_code=201)
async def create_conversation(req: CreateConversationRequest):
    db = await get_db()
    try:
        now = _now()
        conv_id = f"conv-{uuid4().hex[:12]}"
        await db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (conv_id, req.title, now, now),
        )
        await db.commit()
        return await _get_conversation_with_messages(db, conv_id)
    finally:
        await db.close()


@router.put("/{conv_id}")
async def update_conversation(conv_id: str, req: UpdateConversationRequest):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,))
        if not await cursor.fetchone():
            raise HTTPException(404, "Conversation not found")

        await db.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (req.title, _now(), conv_id),
        )
        await db.commit()
        return await _get_conversation_with_messages(db, conv_id)
    finally:
        await db.close()


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str):
    db = await get_db()
    try:
        cursor = await db.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(404, "Conversation not found")
        return {"deleted": conv_id}
    finally:
        await db.close()


@router.post("/{conv_id}/messages", status_code=201)
async def add_message(conv_id: str, req: AddMessageRequest):
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM conversations WHERE id = ?", (conv_id,))
        if not await cursor.fetchone():
            raise HTTPException(404, "Conversation not found")

        msg_id = req.id or f"msg-{uuid4().hex[:12]}"

        # Idempotent on the message id: a re-save of an already-stored message
        # must be a no-op, not a duplicate row. We check first (rather than
        # INSERT OR IGNORE) so a no-op skips the sort_order bump and just
        # returns the existing row — the client's diff can then settle. (CLI-84)
        cursor = await db.execute(
            "SELECT * FROM conversation_messages WHERE id = ?", (msg_id,)
        )
        existing = await cursor.fetchone()
        if existing is not None:
            return _msg_to_dict(existing)

        # Get next sort_order
        cursor = await db.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order "
            "FROM conversation_messages WHERE conversation_id = ?",
            (conv_id,),
        )
        row = await cursor.fetchone()
        sort_order = row["next_order"]

        now = _now()
        await db.execute(
            "INSERT INTO conversation_messages "
            "(id, conversation_id, role, content, sql, viz, title, context_kpis, created_at, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                msg_id,
                conv_id,
                req.role,
                req.content,
                req.sql,
                req.viz,
                req.title,
                json.dumps(req.context_kpis) if req.context_kpis else None,
                now,
                sort_order,
            ),
        )
        # Update conversation title from first user message if still default
        cursor = await db.execute(
            "SELECT title FROM conversations WHERE id = ?", (conv_id,)
        )
        conv = await cursor.fetchone()
        if conv["title"] == "New Conversation" and req.role == "user":
            new_title = req.content[:60]
            await db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (new_title, now, conv_id),
            )
        else:
            await db.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conv_id)
            )

        await db.commit()
        return _msg_to_dict(
            await (await db.execute(
                "SELECT * FROM conversation_messages WHERE id = ?", (msg_id,)
            )).fetchone()
        )
    finally:
        await db.close()


@router.post("/import", status_code=200)
async def bulk_import(req: BulkImportRequest):
    """Import conversations from localStorage migration."""
    db = await get_db()
    try:
        imported = 0
        for conv in req.conversations:
            # Skip if conversation ID already exists
            cursor = await db.execute("SELECT id FROM conversations WHERE id = ?", (conv.id,))
            if await cursor.fetchone():
                continue

            now = _now()
            await db.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conv.id, conv.title, conv.created_at or now, conv.updated_at or now),
            )

            for i, msg in enumerate(conv.messages):
                msg_id = msg.get("id", f"msg-{uuid4().hex[:12]}")
                context_kpis = msg.get("context") or msg.get("context_kpis")
                await db.execute(
                    "INSERT INTO conversation_messages "
                    "(id, conversation_id, role, content, sql, viz, title, context_kpis, created_at, sort_order) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        msg_id,
                        conv.id,
                        msg.get("role", "user"),
                        msg.get("content", ""),
                        msg.get("sql"),
                        msg.get("viz"),
                        msg.get("title"),
                        json.dumps(context_kpis) if context_kpis else None,
                        msg.get("created_at", now),
                        i,
                    ),
                )
            imported += 1

        await db.commit()
        return {"imported": imported, "skipped": len(req.conversations) - imported}
    finally:
        await db.close()
