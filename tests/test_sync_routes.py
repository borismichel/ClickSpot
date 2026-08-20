"""Sync endpoints: start guardrails, stage progress assembly, failure naming.

Dagster is mocked at the app.dagster_client function boundary — these tests
pin the contract the Sync tab depends on, not GraphQL wire formats."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import dagster_client
from app.main import app
from app.sync_naming import (
    SYNC_ID_TAG,
    SYNC_MARKER_TAG,
    SYNC_MARKER_VALUE,
    SYNC_SCHEDULE_NAME,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def stopped_schedule(monkeypatch):
    """Default the schedule lookup to a stopped schedule so status tests never
    reach out to a real Dagster; individual tests re-patch for their scenario."""
    monkeypatch.setattr(
        dagster_client,
        "schedule_state",
        lambda name: {"id": "sched-1", "status": "STOPPED", "next_tick_timestamp": None},
    )


def _run(job, status, sync_id="abc123", run_id=None, tagged=True):
    tags = {SYNC_MARKER_TAG: SYNC_MARKER_VALUE, SYNC_ID_TAG: sync_id} if tagged else {}
    return {
        "runId": run_id or f"{job}-{sync_id}",
        "status": status,
        "jobName": job,
        "startTime": 1.0,
        "endTime": None,
        "tags": tags,
    }


@pytest.fixture
def hubspot_token(monkeypatch):
    monkeypatch.setenv("HUBSPOT_TOKEN", "pat-na1-test")


@pytest.fixture
def no_hubspot_token(monkeypatch):
    monkeypatch.delenv("HUBSPOT_TOKEN", raising=False)


# ---------------------------------------------------------------------------
# Starting a sync
# ---------------------------------------------------------------------------


def test_start_without_hubspot_credentials_is_refused_with_a_reason(no_hubspot_token):
    res = client.post("/api/v1/sync")
    assert res.status_code == 409
    assert "HUBSPOT_TOKEN" in res.json()["detail"]


def test_start_launches_bronze_with_correlation_tags(hubspot_token):
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[]),
        patch.object(dagster_client, "launch_job", return_value="run-1") as launch,
    ):
        res = client.post("/api/v1/sync")
    assert res.status_code == 200
    data = res.json()
    assert data["run_id"] == "run-1"
    assert data["sync_id"]

    job_name = launch.call_args.args[0]
    tags = launch.call_args.kwargs["tags"]
    assert job_name == "bronze_job"
    assert tags[SYNC_MARKER_TAG] == SYNC_MARKER_VALUE
    assert tags[SYNC_ID_TAG] == data["sync_id"]


def test_start_while_a_sync_is_running_does_not_launch_a_second(hubspot_token):
    with (
        patch.object(dagster_client, "in_progress_runs",
                     return_value=[_run("silver_job", "STARTED")]),
        patch.object(dagster_client, "launch_job") as launch,
    ):
        res = client.post("/api/v1/sync")
    assert res.status_code == 409
    assert "already running" in res.json()["detail"]
    launch.assert_not_called()


def test_start_is_blocked_by_a_scheduled_run_too(hubspot_token):
    """The guard is about the warehouse being mid-refresh, however the run was
    started — an hourly-schedule bronze run counts."""
    with (
        patch.object(dagster_client, "in_progress_runs",
                     return_value=[_run("bronze_job", "STARTED", tagged=False)]),
        patch.object(dagster_client, "launch_job") as launch,
    ):
        res = client.post("/api/v1/sync")
    assert res.status_code == 409
    launch.assert_not_called()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_status_with_no_syncs_yet(no_hubspot_token):
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[]),
        patch.object(dagster_client, "runs_by_tag", return_value=[]),
    ):
        res = client.get("/api/v1/sync/status")
    assert res.status_code == 200
    data = res.json()
    assert data["sync"] is None
    assert data["sync_running"] is False
    assert data["hubspot_configured"] is False
    assert data["not_configured_reason"]
    assert data["dagster_ui_url"] == "http://localhost:8194"
    assert data["schedule"] == {"enabled": False, "next_run_timestamp": None}


def test_status_degrades_when_the_orchestrator_is_unreachable(hubspot_token):
    """Dagster being down must not blank the tab — freshness and the config
    state don't depend on it."""
    from fastapi import HTTPException

    with patch.object(
        dagster_client, "in_progress_runs",
        side_effect=HTTPException(503, "Dagster GraphQL unreachable at http://x"),
    ):
        res = client.get("/api/v1/sync/status")
    assert res.status_code == 200
    data = res.json()
    assert "unreachable" in data["dagster_error"]
    assert data["sync"] is None
    assert data["schedule"] is None
    assert data["hubspot_configured"] is True


