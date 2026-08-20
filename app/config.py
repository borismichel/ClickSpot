"""Graph topology and field metadata for the associative analytics engine.

Silver-table entries in ``TABLES`` are derived from :mod:`silver_config` so
column definitions live in exactly one place. Display labels, the ``extras``
overlay (for denormalized columns added in ``assets/silver.py``), and the
hand-rolled ``fact_activities`` / ``fact_stage_history`` entries live here.
Gold tables stay fully hand-rolled — their columns are computed in
``assets/gold/`` and have no silver counterpart.
"""

import silver_config
from silver_config import (
    DIM_COMPANIES,
    DIM_CONTACTS,
    DIM_DEALS,
    DIM_LEAD_PIPELINES,
    DIM_LEAD_PIPELINE_STAGES,
    DIM_LEADS,
    DIM_LISTS,
    DIM_OWNERS,
    DIM_PIPELINES,
    DIM_PIPELINE_STAGES,
    FACT_FORM_SUBMISSIONS,
)

# Each edge is bidirectional — the engine can traverse in either direction.
GRAPH_EDGES = [
    # CRM ↔ CRM
    {
        "from": "dim_companies",
        "to": "dim_contacts",
        "bridge": "bridge_contact_company",
        "from_key": "company_id",
        "to_key": "contact_id",
    },
    {
        "from": "dim_contacts",
        "to": "dim_deals",
        "bridge": "bridge_contact_deal",
        "from_key": "contact_id",
        "to_key": "deal_id",
    },
    {
        "from": "dim_companies",
        "to": "dim_deals",
        "bridge": "bridge_deal_company",
        "from_key": "company_id",
        "to_key": "deal_id",
    },
    {
        "from": "dim_leads",
        "to": "dim_contacts",
        "bridge": "bridge_lead_contact",
        "from_key": "lead_id",
        "to_key": "contact_id",
    },
    {
        "from": "dim_deals",
        "to": "dim_leads",
        "bridge": "bridge_deal_lead",
        "from_key": "deal_id",
        "to_key": "lead_id",
    },
    {
        "from": "dim_leads",
        "to": "dim_companies",
        "bridge": "bridge_lead_company",
        "from_key": "lead_id",
        "to_key": "company_id",
    },
    # Lists ↔ CRM
    {
        "from": "dim_lists",
        "to": "dim_contacts",
        "bridge": "bridge_list_contact",
        "from_key": "list_id",
        "to_key": "contact_id",
    },
    {
        "from": "dim_lists",
        "to": "dim_companies",
        "bridge": "bridge_list_company",
        "from_key": "list_id",
        "to_key": "company_id",
    },
    {
        "from": "dim_lists",
        "to": "dim_deals",
        "bridge": "bridge_list_deal",
        "from_key": "list_id",
        "to_key": "deal_id",
    },
    {
        "from": "dim_lists",
        "to": "dim_leads",
        "bridge": "bridge_list_lead",
        "from_key": "list_id",
        "to_key": "lead_id",
    },
    # Activity ↔ CRM (direct bridges)
    {
        "from": "dim_contacts",
        "to": "fact_activities",
        "bridge": "bridge_activity_contact",
        "from_key": "contact_id",
        "to_key": "activity_id",
    },
    {
        "from": "dim_companies",
        "to": "fact_activities",
        "bridge": "bridge_activity_company",
        "from_key": "company_id",
        "to_key": "activity_id",
    },
    {
        "from": "dim_deals",
        "to": "fact_activities",
        "bridge": "bridge_activity_deal",
        "from_key": "deal_id",
        "to_key": "activity_id",
    },
]

# Direct FK joins (no bridge table needed)
REFERENCE_JOINS = [
    {
        "from": "dim_deals",
        "to": "dim_pipelines",
        "from_col": "pipeline",
        "to_col": "pipeline_id",
    },
    {
        "from": "dim_deals",
        "to": "dim_pipeline_stages",
        "from_col": "dealstage",
        "to_col": "stage_id",
    },
    {
        "from": "dim_deals",
        "to": "dim_owners",
        "from_col": "hubspot_owner_id",
        "to_col": "owner_id",
    },
    {
        "from": "dim_leads",
        "to": "dim_owners",
        "from_col": "hubspot_owner_id",
        "to_col": "owner_id",
    },
    {
        "from": "dim_companies",
        "to": "dim_owners",
        "from_col": "hubspot_owner_id",
        "to_col": "owner_id",
    },
    {
        "from": "fact_activities",
        "to": "dim_owners",
        "from_col": "hubspot_owner_id",
        "to_col": "owner_id",
    },
    {
        "from": "dim_leads",
        "to": "dim_lead_pipelines",
        "from_col": "hs_pipeline",
        "to_col": "pipeline_id",
    },
    {
        "from": "dim_leads",
        "to": "dim_lead_pipeline_stages",
        "from_col": "hs_pipeline_stage",
        "to_col": "stage_id",
    },
]


