import json
from datetime import datetime
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource
from assets.crm import _json_default


def _make_marketing_asset(name: str, path: str, table: str, id_field: str = "id"):
    @asset(name=table, group_name="bronze")
    def _asset(context: AssetExecutionContext, hubspot: HubSpotResource, ch: ClickHouseResource):
        run_start = datetime.utcnow()
        records_written = 0

        for batch in hubspot.fetch_marketing_list(path):
            rows = [
                (
                    str(r[id_field]),
                    run_start,
                    {k: str(v) if v is not None else "" for k, v in r.get("properties", {}).items()},
                    json.dumps(r, default=_json_default),
                )
                for r in batch
            ]
            records_written += ch.insert_records(table, rows)

        context.log.info(f"{table}: {records_written} records written")
        yield MaterializeResult(
            metadata={
                "records_written": MetadataValue.int(records_written),
                "api_path": MetadataValue.text(path),
            }
        )

    return _asset


hs_campaigns = _make_marketing_asset(
    "campaigns", "/marketing/v3/campaigns", "hs_campaigns"
)
hs_forms = _make_marketing_asset(
    "forms", "/marketing/v3/forms", "hs_forms"
)

hs_pipelines = _make_marketing_asset(
    "pipelines", "/crm/v3/pipelines/deals", "hs_pipelines"
)
hs_lead_pipelines = _make_marketing_asset(
    "lead_pipelines", "/crm/v3/pipelines/leads", "hs_lead_pipelines"
)
