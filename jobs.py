from dagster import define_asset_job, AssetSelection

bronze_job = define_asset_job(
    name="bronze_job",
    selection=AssetSelection.all(),
)
