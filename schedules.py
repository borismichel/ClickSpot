"""The hourly refresh, stamped as a sync.

A scheduled refresh is an ordinary sync: stamping the clickspot/* correlation
tags on the bronze run it launches means the chaining sensors propagate them
and the Settings → Data sync tab shows scheduled refreshes exactly like
button-started ones (same stages, failure card, run links). The sync id is
derived from the tick time so re-evaluating a tick cannot mint a second id.
"""

import uuid

from dagster import DefaultScheduleStatus, RunRequest, schedule

from app.sync_naming import (
    SYNC_ID_TAG,
    SYNC_MARKER_TAG,
    SYNC_MARKER_VALUE,
    SYNC_SCHEDULE_NAME,
)
from jobs import bronze_job


@schedule(
    job=bronze_job,
    cron_schedule="0 * * * *",
    name=SYNC_SCHEDULE_NAME,
    default_status=DefaultScheduleStatus.STOPPED,
)
def hourly_schedule(context):
    tick = context.scheduled_execution_time
    sync_id = tick.strftime("sched-%Y%m%d%H%M") if tick else f"sched-{uuid.uuid4().hex[:12]}"
    return RunRequest(tags={SYNC_MARKER_TAG: SYNC_MARKER_VALUE, SYNC_ID_TAG: sync_id})