# ---------------------------------------------------------------------------
# Silver-table derivation
# ---------------------------------------------------------------------------

# Silver-config blocks to surface in TABLES, with their catalog metadata.
# (silver_config_block, catalog_name, primary_key, display_name)
_SILVER_SOURCES = [
    (DIM_CONTACTS,             "dim_contacts",             "contact_id",    "Contacts"),
    (DIM_COMPANIES,            "dim_companies",            "company_id",    "Companies"),
    (DIM_DEALS,                "dim_deals",                "deal_id",       "Deals"),
    (DIM_LEADS,                "dim_leads",                "lead_id",       "Leads"),
    (DIM_OWNERS,               "dim_owners",               "owner_id",      "Owners"),
    (DIM_PIPELINES,            "dim_pipelines",            "pipeline_id",   "Pipelines"),
    (DIM_PIPELINE_STAGES,      "dim_pipeline_stages",      "stage_id",      "Pipeline Stages"),
    (DIM_LEAD_PIPELINES,       "dim_lead_pipelines",       "pipeline_id",   "Lead Pipelines"),
    (DIM_LEAD_PIPELINE_STAGES, "dim_lead_pipeline_stages", "stage_id",      "Lead Pipeline Stages"),
    (DIM_LISTS,                "dim_lists",                "list_id",       "Lists / Segments"),
    (FACT_FORM_SUBMISSIONS,    "fact_form_submissions",    "submission_id", "Form Submissions"),
]

