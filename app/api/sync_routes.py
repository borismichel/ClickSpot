"""REST endpoints behind the Settings → Data sync tab and the
pending-changes banner.

  POST /api/v1/sync          — start a full refresh (bronze → … → anon)
  POST /api/v1/sync/apply    — apply saved settings: reload definitions, then
                               rebuild from data already stored (silver → … →
                               anon, no HubSpot fetch)
  GET  /api/v1/sync/status   — the latest operation's stages, in operator
                               language
  PUT  /api/v1/sync/schedule — turn the automatic hourly refresh on or off

A "sync" is still four separate Dagster runs chained by sensors — nothing is
collapsed. What ties them together is the correlation tag stamped on the bronze
run here and propagated by each chaining sensor (sensors.py), so all four runs
come back from one tag-filtered query, in order, with their statuses. An
"apply" is the same mechanism starting one stage later, distinguished by the
kind tag.

"Last refreshed" deliberately does NOT live here: the existing /api/v1/metadata
endpoint already serves per-table freshness timestamps and the frontend reads
those, rather than this module inventing a parallel notion from run times.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import dagster_client as dagster
from app import schema_refresh
from app.customer import extraction
from app.warehouse_init import ensure_schema_best_effort
from app.sync_naming import (
    APPLY_STAGES,
    STAGES,
    SYNC_ID_TAG,
    SYNC_JOBS,
    SYNC_KIND_TAG,
    SYNC_MARKER_TAG,
    SYNC_MARKER_VALUE,
    SYNC_SCHEDULE_NAME,
    failure_message,
)

log = logging.getLogger("app.api.sync")

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


NOT_CONFIGURED_MESSAGE = (
    "HubSpot credentials are not configured — set HUBSPOT_TOKEN in .env to sync "
    "from a live portal. Without it there is nothing to fetch; use the offline "
    "seed loader (make seed) to load the bundled demo warehouse instead."
)


def _hubspot_configured() -> bool:
    return bool(os.environ.get("HUBSPOT_TOKEN", "").strip())




@router.post("")
def start_sync() -> dict[str, Any]:
    """Launch bronze with a fresh correlation tag; sensors take it from there."""
    if not _hubspot_configured():
        raise HTTPException(409, NOT_CONFIGURED_MESSAGE)

    running = dagster.in_progress_runs(SYNC_JOBS)
    if running:
        raise HTTPException(
            409,
            "A sync is already running — wait for it to finish before starting another.",
        )

    # Fresh-compose path: the stack starts with only the empty `bronze`
    # database from CLICKHOUSE_DB, and bronze assets insert without creating
    # tables — make sure the schema exists before bronze launches.
    ensure_schema_best_effort("before sync launch")

    sync_id = uuid.uuid4().hex[:12]
    run_id = dagster.launch_job(
        "bronze_job",
        tags={SYNC_MARKER_TAG: SYNC_MARKER_VALUE, SYNC_ID_TAG: sync_id,
              SYNC_KIND_TAG: "sync"},
    )
    log.info("Started sync %s (bronze run %s)", sync_id, run_id)
    return {"sync_id": sync_id, "run_id": run_id}


# ---------------------------------------------------------------------------
# Apply changes — reload definitions + rebuild from stored data
# ---------------------------------------------------------------------------

# The apply this process started, or None: {"sync_id", "token", "refreshed"}.
# `token` is the pending-apply token captured at launch, so completion clears
# only the pending state this apply was started for; `refreshed` makes the
# served-schema refresh idempotent across status polls and the watcher thread.
# After a backend restart this is gone — that's fine, because a restart
# recomposes the served schema from the saved config anyway, and an operator
# facing a leftover banner can re-apply harmlessly.
_active_apply: dict[str, Any] | None = None

APPLY_WATCH_INTERVAL_S = 5.0
APPLY_WATCH_TIMEOUT_S = 30 * 60.0


@router.post("/apply")
def start_apply() -> dict[str, Any]:
    """Make the saved settings live: reload the Dagster definitions, then
    rebuild silver onward from data already in the warehouse.

    Nothing is fetched from HubSpot — no credentials needed, and markedly
    faster than a full sync. Harmless with no pending changes.
    """
    global _active_apply

    running = dagster.in_progress_runs(SYNC_JOBS)
    if running:
        raise HTTPException(
            409,
            "A refresh is already running — wait for it to finish before applying changes.",
        )

    ensure_schema_best_effort("before apply launch")

    token = extraction.pending_apply_token()
    reloaded = dagster.reload_all_locations()

    sync_id = uuid.uuid4().hex[:12]
    run_id = dagster.launch_job(
        "silver_job",
        tags={SYNC_MARKER_TAG: SYNC_MARKER_VALUE, SYNC_ID_TAG: sync_id,
              SYNC_KIND_TAG: "apply"},
    )
    _active_apply = {"sync_id": sync_id, "token": token, "refreshed": False}
    _start_apply_watcher(sync_id)
    log.info("Started apply %s (silver run %s)", sync_id, run_id)
    return {"sync_id": sync_id, "run_id": run_id, "reloaded": reloaded}


def _maybe_finalize_apply(sync: dict[str, Any] | None) -> None:
    """Finish the backend-side half of an apply once the rebuild has landed.

    As soon as the silver stage succeeds the warehouse holds the new columns,
    so the served schema (table catalog + memoized chat prompt) is refreshed to
    match. When the whole chain succeeds, the pending flag it was started for
    is cleared. On failure the schema is left as it was — the warehouse swap is
    atomic per table, so the previously working schema stays truthful.
    """
    global _active_apply
    active = _active_apply
    if not sync or sync.get("kind") != "apply":
        return
    if not active or active["sync_id"] != sync["sync_id"]:
        return

    silver_done = any(
        s["stage"] == "silver" and s["status"] == "success" for s in sync["stages"]
    )
    if silver_done and not active["refreshed"]:
        schema_refresh.refresh_served_schema()
        active["refreshed"] = True
        log.info("Apply %s: silver rebuild landed, served schema refreshed", sync["sync_id"])

    if sync["state"] == "succeeded":
        if active["token"]:
            extraction.clear_pending_apply(active["token"])
        _active_apply = None
    elif sync["state"] == "failed":
        _active_apply = None


def _watch_apply(sync_id: str) -> None:
    """Poll until the apply finishes so it completes even if nobody is watching
    the UI. Status polls run the same finalize, so this thread can bail out on
    repeated Dagster errors without stranding anything."""
    deadline = time.monotonic() + APPLY_WATCH_TIMEOUT_S
    errors = 0
    while time.monotonic() < deadline:
        time.sleep(APPLY_WATCH_INTERVAL_S)
        try:
            sync = _latest_sync()
        except HTTPException as e:
            errors += 1
            if errors >= 5:
                log.warning("Apply watcher %s giving up on Dagster: %s", sync_id, e.detail)
                return
            continue
        errors = 0
        if not sync or sync["sync_id"] != sync_id:
            return
        _maybe_finalize_apply(sync)
        if sync["state"] != "running":
            return
    log.warning("Apply watcher %s timed out after %ss", sync_id, APPLY_WATCH_TIMEOUT_S)


def _start_apply_watcher(sync_id: str) -> None:
    threading.Thread(
        target=_watch_apply,
        args=(sync_id,),
        name=f"apply-watcher-{sync_id}",
        daemon=True,
    ).start()


def _stage_status(dagster_status: str) -> str:
    if dagster_status == "SUCCESS":
        return "success"
    if dagster_status in ("FAILURE", "CANCELED"):
        return "failure"
    return "running"


def _failed_step_key(run_id: str) -> str | None:
    """The first failed step of a run, for naming what broke."""
    try:
        for step in dagster.run_step_stats(run_id):
            if step.get("status") == "FAILURE":
                return step.get("stepKey")
    except HTTPException as e:
        log.warning("Step stats unavailable for run %s: %s", run_id, e.detail)
    return None


def _latest_sync() -> dict[str, Any] | None:
    """Assemble the most recent operation (sync or apply) from its
    tag-correlated runs."""
    runs = dagster.runs_by_tag(SYNC_MARKER_TAG, SYNC_MARKER_VALUE)
    if not runs:
        return None

    # Runs come back newest first; the first run's sync id names the latest sync.
    sync_id = runs[0]["tags"].get(SYNC_ID_TAG)
    if not sync_id:
        return None
    sync_runs = [r for r in runs if r["tags"].get(SYNC_ID_TAG) == sync_id]

    # Runs without a kind tag predate the apply surface — they are all syncs.
    kind = "apply" if runs[0]["tags"].get(SYNC_KIND_TAG) == "apply" else "sync"
    stage_list = APPLY_STAGES if kind == "apply" else STAGES

    # One run per job — keep the newest (a retried stage would appear twice).
    run_by_job: dict[str, dict[str, Any]] = {}
    for run in reversed(sync_runs):
        run_by_job[run["jobName"]] = run

    stages: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None
    state = "running"
    for stage, job, label in stage_list:
        run = run_by_job.get(job)
        if run is None:
            stages.append({"stage": stage, "label": label, "status": "pending",
                           "run_id": None, "run_url": None})
            continue
        status = _stage_status(run["status"])
        stages.append({
            "stage": stage,
            "label": label,
            "status": status,
            "run_id": run["runId"],
            "run_url": dagster.run_url(run["runId"]),
        })
        if status == "failure" and error is None:
            step_key = _failed_step_key(run["runId"])
            error = {
                "stage": stage,
                "stage_label": label,
                "message": failure_message(stage, step_key, kind),
                "failed_step": step_key,
                "run_id": run["runId"],
                "run_url": dagster.run_url(run["runId"]),
            }

    if error is not None:
        state = "failed"
    elif run_by_job.get("anon_job", {}).get("status") == "SUCCESS":
        state = "succeeded"

    return {"sync_id": sync_id, "kind": kind, "state": state, "stages": stages,
            "error": error}


def _schedule_info() -> dict[str, Any]:
    """The switch's source of truth: what the orchestrator says the schedule
    is doing right now, not what ClickSpot last asked for."""
    state = dagster.schedule_state(SYNC_SCHEDULE_NAME)
    enabled = state["status"] == "RUNNING"
    return {
        "enabled": enabled,
        # futureTicks is computed from the cron whether or not the schedule is
        # running, so only surface it when a tick will actually fire.
        "next_run_timestamp": state["next_tick_timestamp"] if enabled else None,
    }


@router.get("/status")
def sync_status() -> dict[str, Any]:
    # An unreachable orchestrator must not blank the whole tab — the freshness
    # line and the "why can't I sync" explanation don't depend on Dagster.
    dagster_error: str | None = None
    sync_running = False
    sync: dict[str, Any] | None = None
    try:
        sync_running = bool(dagster.in_progress_runs(SYNC_JOBS))
        sync = _latest_sync()
    except HTTPException as e:
        dagster_error = str(e.detail)

    # Status polls double as the fallback finalizer: if the watcher thread died
    # (or Dagster was briefly unreachable), the next poll lands the refresh.
    try:
        _maybe_finalize_apply(sync)
    except Exception as e:
        log.warning("Apply finalize failed during status poll: %s", e)

    # A schedule-only failure (e.g. the code location mid-reload) greys out the
    # switch without discarding the sync progress fetched above.
    schedule: dict[str, Any] | None = None
    if dagster_error is None:
        try:
            schedule = _schedule_info()
        except HTTPException as e:
            log.warning("Schedule state unavailable: %s", e.detail)

    return {
        "hubspot_configured": _hubspot_configured(),
        "not_configured_reason": None if _hubspot_configured() else NOT_CONFIGURED_MESSAGE,
        "dagster_ui_url": dagster.ui_url(),
        "dagster_error": dagster_error,
        "sync_running": sync_running,
        "pending_apply": extraction.pending_apply_token() is not None,
        "sync": sync,
        "schedule": schedule,
    }


class ScheduleToggle(BaseModel):
    enabled: bool


@router.put("/schedule")
def set_schedule(body: ScheduleToggle) -> dict[str, Any]:
    """Turn the automatic hourly refresh on or off.

    Off is never guarded: it must stay reachable even without credentials, and
    stopping the schedule only stops future ticks — a sync already in flight
    is not touched."""
    if body.enabled:
        if not _hubspot_configured():
            raise HTTPException(409, NOT_CONFIGURED_MESSAGE)
        status = dagster.start_schedule(SYNC_SCHEDULE_NAME)
    else:
        status = dagster.stop_schedule(SYNC_SCHEDULE_NAME)
    log.info("Automatic updates turned %s", "on" if body.enabled else "off")
    return {"enabled": status == "RUNNING"}
