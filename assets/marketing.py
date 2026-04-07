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


@asset(name="hs_form_submissions", group_name="bronze", deps=[])
def hs_form_submissions(
    context: AssetExecutionContext,
    hubspot: HubSpotResource,
    ch: ClickHouseResource,
):
    """Extract form submissions across all forms.

    Iterates all forms, fetches submissions per form via the legacy v1 API,
    and stores each submission as a bronze record with form_id/form_name
    injected into the properties map.
    """
    run_start = datetime.utcnow()
    records_written = 0

    forms = hubspot.fetch_all_form_ids()
    context.log.info(f"Found {len(forms)} forms to fetch submissions for")

    for form in forms:
        form_id = form["id"]
        form_name = form["name"]
        form_count = 0

        for batch in hubspot.fetch_form_submissions(form_id):
            rows = []
            for sub in batch:
                # Flatten values array into a properties-like dict
                props = {
                    "form_id": form_id,
                    "form_name": form_name,
                    "submitted_at": str(sub.get("submittedAt") or ""),
                    "page_url": str(sub.get("pageUrl") or ""),
                }
                for field in sub.get("values", []):
                    props[field["name"]] = str(field.get("value") or "")

                rows.append((
                    str(sub.get("conversionId", "")),
                    run_start,
                    props,
                    json.dumps(sub, default=_json_default),
                ))
            form_count += ch.insert_records("hs_form_submissions", rows)

        if form_count > 0:
            context.log.info(f"  {form_name}: {form_count} submissions")
        records_written += form_count

    context.log.info(f"hs_form_submissions: {records_written} total submissions")
    yield MaterializeResult(
        metadata={
            "records_written": MetadataValue.int(records_written),
            "forms_scanned": MetadataValue.int(len(forms)),
        }
    )