# Per-table display labels and denormalized extras.
# ``field_displays``: override the auto-humanized label for specific columns.
# ``extras``: columns added in the silver asset DDL (e.g. dictGet-derived labels)
#             that do not exist in silver_config.columns.
_SILVER_OVERLAY: dict[str, dict] = {
    "dim_contacts": {
        "field_displays": {
            "email": "Email",
            "full_name": "Full Name",
            "jobtitle": "Job Title",
            "lifecyclestage": "Lifecycle Stage",
            "hs_analytics_source": "Analytics Source",
            "hs_analytics_source_data_1": "Source Detail 1",
            "hs_analytics_source_data_2": "Source Detail 2",
            "hs_object_source_label": "Object Source",
            "createdate": "Created",
            "hs_v2_date_entered_marketingqualifiedlead": "MQL Date",
            "hs_v2_date_entered_salesqualifiedlead": "SQL Date",
            "hs_analytics_first_timestamp": "First Seen",
            "first_conversion_date": "First Conversion Date",
            "recent_conversion_date": "Recent Conversion Date",
            "first_deal_created_date": "First Deal Created Date",
            "closedate": "Close Date",
            "hs_analytics_first_visit_timestamp": "First Visit",
            "hs_analytics_last_timestamp": "Last Seen",
            "hs_analytics_last_visit_timestamp": "Last Visit",
            "hs_latest_source_timestamp": "Latest Source Timestamp",
            "hs_last_sales_activity_date": "Last Sales Activity Date",
            "hs_last_sales_activity_timestamp": "Last Sales Activity Timestamp",
            "hs_last_sales_activity_type": "Last Sales Activity Type",
            "hs_sa_first_engagement_date": "First Sales Engagement Date",
            "first_outreach_date": "First Outreach Date",
            "hs_email_first_send_date": "Email First Send",
            "hs_email_last_send_date": "Email Last Send",
            "hs_email_first_open_date": "Email First Open",
            "hs_email_last_open_date": "Email Last Open",
            "hs_email_first_click_date": "Email First Click",
            "hs_email_last_click_date": "Email Last Click",
            "hs_latest_sequence_enrolled_date": "Latest Sequence Enrolled",
            "hs_latest_sequence_ended_date": "Latest Sequence Ended",
            "hs_latest_sequence_finished_date": "Latest Sequence Finished",
            "hs_latest_sequence_unenrolled_date": "Latest Sequence Unenrolled",
            "hs_latest_open_lead_date": "Latest Open Lead Date",
            "hs_latest_qualified_lead_date": "Latest Qualified Lead Date",
            "hs_latest_disqualified_lead_date": "Latest Disqualified Lead Date",
            "notes_last_updated": "Notes Last Updated",
            "notes_next_activity_date": "Next Activity Date",
            "hs_notes_next_activity_type": "Next Activity Type",
            "hubspot_owner_id": "Owner ID",
            "hubspot_owner_assigneddate": "Owner Assigned Date",
            "recent_deal_close_date": "Recent Deal Close Date",
        },
    },
    "dim_companies": {
        "field_displays": {
            "name": "Company Name",
            "domain": "Domain",
            "industry": "Industry",
            "city": "City",
            "country": "Country",
            "lifecyclestage": "Lifecycle Stage",
            "type": "Type",
            "numberofemployees": "Employees",
            "annualrevenue": "Annual Revenue",
            "hubspot_owner_id": "Owner ID",
            "createdate": "Created",
            "hs_lastmodifieddate": "Last Modified",
            "notes_last_updated": "Notes Last Updated",
            "first_contact_createdate": "First Contact Created",
            "first_deal_created_date": "First Deal Created",
            "first_conversion_date": "First Conversion Date",
            "recent_conversion_date": "Recent Conversion Date",
            "closedate": "Close Date",
            "recent_deal_close_date": "Recent Deal Close Date",
            "hs_analytics_first_timestamp": "First Seen",
            "hs_analytics_first_visit_timestamp": "First Visit",
            "hs_analytics_last_timestamp": "Last Seen",
            "hs_analytics_last_visit_timestamp": "Last Visit",
            "hs_analytics_latest_source_timestamp": "Latest Source Timestamp",
            "hs_last_sales_activity_date": "Last Sales Activity Date",
            "hs_last_sales_activity_timestamp": "Last Sales Activity Timestamp",
            "hs_last_sales_activity_type": "Last Sales Activity Type",
            "hs_last_booked_meeting_date": "Last Booked Meeting Date",
            "hs_last_logged_call_date": "Last Logged Call Date",
            "hs_last_logged_outgoing_email_date": "Last Logged Outgoing Email Date",
            "hs_last_open_task_date": "Last Open Task Date",
            "notes_next_activity_date": "Next Activity Date",
            "hs_notes_next_activity_type": "Next Activity Type",
            "hubspot_owner_assigneddate": "Owner Assigned Date",
        },
    },
    "dim_deals": {
        "field_displays": {
            "dealname": "Deal Name",
            "dealstage": "Deal Stage",
            "pipeline": "Pipeline ID",
            "amount": "Amount",
            "deal_currency_code": "Currency",
            "hubspot_owner_id": "Owner ID",
            "hubspot_team_id": "Team ID",
            "hs_manual_forecast_category": "Forecast Category",
            "hs_deal_stage_probability": "Stage Probability",
            "hs_forecast_amount": "Forecast Amount",
            "days_to_close": "Days to Close",
            "closedate": "Close Date",
            "createdate": "Created",
            "closedlost_reason": "Lost Reason",
            "won_reason": "Won Reason",
            "hs_is_closed_won": "Closed Won",
            "hs_is_closed": "Closed",
            "hs_closed_deal_close_date": "Closed Deal Close Date",
            "hs_closed_deal_create_date": "Closed Deal Create Date",
            "hs_closed_won_date": "Closed Won Date",
            "hs_open_deal_create_date": "Open Deal Create Date",
            "hs_analytics_latest_source_timestamp": "Latest Source Timestamp",
            "hs_analytics_latest_source_timestamp_company": "Latest Source Timestamp (Company)",
            "hs_analytics_latest_source_timestamp_contact": "Latest Source Timestamp (Contact)",
            "hs_latest_marketing_email_open_date": "Latest Marketing Email Open",
            "hs_latest_marketing_email_click_date": "Latest Marketing Email Click",
            "hs_latest_sales_email_open_date": "Latest Sales Email Open",
            "hs_latest_sales_email_reply_date": "Latest Sales Email Reply",
            "hs_is_stalled_after_timestamp": "Stalled After",
            "hs_next_step_updated_at": "Next Step Updated At",
            "notes_last_updated": "Notes Last Updated",
            "notes_next_activity_date": "Next Activity Date",
            "hs_notes_next_activity_type": "Next Activity Type",
            "hubspot_owner_assigneddate": "Owner Assigned Date",
        },
        "extras": {
            # Denormalized label columns added in assets/silver.py::dim_deals
            "pipeline_label": {"type": "String", "display": "Pipeline"},
            "stage_label":    {"type": "String", "display": "Stage"},
            "owner_name":     {"type": "String", "display": "Owner"},
        },
    },
    "dim_leads": {
        "field_displays": {
            "hs_lead_name": "Lead Name",
            "hs_pipeline": "Lead Pipeline ID",
            "hs_pipeline_stage": "Lead Pipeline Stage ID (use dict_lead_pipeline_stages for label)",
            "hs_lead_status": "Lead Status (currently unused, always empty)",
            "hs_lead_type": "Lead Type",
            "hubspot_owner_id": "Owner ID",
            "disqualification_reason": "Disqualification Reason",
            "hs_lead_call_count": "Call Count",
            "hs_lead_email_count": "Email Count",
            "first_outreach_date": "First Outreach Date",
            "last_engagement_date": "Last Engagement Date",
            "last_engagement_type": "Last Engagement Type",
            "last_activity_date": "Last Activity Date",
            "next_activity_date": "Next Activity Date",
            "next_activity_type": "Next Activity Type",
            "last_webpage_visit": "Last Webpage Visit",
            "contact_last_activity_date": "Contact Last Activity Date",
            "contact_last_engagement_date": "Contact Last Engagement Date",
            "contact_last_engagement_type": "Contact Last Engagement Type",
            "contact_last_webpage_visit": "Contact Last Webpage Visit",
            "contact_next_activity_date": "Contact Next Activity Date",
            "contact_next_activity_type": "Contact Next Activity Type",
            "company_last_activity_date": "Company Last Activity Date",
            "company_last_engagement_date": "Company Last Engagement Date",
            "company_last_engagement_type": "Company Last Engagement Type",
            "company_last_webpage_visit": "Company Last Webpage Visit",
            "company_next_activity_date": "Company Next Activity Date",
            "company_next_activity_type": "Company Next Activity Type",
            "pipeline_stage_last_updated": "Pipeline Stage Last Updated",
            "owner_assigned_date": "Owner Assigned Date",
            "date_entered_current_stage": "Date Entered Current Stage",
            "createdate": "Created",
        },
    },
    "dim_owners": {
        "field_displays": {
            "email": "Email",
            "first_name": "First Name",
            "last_name": "Last Name",
        },
    },
    "dim_pipelines": {
        "field_displays": {
            "label": "Pipeline Name",
        },
    },
    "dim_pipeline_stages": {
        "field_displays": {
            "label": "Stage Name",
            "pipeline_id": "Pipeline ID",
            "is_closed": "Is Closed",
            "display_order": "Display Order",
            "probability": "Probability",
        },
    },
    "dim_lead_pipelines": {
        "field_displays": {
            "label": "Pipeline Name",
        },
    },
    "dim_lead_pipeline_stages": {
        "field_displays": {
            "label": "Stage Name",
            "pipeline_id": "Pipeline ID",
            "is_closed": "Is Closed",
            "display_order": "Display Order",
        },
    },
    "dim_lists": {
        "field_displays": {
            "name": "List / Segment Name",
            "list_type": "List Type",
            "processing_type": "Processing Type",
            "object_type_id": "Member Object Type (0-1 contacts, 0-2 companies, 0-3 deals, 0-136 leads)",
            "processing_status": "Processing Status",
            "created_by_id": "Created By (Owner ID)",
            "updated_by_id": "Updated By (Owner ID)",
            "created_at": "Created",
            "updated_at": "Last Updated",
            "filters_updated_at": "Filters Last Updated",
        },
    },
    "fact_form_submissions": {
        "field_displays": {
            "form_id": "Form ID",
            "form_name": "Form Name",
            "submitted_at": "Submitted At",
            "page_url": "Page URL",
            "email": "Email",
            "firstname": "First Name",
            "lastname": "Last Name",
            "company": "Company",
            "jobtitle": "Job Title",
            "phone": "Phone",
        },
    },
}


