from dagster import define_asset_job, AssetSelection, Backoff, RetryPolicy

# Re-run a failed op after a pause instead of failing the whole run. Every
# silver/gold/anon asset rebuilds a staging table from scratch, so a step
# re-run is idempotent; bronze inserts dedupe via ReplacingMergeTree.
_op_retry = RetryPolicy(max_retries=2, delay=20, backoff=Backoff.EXPONENTIAL)

bronze_job = define_asset_job(
    name="bronze_job",
    selection=AssetSelection.groups("bronze"),
    op_retry_policy=_op_retry,
)

silver_job = define_asset_job(
    name="silver_job",
    selection=AssetSelection.groups("silver"),
    op_retry_policy=_op_retry,
    config={
        "execution": {
            "config": {
                "multiprocess": {
                    # Keep peak ClickHouse memory low: the host VM is shared
                    # and has OOM-killed the server under 3 concurrent builds.
                    "max_concurrent": 2,
                }
            }
        }
    },
)

gold_job = define_asset_job(
    name="gold_job",
    selection=AssetSelection.groups("gold"),
    op_retry_policy=_op_retry,
)

anon_job = define_asset_job(
    name="anon_job",
    selection=AssetSelection.groups("silver_anon", "gold_anon"),
    op_retry_policy=_op_retry,
)
