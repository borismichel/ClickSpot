from dagster import ScheduleDefinition, DefaultScheduleStatus
from jobs import bronze_job

hourly_schedule = ScheduleDefinition(
    job=bronze_job,
    cron_schedule="0 * * * *",
    default_status=DefaultScheduleStatus.STOPPED,
)