def _humanize(col: str) -> str:
    """Fallback display label for columns without an explicit override."""
    s = col.removeprefix("hs_").replace("_", " ").strip()
    return s.title() if s else col


def _derive_silver_tables() -> dict:
    tables: dict[str, dict] = {}
    for config, name, primary_key, display_name in _SILVER_SOURCES:
        overlay = _SILVER_OVERLAY.get(name, {})
        displays = overlay.get("field_displays", {})
        fields: dict[str, dict] = {}
        for entry in config["columns"]:
            # 3-tuple (silver_col, bronze_prop, ch_type) for property/json sources;
            # 2-tuple (col, ch_type) for nested_stages sources.
            if len(entry) == 2:
                col_name, ch_type = entry
            else:
                col_name, _bronze, ch_type = entry
            fields[col_name] = {
                "type": ch_type,
                "display": displays.get(col_name, _humanize(col_name)),
            }
        for extra_name, extra_meta in overlay.get("extras", {}).items():
            fields[extra_name] = dict(extra_meta)
        tables[name] = {
            "primary_key": primary_key,
            "display_name": display_name,
            "fields": fields,
        }
    return tables


# ---------------------------------------------------------------------------
# Hand-rolled silver tables (not derivable from silver_config)
# ---------------------------------------------------------------------------

