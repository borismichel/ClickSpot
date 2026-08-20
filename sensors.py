from dagster import run_status_sensor, DagsterRunStatus, RunRequest
from jobs import bronze_job, silver_job, gold_job, anon_job

# A "Sync now" from the ClickSpot UI stamps clickspot/* correlation tags on the
# bronze run (app/api/sync_routes.py). Each chaining sensor copies them onto
# the run it requests, so all four runs of one sync are retrievable with a
# single tag-filtered query — timestamps never have to be guessed at. Runs
# without the tags (hourly schedule, manual Dagster launches) chain unchanged.
_SYNC_TAG_PREFIX = "clickspot/"


def propagated_sync_tags(tags: dict[str, str]) -> dict[str, str]:
    """The clickspot/* correlation tags of an upstream run, if any."""
    return {k: v for k, v in tags.items() if k.startswith(_SYNC_TAG_PREFIX)}


def _chain(context) -> RunRequest:
    return RunRequest(tags=propagated_sync_tags(context.dagster_run.tags))


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[bronze_job],
    request_job=silver_job,
    name="trigger_silver_after_bronze",
)
def trigger_silver_after_bronze(context):
    """Automatically run silver_job after bronze_job succeeds."""
    return _chain(context)


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[silver_job],
    request_job=gold_job,
    name="trigger_gold_after_silver",
)
def trigger_gold_after_silver(context):
    """Automatically run gold_job after silver_job succeeds."""
    return _chain(context)


@run_status_sensor(
    run_status=DagsterRunStatus.SUCCESS,
    monitored_jobs=[gold_job],
    request_job=anon_job,
    name="trigger_anon_after_gold",
)
def trigger_anon_after_gold(context):
    """Rebuild silver_anon/gold_anon after gold_job succeeds."""
    return _chain(context)
