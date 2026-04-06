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
from jobs import bronze_job, silver_job, gold_job, full_pipeline_job
from schedules import hourly_schedule
from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource

load_dotenv()

all_assets = [
    hs_contacts, hs_companies, hs_deals, hs_leads,
    hs_calls, hs_meetings, hs_engagement_emails, hs_notes, hs_tasks,
    hs_campaigns, hs_forms, hs_pipelines, hs_lead_pipelines, hs_form_submissions,
    hs_owners,
    # CRM ↔ CRM associations
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
] + all_silver_assets + all_gold_assets

defs = Definitions(
    assets=all_assets,
    jobs=[bronze_job, silver_job, gold_job, full_pipeline_job],
    schedules=[hourly_schedule],
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
    },
)
