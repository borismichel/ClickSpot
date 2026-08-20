"""Bring this process's served view of the warehouse schema in line with the
current customer configuration.

The table catalog is derived from the composed silver column lists at import
time, and the chat schema prompt is memoized on top of it — so a configuration
change is invisible to chat, the SQL validator, and /schema until something
re-derives both. That something is here.

Called when an "Apply changes" rebuild lands (app/api/sync_routes.py), i.e.
once the warehouse actually holds the new columns — refreshing on save would
leave chat describing columns with no data behind them, and a failed rebuild
would strand a half-applied schema. Failures are logged rather than raised:
the caller is reporting on a rebuild that already succeeded.
"""

from __future__ import annotations

import logging

log = logging.getLogger("app.schema_refresh")


def refresh_served_schema() -> None:
    try:
        from app.config import rebuild_tables
        rebuild_tables()
    except Exception as e:
        log.warning("Failed to rebuild table catalog: %s", e)
        return
    try:
        from app.llm.providers import refresh_schema_prompt
        refresh_schema_prompt()
    except Exception as e:
        log.warning("Failed to refresh schema prompt: %s", e)
