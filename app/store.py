"""SQLite application store — persists dashboards, saved objects, and conversations.

ClickHouse handles analytics data; SQLite handles app state.
Database file: ~/.clickspot/app.db
"""

import logging
from pathlib import Path

import aiosqlite

log = logging.getLogger("app.store")

DB_PATH = Path.home() / ".clickspot" / "app.db"

SCHEMA_SQL = """
-- Saved objects (chat results saved to library)
CREATE TABLE IF NOT EXISTS saved_objects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    sql TEXT NOT NULL,
    viz TEXT NOT NULL,
    context_kpis TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Dashboards
CREATE TABLE IF NOT EXISTS dashboards (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filters TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Dashboard items (links dashboard to saved objects with layout)
CREATE TABLE IF NOT EXISTS dashboard_items (
    dashboard_id TEXT NOT NULL REFERENCES dashboards(id) ON DELETE CASCADE,
    object_id TEXT NOT NULL REFERENCES saved_objects(id) ON DELETE CASCADE,
    layout_x INTEGER NOT NULL DEFAULT 0,
    layout_y INTEGER NOT NULL DEFAULT 0,
    layout_w INTEGER NOT NULL DEFAULT 4,
    layout_h INTEGER NOT NULL DEFAULT 4,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (dashboard_id, object_id)
);

-- Chat conversations
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    space_id TEXT,                -- NULL = global chat, non-NULL = data space chat
    title TEXT NOT NULL DEFAULT 'New Conversation',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_conversations_space ON conversations(space_id);

-- Chat messages
CREATE TABLE IF NOT EXISTS conversation_messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sql TEXT,
    viz TEXT,
    title TEXT,
    context_kpis TEXT,
    created_at TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_messages_conv
    ON conversation_messages(conversation_id, sort_order);

-- Space-bound dashboards
CREATE TABLE IF NOT EXISTS space_dashboards (
    id TEXT PRIMARY KEY,
    space_id TEXT NOT NULL,
    title TEXT NOT NULL,
    pinned_columns TEXT NOT NULL DEFAULT '[]',
    filters TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_space_dash_space ON space_dashboards(space_id);

-- Space dashboard items (inline SQL, not referencing saved_objects)
CREATE TABLE IF NOT EXISTS space_dashboard_items (
    id TEXT PRIMARY KEY,
    dashboard_id TEXT NOT NULL REFERENCES space_dashboards(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    sql TEXT NOT NULL,
    viz TEXT NOT NULL,
    context_kpis TEXT NOT NULL DEFAULT '[]',
    layout_x INTEGER NOT NULL DEFAULT 0,
    layout_y INTEGER NOT NULL DEFAULT 0,
    layout_w INTEGER NOT NULL DEFAULT 4,
    layout_h INTEGER NOT NULL DEFAULT 4,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_space_items_dash ON space_dashboard_items(dashboard_id);
"""


async def init_db():
    """Create tables if they don't exist. Called on app startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        # Migrate first: add space_id column if missing (existing databases)
        cursor = await db.execute("PRAGMA table_info(conversations)")
        cols = {row[1] for row in await cursor.fetchall()}
        if cols and "space_id" not in cols:
            await db.execute("ALTER TABLE conversations ADD COLUMN space_id TEXT")
            await db.commit()
            log.info("Migrated conversations table: added space_id column")

        # Now create all tables + indexes (safe — space_id exists or table is new)
        await db.executescript(SCHEMA_SQL)
        await db.commit()
    log.info(f"SQLite database initialized at {DB_PATH}")


async def get_db() -> aiosqlite.Connection:
    """Get a database connection with FK enforcement and dict-like rows."""
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    return db
