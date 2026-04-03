import json
from datetime import datetime
from dagster import asset, AssetExecutionContext, MaterializeResult, MetadataValue

from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource


ASSOCIATION_PAIRS = [
    # CRM ↔ CRM
    ("contacts", "companies", "hs_assoc_contact_company"),
    ("contacts", "deals",     "hs_assoc_contact_deal"),
    ("deals",    "companies", "hs_assoc_deal_company"),
    ("leads",    "contacts",  "hs_assoc_lead_contact"),
    ("deals",    "leads",     "hs_assoc_deal_lead"),
    ("leads",    "companies", "hs_assoc_lead_company"),
    # Activity ↔ Contacts
    ("calls",    "contacts",  "hs_assoc_call_contact"),
    ("meetings", "contacts",  "hs_assoc_meeting_contact"),
    ("emails",   "contacts",  "hs_assoc_email_contact"),
    ("notes",    "contacts",  "hs_assoc_note_contact"),
    ("tasks",    "contacts",  "hs_assoc_task_contact"),
    # Activity ↔ Companies
    ("calls",    "companies", "hs_assoc_call_company"),
    ("meetings", "companies", "hs_assoc_meeting_company"),
    ("emails",   "companies", "hs_assoc_email_company"),
    ("notes",    "companies", "hs_assoc_note_company"),
    ("tasks",    "companies", "hs_assoc_task_company"),
    # Activity ↔ Deals
    ("calls",    "deals",     "hs_assoc_call_deal"),
    ("meetings", "deals",     "hs_assoc_meeting_deal"),
    ("emails",   "deals",     "hs_assoc_email_deal"),
    ("notes",    "deals",     "hs_assoc_note_deal"),
    ("tasks",    "deals",     "hs_assoc_task_deal"),
]


def _make_association_asset(from_type: str, to_type: str, table: str):
    @asset(name=table, group_name="bronze")
    def _asset(
        context: AssetExecutionContext,
        hubspot: HubSpotResource,
        ch: ClickHouseResource,
    ):
        run_start = datetime.utcnow()
        records_written = 0

        object_ids = hubspot.fetch_all_object_ids(from_type)
        context.log.info(f"Fetched {len(object_ids)} {from_type} IDs for association lookup")

        for batch in hubspot.fetch_associations_batched(from_type, to_type, object_ids):
            rows = [
                (r["from_id"], r["to_id"], r["association_type"], run_start)
                for r in batch
            ]
            records_written += ch.insert_association_records(table, rows)

        yield MaterializeResult(
            metadata={
                "records_written": MetadataValue.int(records_written),
                "from_type": MetadataValue.text(from_type),
                "to_type": MetadataValue.text(to_type),
            }
        )

    return _asset


# Generate all association assets
_association_assets = {
    table: _make_association_asset(from_type, to_type, table)
    for from_type, to_type, table in ASSOCIATION_PAIRS
}

# CRM ↔ CRM
hs_assoc_contact_company = _association_assets["hs_assoc_contact_company"]
hs_assoc_contact_deal = _association_assets["hs_assoc_contact_deal"]
hs_assoc_deal_company = _association_assets["hs_assoc_deal_company"]
hs_assoc_lead_contact = _association_assets["hs_assoc_lead_contact"]
hs_assoc_deal_lead = _association_assets["hs_assoc_deal_lead"]
hs_assoc_lead_company = _association_assets["hs_assoc_lead_company"]
# Activity ↔ Contacts
hs_assoc_call_contact = _association_assets["hs_assoc_call_contact"]
hs_assoc_meeting_contact = _association_assets["hs_assoc_meeting_contact"]
hs_assoc_email_contact = _association_assets["hs_assoc_email_contact"]
hs_assoc_note_contact = _association_assets["hs_assoc_note_contact"]
hs_assoc_task_contact = _association_assets["hs_assoc_task_contact"]
# Activity ↔ Companies
hs_assoc_call_company = _association_assets["hs_assoc_call_company"]
hs_assoc_meeting_company = _association_assets["hs_assoc_meeting_company"]
hs_assoc_email_company = _association_assets["hs_assoc_email_company"]
hs_assoc_note_company = _association_assets["hs_assoc_note_company"]
hs_assoc_task_company = _association_assets["hs_assoc_task_company"]
# Activity ↔ Deals
hs_assoc_call_deal = _association_assets["hs_assoc_call_deal"]
hs_assoc_meeting_deal = _association_assets["hs_assoc_meeting_deal"]
hs_assoc_email_deal = _association_assets["hs_assoc_email_deal"]
hs_assoc_note_deal = _association_assets["hs_assoc_note_deal"]
hs_assoc_task_deal = _association_assets["hs_assoc_task_deal"]
