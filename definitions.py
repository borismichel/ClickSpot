import os
from dotenv import load_dotenv
from dagster import Definitions

from assets.crm import hs_contacts, hs_companies, hs_deals, hs_leads
from assets.activities import hs_calls, hs_meetings, hs_engagement_emails, hs_notes, hs_tasks
from assets.marketing import hs_campaigns, hs_forms, hs_ads, hs_marketing_emails
from jobs import bronze_job
from schedules import hourly_schedule
from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource

load_dotenv()

all_assets = [
    hs_contacts, hs_companies, hs_deals, hs_leads,
    hs_calls, hs_meetings, hs_engagement_emails, hs_notes, hs_tasks,
    hs_campaigns, hs_forms, hs_ads, hs_marketing_emails,
]

defs = Definitions(
    assets=all_assets,
    jobs=[bronze_job],
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
    },
)