def test_status_mid_sync_reports_stage_progress_in_order(hubspot_token):
    runs = [
        _run("silver_job", "STARTED"),
        _run("bronze_job", "SUCCESS"),
    ]
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[runs[0]]),
        patch.object(dagster_client, "runs_by_tag", return_value=runs),
    ):
        res = client.get("/api/v1/sync/status")
    sync = res.json()["sync"]
    assert sync["state"] == "running"
    assert [s["stage"] for s in sync["stages"]] == ["bronze", "silver", "gold", "anon"]
    assert [s["status"] for s in sync["stages"]] == ["success", "running", "pending", "pending"]
    assert sync["stages"][1]["label"] == "Preparing tables"
    assert sync["error"] is None


def test_status_completed_sync(hubspot_token):
    runs = [
        _run("anon_job", "SUCCESS"),
        _run("gold_job", "SUCCESS"),
        _run("silver_job", "SUCCESS"),
        _run("bronze_job", "SUCCESS"),
    ]
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[]),
        patch.object(dagster_client, "runs_by_tag", return_value=runs),
    ):
        res = client.get("/api/v1/sync/status")
    sync = res.json()["sync"]
    assert sync["state"] == "succeeded"
    assert all(s["status"] == "success" for s in sync["stages"])


def test_failed_stage_names_the_hubspot_object_and_links_the_run(hubspot_token, monkeypatch):
    monkeypatch.setenv("DAGSTER_UI_URL", "https://dagster.example.com")
    runs = [
        _run("silver_job", "FAILURE", run_id="run-silver"),
        _run("bronze_job", "SUCCESS"),
    ]
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[]),
        patch.object(dagster_client, "runs_by_tag", return_value=runs),
        patch.object(dagster_client, "run_step_stats", return_value=[
            {"stepKey": "dim_owners", "status": "SUCCESS"},
            {"stepKey": "dim_contacts", "status": "FAILURE"},
        ]),
    ):
        res = client.get("/api/v1/sync/status")
    sync = res.json()["sync"]
    assert sync["state"] == "failed"
    error = sync["error"]
    assert error["message"] == "Sync failed while preparing Contacts"
    assert error["run_url"] == "https://dagster.example.com/runs/run-silver"
    # The raw step key rides along for whoever follows the details link…
    assert error["failed_step"] == "dim_contacts"


def test_failure_on_internal_table_uses_generic_phrase(hubspot_token):
    runs = [
        _run("silver_job", "FAILURE", run_id="run-silver"),
        _run("bronze_job", "SUCCESS"),
    ]
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[]),
        patch.object(dagster_client, "runs_by_tag", return_value=runs),
        patch.object(dagster_client, "run_step_stats", return_value=[
            {"stepKey": "bridge_contact_company", "status": "FAILURE"},
        ]),
    ):
        res = client.get("/api/v1/sync/status")
    error = res.json()["sync"]["error"]
    assert error["message"] == "Sync failed while preparing internal tables"
    assert "bridge_contact_company" not in error["message"]