# fact_activities: silver_config uses per-activity-type property mapping, not a
# flat column list. fact_stage_history: not a silver_config dim at all.
_HANDROLLED_SILVER: dict[str, dict] = {
    "fact_activities": {
        "primary_key": "activity_id",
        "display_name": "Activities",
        "fields": {
            "activity_type":    {"type": "String",   "display": "Activity Type"},
            "subject":          {"type": "String",   "display": "Subject"},
            "disposition":      {"type": "String",   "display": "Disposition"},
            "hubspot_owner_id": {"type": "String",   "display": "Owner ID"},
            "hs_timestamp":     {"type": "DateTime", "display": "Activity Date"},
            "duration_ms":      {"type": "Nullable(Int64)", "display": "Duration (ms)"},
            "createdate":       {"type": "DateTime", "display": "Created"},
        },
    },
    "fact_stage_history": {
        "primary_key": "entity_id",
        "display_name": "Stage History (enter/exit timestamps per stage for leads, deals, contacts)",
        "fields": {
            "entity_type":    {"type": "LowCardinality(String)", "display": "Entity Type (lead/deal/contact)"},
            "stage_id":       {"type": "String",   "display": "Stage ID"},
            "stage_label":    {"type": "String",   "display": "Stage Name"},
            "entered_at":     {"type": "DateTime", "display": "Date Entered Stage"},
            "exited_at":      {"type": "Nullable(DateTime)", "display": "Date Exited Stage (NULL if still in stage)"},
            "duration_ms":    {"type": "Nullable(Int64)", "display": "Time in Stage (milliseconds)"},
        },
    },
}


# ---------------------------------------------------------------------------
# Gold tables (hand-rolled — columns are computed in assets/gold/)
# ---------------------------------------------------------------------------

