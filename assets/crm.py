import json
from datetime import date, datetime


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource


def _make_crm_asset(object_type: str, table: str):
    @asset(name=table, group_name="bronze")
    def _asset(context: AssetExecutionContext, hubspot: HubSpotResource, ch: ClickHouseResource):
        run_start = datetime.utcnow()
        records_written = 0

        for batch in hubspot.fetch_crm_objects_batched(object_type):
            rows = [
                (
                    str(r["id"]),
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
                "object_type": MetadataValue.text(object_type),
            }
        )

    return _asset


hs_contacts = _make_crm_asset("contacts", "hs_contacts")
hs_companies = _make_crm_asset("companies", "hs_companies")
hs_deals = _make_crm_asset("deals", "hs_deals")
hs_leads = _make_crm_asset("leads", "hs_leads")


@asset(name="hs_owners", group_name="bronze")
def hs_owners(context: AssetExecutionContext, hubspot: HubSpotResource, ch: ClickHouseResource):
    """Extract owners from /crm/v3/owners (flat JSON, no properties map)."""
    run_start = datetime.utcnow()
    records_written = 0

    for batch in hubspot.fetch_owners():
        rows = [
            (
                str(r["id"]),
                run_start,
                {},  # owners have no properties map
                json.dumps(r, default=_json_default),
            )
            for r in batch
        ]
        records_written += ch.insert_records("hs_owners", rows)

    context.log.info(f"hs_owners: {records_written} records written")
    yield MaterializeResult(
        metadata={
            "records_written": MetadataValue.int(records_written),
        }
    )
