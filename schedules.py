from dagster import ScheduleDefinition
from jobs import bronze_job

hourly_schedule = ScheduleDefinition(
    job=bronze_job,
    cron_schedule="0 * * * *",
)
