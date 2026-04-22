from dagster import run_status_sensor, DagsterRunStatus, RunRequest
from jobs import bronze_job, silver_job, gold_job, anon_job


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[bronze_job],
    request_job=silver_job,
    name="trigger_silver_after_bronze",
)
def trigger_silver_after_bronze(context):
    """Automatically run silver_job after bronze_job succeeds."""
    return RunRequest()


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[silver_job],
    request_job=gold_job,
    name="trigger_gold_after_silver",
)
def trigger_gold_after_silver(context):
    """Automatically run gold_job after silver_job succeeds."""
    return RunRequest()


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[gold_job],
    request_job=anon_job,
    name="trigger_anon_after_gold",
)
def trigger_anon_after_gold(context):
    """Rebuild silver_anon/gold_anon after gold_job succeeds."""
    return RunRequest()