def test_status_only_reports_the_latest_sync(hubspot_token):
    """Runs of an older sync (different correlation id) are not mixed in."""
    runs = [
        _run("bronze_job", "STARTED", sync_id="new111"),
        _run("anon_job", "SUCCESS", sync_id="old000"),
        _run("gold_job", "SUCCESS", sync_id="old000"),
        _run("silver_job", "SUCCESS", sync_id="old000"),
        _run("bronze_job", "SUCCESS", sync_id="old000"),
    ]
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[runs[0]]),
        patch.object(dagster_client, "runs_by_tag", return_value=runs),
    ):
        res = client.get("/api/v1/sync/status")
    sync = res.json()["sync"]
    assert sync["sync_id"] == "new111"
    assert [s["status"] for s in sync["stages"]] == ["running", "pending", "pending", "pending"]


# ---------------------------------------------------------------------------
# Automatic updates (the hourly schedule, as an operator-facing switch)
# ---------------------------------------------------------------------------


def test_status_reports_a_running_schedule_with_its_next_run(hubspot_token, monkeypatch):
    monkeypatch.setattr(
        dagster_client,
        "schedule_state",
        lambda name: {"id": "sched-1", "status": "RUNNING", "next_tick_timestamp": 1766240400.0},
    )
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[]),
        patch.object(dagster_client, "runs_by_tag", return_value=[]),
    ):
        res = client.get("/api/v1/sync/status")
    assert res.json()["schedule"] == {"enabled": True, "next_run_timestamp": 1766240400.0}


def test_status_survives_a_failed_schedule_lookup(hubspot_token, monkeypatch):
    """A broken schedule lookup greys out the switch (schedule: null) but must
    not blank the sync progress, which comes from independent queries."""
    from fastapi import HTTPException

    def boom(name):
        raise HTTPException(502, "Dagster schedule lookup failed: PythonError")

    monkeypatch.setattr(dagster_client, "schedule_state", boom)
    runs = [_run("bronze_job", "SUCCESS")]
    with (
        patch.object(dagster_client, "in_progress_runs", return_value=[]),
        patch.object(dagster_client, "runs_by_tag", return_value=runs),
    ):
        res = client.get("/api/v1/sync/status")
    data = res.json()
    assert data["schedule"] is None
    assert data["dagster_error"] is None
    assert data["sync"] is not None


def test_turning_on_without_hubspot_credentials_is_refused(no_hubspot_token):
    with patch.object(dagster_client, "start_schedule") as start:
        res = client.put("/api/v1/sync/schedule", json={"enabled": True})
    assert res.status_code == 409
    assert "HUBSPOT_TOKEN" in res.json()["detail"]
    start.assert_not_called()


def test_turning_on_starts_the_schedule(hubspot_token):
    with patch.object(dagster_client, "start_schedule", return_value="RUNNING") as start:
        res = client.put("/api/v1/sync/schedule", json={"enabled": True})
    assert res.status_code == 200
    assert res.json() == {"enabled": True}
    start.assert_called_once_with(SYNC_SCHEDULE_NAME)


def test_turning_off_stops_the_schedule_and_needs_no_credentials(no_hubspot_token):
    """Off must always be reachable — an operator whose token was removed can
    still stop the automation that depends on it."""
    with patch.object(dagster_client, "stop_schedule", return_value="STOPPED") as stop:
        res = client.put("/api/v1/sync/schedule", json={"enabled": False})
    assert res.status_code == 200
    assert res.json() == {"enabled": False}
    stop.assert_called_once_with(SYNC_SCHEDULE_NAME)


def test_turning_off_leaves_a_sync_in_progress_alone(hubspot_token):
    """Stopping the schedule stops future ticks only — the toggle never
    consults or cancels in-flight runs."""
    with (
        patch.object(dagster_client, "stop_schedule", return_value="STOPPED"),
        patch.object(dagster_client, "in_progress_runs") as in_progress,
        patch.object(dagster_client, "launch_job") as launch,
    ):
        res = client.put("/api/v1/sync/schedule", json={"enabled": False})
    assert res.status_code == 200
    in_progress.assert_not_called()
    launch.assert_not_called()
