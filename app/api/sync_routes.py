"""REST endpoints behind the Settings → Data sync tab.

  POST /api/v1/sync         — start a full refresh (bronze → … → anon)
  GET  /api/v1/sync/status  — the latest sync's stages, in operator language

A "sync" is still four separate Dagster runs chained by sensors — nothing is
collapsed. What ties them together is the correlation tag stamped on the bronze
run here and propagated by each chaining sensor (sensors.py), so all four runs
come back from one tag-filtered query, in order, with their statuses.

"Last refreshed" deliberately does NOT live here: the existing /api/v1/metadata
endpoint already serves per-table freshness timestamps and the frontend reads
those, rather than this module inventing a parallel notion from run times.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app import dagster_client as dagster
from app.sync_naming import (
    STAGES,
    SYNC_ID_TAG,
    SYNC_JOBS,
    SYNC_MARKER_TAG,
    SYNC_MARKER_VALUE,
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

    sync_id = uuid.uuid4().hex[:12]
    run_id = dagster.launch_job(
        "bronze_job",
        tags={SYNC_MARKER_TAG: SYNC_MARKER_VALUE, SYNC_ID_TAG: sync_id},
    )
    log.info("Started sync %s (bronze run %s)", sync_id, run_id)
    return {"sync_id": sync_id, "run_id": run_id}


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
    """Assemble the most recent sync from its tag-correlated runs."""
    runs = dagster.runs_by_tag(SYNC_MARKER_TAG, SYNC_MARKER_VALUE)
    if not runs:
        return None

    # Runs come back newest first; the first run's sync id names the latest sync.
    sync_id = runs[0]["tags"].get(SYNC_ID_TAG)
    if not sync_id:
        return None
    sync_runs = [r for r in runs if r["tags"].get(SYNC_ID_TAG) == sync_id]

    # One run per job — keep the newest (a retried stage would appear twice).
    run_by_job: dict[str, dict[str, Any]] = {}
    for run in reversed(sync_runs):
        run_by_job[run["jobName"]] = run

    stages: list[dict[str, Any]] = []
    error: dict[str, Any] | None = None
    state = "running"
    for stage, job, label in STAGES:
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
                "message": failure_message(stage, step_key),
                "failed_step": step_key,
                "run_id": run["runId"],
                "run_url": dagster.run_url(run["runId"]),
            }

    if error is not None:
        state = "failed"
    elif run_by_job.get("anon_job", {}).get("status") == "SUCCESS":
        state = "succeeded"

    return {"sync_id": sync_id, "state": state, "stages": stages, "error": error}


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

    return {
        "hubspot_configured": _hubspot_configured(),
        "not_configured_reason": None if _hubspot_configured() else NOT_CONFIGURED_MESSAGE,
        "dagster_ui_url": dagster.ui_url(),
        "dagster_error": dagster_error,
        "sync_running": sync_running,
        "sync": sync,
    }