_GOLD_TABLES: dict[str, dict] = {
    "agg_rep_performance": {
        "primary_key": "hubspot_owner_id",
        "display_name": "Rep Performance (monthly aggregates per rep)",
        "database": "gold",
        "fields": {
            "owner_name":     {"type": "String",           "display": "Rep Name (use directly, no dictGet needed)"},
            "period_start":   {"type": "Date",             "display": "Period Start"},
            "deals_won":      {"type": "UInt32",           "display": "Deals Won"},
            "deals_lost":     {"type": "UInt32",           "display": "Deals Lost"},
            "deals_created":  {"type": "UInt32",           "display": "Deals Created"},
            "win_rate":       {"type": "Nullable(Float64)", "display": "Win Rate"},
            "total_arr_closed": {"type": "Nullable(Float64)", "display": "ARR Closed"},
            "avg_deal_size":  {"type": "Nullable(Float64)", "display": "Avg Deal Size"},
            "avg_days_to_close": {"type": "Nullable(Float64)", "display": "Avg Days to Close"},
            "pipeline_value": {"type": "Nullable(Float64)", "display": "Pipeline Value"},
            "calls_count":    {"type": "UInt32",           "display": "Calls"},
            "meetings_count": {"type": "UInt32",           "display": "Meetings"},
            "emails_count":   {"type": "UInt32",           "display": "Emails"},
            "tasks_count":    {"type": "UInt32",           "display": "Tasks"},
            "total_activities": {"type": "UInt32",         "display": "Total Activities"},
        },
    },
    "agg_deal_health": {
        "primary_key": "deal_id",
        "display_name": "Deal Health (per-deal health indicators)",
        "database": "gold",
        "fields": {
            "dealname":       {"type": "String",           "display": "Deal Name"},
            "dealstage":      {"type": "String",           "display": "Deal Stage ID"},
            "stage_label":    {"type": "String",           "display": "Stage Label (use directly, no dictGet needed)"},
            "pipeline":       {"type": "String",           "display": "Pipeline ID"},
            "pipeline_label": {"type": "String",           "display": "Pipeline Label (use directly, no dictGet needed)"},
            "hubspot_owner_id": {"type": "String",         "display": "Owner ID"},
            "owner_name":     {"type": "String",           "display": "Owner Name (use directly, no dictGet needed)"},
            "amount":         {"type": "Nullable(Float64)", "display": "Amount"},
            "hs_is_closed":   {"type": "String",            "display": "Is Closed ('true'/'false')"},
            "hs_is_closed_won": {"type": "String",          "display": "Is Closed Won ('true'/'false')"},
            "days_in_current_stage": {"type": "Nullable(UInt32)", "display": "Days in Stage"},
            "days_since_last_activity": {"type": "Nullable(UInt32)", "display": "Days Since Activity"},
            "last_activity_date": {"type": "Nullable(DateTime)", "display": "Last Activity Date"},
            "last_activity_type": {"type": "String",       "display": "Last Activity Type"},
            "has_future_activity": {"type": "UInt8",       "display": "Has Future Activity"},
            "next_activity_date": {"type": "Nullable(DateTime)", "display": "Next Activity Date"},
            "is_stale":       {"type": "UInt8",            "display": "Stale"},
            "missing_amount": {"type": "UInt8",            "display": "Missing Amount"},
            "missing_closedate": {"type": "UInt8",         "display": "Missing Close Date"},
            "missing_owner":  {"type": "UInt8",            "display": "Missing Owner"},
        },
    },
    "agg_source_attribution": {
        "primary_key": "hs_analytics_source",
        "display_name": "Source Attribution",
        "database": "gold",
        "fields": {
            "hs_analytics_source_data_1": {"type": "String", "display": "Source Detail"},
            "contacts_count": {"type": "UInt32",           "display": "Contacts"},
            "mql_count":      {"type": "UInt32",           "display": "MQLs"},
            "sql_count":      {"type": "UInt32",           "display": "SQLs"},
            "deals_associated": {"type": "UInt32",         "display": "Deals"},
            "deals_won":      {"type": "UInt32",           "display": "Deals Won"},
            "closed_won_value": {"type": "Nullable(Float64)", "display": "Won Revenue"},
        },
    },
    "fact_pipeline_snapshots": {
        "primary_key": "snapshot_date",
        "display_name": "Pipeline Snapshots",
        "database": "gold",
        "fields": {
            "pipeline":       {"type": "LowCardinality(String)", "display": "Pipeline"},
            "total_open_deals": {"type": "UInt32",         "display": "Open Deals"},
            "total_pipeline_value": {"type": "Nullable(Float64)", "display": "Pipeline Value"},
            "weighted_pipeline_value": {"type": "Nullable(Float64)", "display": "Weighted Pipeline"},
            "closed_won_value": {"type": "Nullable(Float64)", "display": "Closed Won"},
        },
    },
    "agg_deal_stage_funnel": {
        "primary_key": "stage_id",
        "display_name": "Deal Stage Funnel (deals per pipeline stage)",
        "database": "gold",
        "fields": {
            "pipeline_id":        {"type": "LowCardinality(String)", "display": "Pipeline ID"},
            "stage_label":        {"type": "String",           "display": "Stage Label"},
            "display_order":      {"type": "UInt32",           "display": "Stage Order"},
            "is_closed":          {"type": "LowCardinality(String)", "display": "Is Closed Stage"},
            "deals_currently_in": {"type": "UInt32",           "display": "Deals in Stage"},
            "total_value":        {"type": "Nullable(Float64)", "display": "Total Value"},
            "weighted_value":     {"type": "Nullable(Float64)", "display": "Weighted Value"},
        },
    },
    "agg_lead_health": {
        "primary_key": "lead_id",
        "display_name": "Lead Health (per-lead health indicators)",
        "database": "gold",
        "fields": {
            "lead_name":          {"type": "String",           "display": "Lead Name"},
            "hubspot_owner_id":   {"type": "String",           "display": "Owner ID"},
            "owner_name":         {"type": "String",           "display": "Owner Name"},
            "hs_pipeline":        {"type": "LowCardinality(String)", "display": "Lead Pipeline ID"},
            "pipeline_label":     {"type": "LowCardinality(String)", "display": "Lead Pipeline"},
            "hs_pipeline_stage":  {"type": "LowCardinality(String)", "display": "Lead Pipeline Stage ID"},
            "stage_label":        {"type": "LowCardinality(String)", "display": "Lead Stage"},
            "hs_lead_status":     {"type": "LowCardinality(String)", "display": "Lead Status (currently unused)"},
            "hs_lead_type":       {"type": "LowCardinality(String)", "display": "Lead Type"},
            "createdate":         {"type": "DateTime",         "display": "Created Date"},
            "date_entered_current_stage": {"type": "DateTime", "display": "Date Entered Current Stage"},
            "days_in_current_stage": {"type": "Nullable(UInt32)", "display": "Days in Current Stage"},
            "days_since_creation": {"type": "UInt32",          "display": "Days Since Creation"},
            "days_since_last_engagement": {"type": "Nullable(UInt32)", "display": "Days Since Last Engagement"},
            "has_outreach":       {"type": "UInt8",            "display": "Has Outreach"},
            "days_to_first_outreach": {"type": "Nullable(UInt32)", "display": "Days to First Outreach"},
            "has_associated_deal": {"type": "UInt8",           "display": "Has Deal"},
            "is_stale":           {"type": "UInt8",            "display": "Is Stale"},
        },
    },
    "agg_deal_cohorts": {
        "primary_key": "cohort_month",
        "display_name": "Deal Cohorts (creation-month cohort analysis)",
        "database": "gold",
        "fields": {
            "pipeline":           {"type": "LowCardinality(String)", "display": "Pipeline"},
            "deal_origin":        {"type": "LowCardinality(String)", "display": "Deal Origin"},
            "deals_created":      {"type": "UInt32",           "display": "Deals Created"},
            "deals_won":          {"type": "UInt32",           "display": "Deals Won"},
            "deals_lost":         {"type": "UInt32",           "display": "Deals Lost"},
            "deals_still_open":   {"type": "UInt32",           "display": "Still Open"},
            "total_created_value": {"type": "Nullable(Float64)", "display": "Created Value"},
            "total_won_value":    {"type": "Nullable(Float64)", "display": "Won Value"},
            "avg_days_to_close":  {"type": "Nullable(Float64)", "display": "Avg Days to Close"},
        },
    },
}


# Table metadata: primary key, display name, filterable fields.
# Silver tables derive their field list from silver_config (single source of truth).
TABLES: dict[str, dict] = {
    **_derive_silver_tables(),
    **_HANDROLLED_SILVER,
    **_GOLD_TABLES,
}


def rebuild_tables() -> None:
    """Re-derive ``TABLES`` from the current customer config, in place.

    The Settings UI can add or remove silver columns at runtime; without this the
    catalog (and everything downstream of it — the schema prompt, the SQL
    validator, /api/v1/schema) would keep describing the column list captured at
    import time until the process restarted.

    ``TABLES`` is mutated in place rather than rebound because callers import the
    dict object itself (``from app.config import TABLES``). Additions land before
    removals so a concurrent reader never sees a table missing — worst case it
    briefly sees a stale entry.
    """
    silver_config.recompose_columns()
    fresh = {
        **_derive_silver_tables(),
        **_HANDROLLED_SILVER,
        **_GOLD_TABLES,
    }
    TABLES.update(fresh)
    for stale in [name for name in TABLES if name not in fresh]:
        del TABLES[stale]
