from dagster import ScheduleDefinition, DefaultScheduleStatus
from jobs import full_pipeline_job

hourly_schedule = ScheduleDefinition(
    job=full_pipeline_job,
    cron_schedule="0 * * * *",
    default_status=DefaultScheduleStatus.STOPPED,
)
