import json
from datetime import datetime, timedelta
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource
from assets.crm import _get_high_water_mark, _json_default


def _make_marketing_asset(name: str, path: str, table: str, id_field: str = "id"):
    @asset(name=table, group_name="bronze")
    def _asset(context: AssetExecutionContext, hubspot: HubSpotResource, ch: ClickHouseResource):
        since = _get_high_water_mark(context)
        run_start = datetime.utcnow()
        records_written = 0

        for batch in hubspot.fetch_marketing_list(path, since=since):
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

        yield MaterializeResult(
            metadata={
                "high_water_mark": MetadataValue.text(run_start.isoformat()),
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
# BLOCKED: hs_ads and hs_marketing_emails deactivated — API endpoint issues
# hs_ads = _make_marketing_asset("ads", "/ads/v3/accounts", "hs_ads")
# hs_marketing_emails = _make_marketing_asset("marketing_emails", "/marketing/v3/emails/statistics/list", "hs_marketing_emails")

hs_pipelines = _make_marketing_asset(
    "pipelines", "/crm/v3/pipelines/deals", "hs_pipelines"
)
hs_lead_pipelines = _make_marketing_asset(
    "lead_pipelines", "/crm/v3/pipelines/leads", "hs_lead_pipelines"
)
