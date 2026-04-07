from dagster import define_asset_job, AssetSelection

bronze_job = define_asset_job(
    name="bronze_job",
    selection=AssetSelection.groups("bronze"),
)

silver_job = define_asset_job(
    name="silver_job",
    selection=AssetSelection.groups("silver"),
)

gold_job = define_asset_job(
    name="gold_job",
    selection=AssetSelection.groups("gold"),
)
