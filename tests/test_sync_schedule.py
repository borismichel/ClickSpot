"""A scheduled refresh IS a sync: the hourly schedule stamps the same
clickspot/* correlation tags on the bronze run it launches as the Sync now
button does, so the Settings tab shows it with the same stages, failure card
and run links — with no special-casing in the status endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

from dagster import DefaultScheduleStatus, build_schedule_context

from app.sync_naming import (
    SYNC_ID_TAG,
    SYNC_MARKER_TAG,
    SYNC_MARKER_VALUE,
    SYNC_SCHEDULE_NAME,
)
from schedules import hourly_schedule


def _tick(when: datetime):
    return build_schedule_context(scheduled_execution_time=when)


def test_scheduled_tick_is_stamped_as_a_sync():
    request = hourly_schedule(_tick(datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)))
    assert request.tags[SYNC_MARKER_TAG] == SYNC_MARKER_VALUE
    assert request.tags[SYNC_ID_TAG] == "sched-202608201400"


def test_sync_id_is_deterministic_per_tick():
    """Re-evaluating the same tick must not mint a second sync id."""
    when = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
    first = hourly_schedule(_tick(when))
    second = hourly_schedule(_tick(when))
    assert first.tags[SYNC_ID_TAG] == second.tags[SYNC_ID_TAG]


def test_distinct_ticks_get_distinct_sync_ids():
    a = hourly_schedule(_tick(datetime(2026, 8, 20, 14, 0, tzinfo=timezone.utc)))
    b = hourly_schedule(_tick(datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)))
    assert a.tags[SYNC_ID_TAG] != b.tags[SYNC_ID_TAG]


def test_schedule_keeps_its_historical_name_and_ships_stopped():
    """The Dagster name predates the toggle ("<job>_schedule"); keeping it means
    a schedule an operator already started stays started across an upgrade.
    Hourly cadence and the stopped default are part of the same contract."""
    assert hourly_schedule.name == SYNC_SCHEDULE_NAME == "bronze_job_schedule"
    assert hourly_schedule.cron_schedule == "0 * * * *"
    assert hourly_schedule.default_status == DefaultScheduleStatus.STOPPED
