import json
from datetime import date, datetime, timedelta


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource


def _get_high_water_mark(context: AssetExecutionContext) -> datetime | None:
    """Read high-water mark from the last successful materialization metadata."""
    event = context.instance.get_latest_materialization_event(context.asset_key)
    if event and event.asset_materialization:
        meta = event.asset_materialization.metadata
        if "high_water_mark" in meta:
            hwm = datetime.fromisoformat(meta["high_water_mark"].value)
            return hwm - timedelta(minutes=5)
    return None


def _make_crm_asset(object_type: str, table: str):
    @asset(name=table, group_name="bronze")
    def _asset(context: AssetExecutionContext, hubspot: HubSpotResource, ch: ClickHouseResource):
        since = _get_high_water_mark(context)
        run_start = datetime.utcnow()
        records_written = 0

        for batch in hubspot.fetch_crm_objects_batched(object_type, since=since):
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

        yield MaterializeResult(
            metadata={
                "high_water_mark": MetadataValue.text(run_start.isoformat()),
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

    yield MaterializeResult(
        metadata={
            "high_water_mark": MetadataValue.text(run_start.isoformat()),
            "records_written": MetadataValue.int(records_written),
        }
    )
