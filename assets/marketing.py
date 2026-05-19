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


# ---------------------------------------------------------------------------
# Lists / segments — flat JSON catalog + per-object-type memberships
# ---------------------------------------------------------------------------

@asset(name="hs_lists", group_name="bronze")
def hs_lists(
    context: AssetExecutionContext,
    hubspot: HubSpotResource,
    ch: ClickHouseResource,
):
    """List catalog from POST /crm/v3/lists/search (flat JSON, no properties map)."""
    run_start = datetime.utcnow()
    records_written = 0
    for batch in hubspot.fetch_lists():
        rows = [
            (
                str(r["listId"]),
                run_start,
                {},
                json.dumps(r, default=_json_default),
            )
            for r in batch
            if r.get("listId") is not None
        ]
        records_written += ch.insert_records("hs_lists", rows)

    context.log.info(f"hs_lists: {records_written} records written")
    yield MaterializeResult(
        metadata={
            "records_written": MetadataValue.int(records_written),
            "api_path": MetadataValue.text("/crm/v3/lists/search"),
        }
    )


# objectTypeId values per HubSpot docs. Confirm against /crm/v3/lists/search on
# a live portal if a future API rev introduces new IDs.
_LIST_OBJECT_TYPE_IDS = {
    "contact": "0-1",
    "company": "0-2",
    "deal":    "0-3",
    "lead":    "0-136",
}


def _fetch_list_memberships_for_object_type(
    hubspot: HubSpotResource,
    ch: ClickHouseResource,
    *,
    object_type_id: str,
    bronze_table: str,
    run_start: datetime,
    log=None,
) -> tuple[int, int]:
    """Iterate every list of the given objectTypeId, write memberships as
    (_from_id=list_id, _to_id=record_id, _association_type='MEMBER',
    _extracted_at) tuples into the assoc-shaped bronze table.

    Returns (rows_written, lists_skipped). Per-list 4xx errors are logged and
    skipped — HubSpot occasionally returns 400 for archived/in-progress lists
    even when /lists/search lists them, and one bad list shouldn't fail the
    whole asset.
    """
    import requests as _requests

    res = ch.get_client().query(
        "SELECT _record_id FROM bronze.hs_lists FINAL "
        "WHERE JSONExtractString(_raw, 'objectTypeId') = %(otid)s",
        parameters={"otid": object_type_id},
    )
    list_ids = [row[0] for row in res.result_rows]
    written = 0
    skipped = 0
    for list_id in list_ids:
        try:
            for batch in hubspot.fetch_list_memberships(list_id):
                rows = [
                    (list_id, str(m["recordId"]), "MEMBER", run_start)
                    for m in batch
                    if m.get("recordId") is not None
                ]
                written += ch.insert_association_records(bronze_table, rows)
        except _requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "?"
            if log is not None:
                log.warning(
                    f"Skipping list {list_id} for objectTypeId={object_type_id}: "
                    f"HTTP {status} — {e}"
                )
            skipped += 1
            continue
    return written, skipped


def _make_list_membership_asset(suffix: str):
    object_type_id = _LIST_OBJECT_TYPE_IDS[suffix]
    bronze_table = f"hs_assoc_list_{suffix}"

    @asset(name=bronze_table, group_name="bronze", deps=[hs_lists])
    def _asset(
        context: AssetExecutionContext,
        hubspot: HubSpotResource,
        ch: ClickHouseResource,
    ):
        run_start = datetime.utcnow()
        written, skipped = _fetch_list_memberships_for_object_type(
            hubspot, ch,
            object_type_id=object_type_id,
            bronze_table=bronze_table,
            run_start=run_start,
            log=context.log,
        )
        context.log.info(
            f"{bronze_table}: {written} memberships written, {skipped} lists skipped"
        )
        yield MaterializeResult(
            metadata={
                "records_written": MetadataValue.int(written),
                "lists_skipped": MetadataValue.int(skipped),
                "object_type_id": MetadataValue.text(object_type_id),
            }
        )

    return _asset


hs_assoc_list_contact = _make_list_membership_asset("contact")
hs_assoc_list_company = _make_list_membership_asset("company")
hs_assoc_list_deal = _make_list_membership_asset("deal")
hs_assoc_list_lead = _make_list_membership_asset("lead")


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
