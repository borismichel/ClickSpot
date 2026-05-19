import os
from dotenv import load_dotenv
from dagster import Definitions

from assets.crm import hs_contacts, hs_companies, hs_deals, hs_leads, hs_owners
from assets.activities import hs_calls, hs_meetings, hs_engagement_emails, hs_notes, hs_tasks
from assets.marketing import hs_campaigns, hs_forms, hs_pipelines, hs_lead_pipelines, hs_form_submissions
from assets.associations import (
    # CRM ↔ CRM
    hs_assoc_contact_company, hs_assoc_contact_deal, hs_assoc_deal_company,
    hs_assoc_lead_contact, hs_assoc_deal_lead, hs_assoc_lead_company,
    # Activity ↔ Contacts
    hs_assoc_call_contact, hs_assoc_meeting_contact, hs_assoc_email_contact,
    hs_assoc_note_contact, hs_assoc_task_contact,
    # Activity ↔ Companies
    hs_assoc_call_company, hs_assoc_meeting_company, hs_assoc_email_company,
    hs_assoc_note_company, hs_assoc_task_company,
    # Activity ↔ Deals
    hs_assoc_call_deal, hs_assoc_meeting_deal, hs_assoc_email_deal,
    hs_assoc_note_deal, hs_assoc_task_deal,
)
from assets.silver import all_silver_assets
from assets.gold import all_gold_assets
from assets.silver_anon import all_silver_anon_assets
from assets.gold_anon import all_gold_anon_assets
from jobs import bronze_job, silver_job, gold_job, anon_job
from schedules import hourly_schedule
from sensors import (
    trigger_silver_after_bronze,
    trigger_gold_after_silver,
    trigger_anon_after_gold,
)
from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource
from app.customer import extraction as _ext

load_dotenv()


# ---------------------------------------------------------------------------
# Asset registries — symbols keyed by their bronze table name so we can filter
# by `app.customer.extraction.get_enabled_bronze_tables()` at startup.
# Existing symbols are imported unchanged so the file diff stays minimal.
# ---------------------------------------------------------------------------

_BRONZE_OBJECT_ASSETS = {
    "hs_contacts": hs_contacts,
    "hs_companies": hs_companies,
    "hs_deals": hs_deals,
    "hs_leads": hs_leads,
    "hs_owners": hs_owners,
    "hs_calls": hs_calls,
    "hs_meetings": hs_meetings,
    "hs_engagement_emails": hs_engagement_emails,
    "hs_notes": hs_notes,
    "hs_tasks": hs_tasks,
    "hs_campaigns": hs_campaigns,
    "hs_forms": hs_forms,
    "hs_pipelines": hs_pipelines,
    "hs_lead_pipelines": hs_lead_pipelines,
    "hs_form_submissions": hs_form_submissions,
}

_BRONZE_ASSOC_ASSETS = {
    "hs_assoc_contact_company": hs_assoc_contact_company,
    "hs_assoc_contact_deal": hs_assoc_contact_deal,
    "hs_assoc_deal_company": hs_assoc_deal_company,
    "hs_assoc_lead_contact": hs_assoc_lead_contact,
    "hs_assoc_deal_lead": hs_assoc_deal_lead,
    "hs_assoc_lead_company": hs_assoc_lead_company,
    "hs_assoc_call_contact": hs_assoc_call_contact,
    "hs_assoc_meeting_contact": hs_assoc_meeting_contact,
    "hs_assoc_email_contact": hs_assoc_email_contact,
    "hs_assoc_note_contact": hs_assoc_note_contact,
    "hs_assoc_task_contact": hs_assoc_task_contact,
    "hs_assoc_call_company": hs_assoc_call_company,
    "hs_assoc_meeting_company": hs_assoc_meeting_company,
    "hs_assoc_email_company": hs_assoc_email_company,
    "hs_assoc_note_company": hs_assoc_note_company,
    "hs_assoc_task_company": hs_assoc_task_company,
    "hs_assoc_call_deal": hs_assoc_call_deal,
    "hs_assoc_meeting_deal": hs_assoc_meeting_deal,
    "hs_assoc_email_deal": hs_assoc_email_deal,
    "hs_assoc_note_deal": hs_assoc_note_deal,
    "hs_assoc_task_deal": hs_assoc_task_deal,
}


def _build_asset_list():
    """Compose the asset list, filtered by the extraction settings.

    Reads `~/.clickspot/customer.json -> extraction`. Missing block = everything
    enabled (backward-compatible default).
    """
    enabled_bronze = _ext.get_enabled_bronze_tables()
    enabled_assoc = _ext.get_enabled_assoc_tables()

    bronze = [a for table, a in _BRONZE_OBJECT_ASSETS.items() if table in enabled_bronze]
    bronze += [a for table, a in _BRONZE_ASSOC_ASSETS.items() if table in enabled_assoc]
    return bronze + all_silver_assets + all_gold_assets + all_silver_anon_assets + all_gold_anon_assets


all_assets = _build_asset_list()

defs = Definitions(
    assets=all_assets,
    jobs=[bronze_job, silver_job, gold_job, anon_job],
    schedules=[hourly_schedule],
    sensors=[
        trigger_silver_after_bronze,
        trigger_gold_after_silver,
        trigger_anon_after_gold,
    ],
    resources={
        "hubspot": HubSpotResource(
            access_token=os.environ["HUBSPOT_TOKEN"],
        ),
        "ch": ClickHouseResource(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
            username=os.environ["CLICKHOUSE_USER"],
            password=os.environ["CLICKHOUSE_PASSWORD"],
        ),
        "ch_silver": ClickHouseResource(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
            username=os.environ["CLICKHOUSE_USER"],
            password=os.environ["CLICKHOUSE_PASSWORD"],
            database="silver",
        ),
        "ch_gold": ClickHouseResource(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
            username=os.environ["CLICKHOUSE_USER"],
            password=os.environ["CLICKHOUSE_PASSWORD"],
            database="gold",
        ),
        "ch_silver_anon": ClickHouseResource(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
            username=os.environ["CLICKHOUSE_USER"],
            password=os.environ["CLICKHOUSE_PASSWORD"],
            database="silver_anon",
        ),
        "ch_gold_anon": ClickHouseResource(
            host=os.environ["CLICKHOUSE_HOST"],
            port=int(os.environ.get("CLICKHOUSE_PORT", 8123)),
            username=os.environ["CLICKHOUSE_USER"],
            password=os.environ["CLICKHOUSE_PASSWORD"],
            database="gold_anon",
        ),
    },
)
