"""Graph topology and field metadata for the associative analytics engine.

This mirrors the silver_config.py schema but encodes the *relationships*
between tables (bridges, FK joins) and which fields are filterable in the UI.
"""

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
]

# Table metadata: primary key, display name, filterable fields
TABLES = {
    "dim_contacts": {
        "primary_key": "contact_id",
        "display_name": "Contacts",
        "fields": {
            "email":              {"type": "String",   "display": "Email"},
            "full_name":          {"type": "String",   "display": "Full Name"},
            "jobtitle":           {"type": "String",   "display": "Job Title"},
            "lifecyclestage":     {"type": "String",   "display": "Lifecycle Stage"},
            "hs_analytics_source": {"type": "String",  "display": "Analytics Source"},
            "hs_analytics_source_data_1": {"type": "String", "display": "Source Detail 1"},
            "hs_analytics_source_data_2": {"type": "String", "display": "Source Detail 2"},
            "hs_object_source_label": {"type": "String", "display": "Object Source"},
            "createdate":         {"type": "DateTime", "display": "Created"},
            "hs_v2_date_entered_marketingqualifiedlead": {"type": "DateTime", "display": "MQL Date"},
            "hs_v2_date_entered_salesqualifiedlead":     {"type": "DateTime", "display": "SQL Date"},
            "hs_analytics_first_timestamp": {"type": "DateTime", "display": "First Seen"},
        },
    },
    "dim_companies": {
        "primary_key": "company_id",
        "display_name": "Companies",
        "fields": {
            "name":             {"type": "String",   "display": "Company Name"},
            "domain":           {"type": "String",   "display": "Domain"},
            "industry":         {"type": "String",   "display": "Industry"},
            "city":             {"type": "String",   "display": "City"},
            "country":          {"type": "String",   "display": "Country"},
            "lifecyclestage":   {"type": "String",   "display": "Lifecycle Stage"},
            "type":             {"type": "String",   "display": "Type"},
            "numberofemployees": {"type": "String",  "display": "Employees"},
            "annualrevenue":    {"type": "String",   "display": "Annual Revenue"},
            "hubspot_owner_id": {"type": "String",   "display": "Owner ID"},
            "createdate":       {"type": "DateTime", "display": "Created"},
        },
    },
    "dim_deals": {
        "primary_key": "deal_id",
        "display_name": "Deals",
        "fields": {
            "dealname":         {"type": "String",           "display": "Deal Name"},
            "dealstage":        {"type": "String",           "display": "Deal Stage"},
            "pipeline":         {"type": "String",           "display": "Pipeline"},
            "amount":           {"type": "Nullable(Float64)", "display": "Amount"},
            "deal_currency_code": {"type": "String",         "display": "Currency"},
            "hubspot_owner_id": {"type": "String",           "display": "Owner ID"},
            "hubspot_team_id":  {"type": "String",           "display": "Team ID"},
            "hs_manual_forecast_category": {"type": "String", "display": "Forecast Category"},
            "hs_deal_stage_probability": {"type": "Nullable(Float64)", "display": "Stage Probability"},
            "hs_forecast_amount": {"type": "Nullable(Float64)", "display": "Forecast Amount"},
            "annual_contract_value": {"type": "Nullable(Float64)", "display": "First Year ACV"},
            "annual_recurring_revenue": {"type": "Nullable(Float64)", "display": "First Year New ARR"},
            "total_contract_value":      {"type": "Nullable(Float64)", "display": "License TCV"},
            "renewal_revenue": {"type": "Nullable(Float64)", "display": "Renewal TCV"},
            "days_to_close":    {"type": "Nullable(Float64)", "display": "Days to Close"},
            "closedate":        {"type": "DateTime",         "display": "Close Date"},
            "createdate":       {"type": "DateTime",         "display": "Created"},
            "closedlost_reason": {"type": "String",          "display": "Lost Reason"},
            "won_reason":       {"type": "String",           "display": "Won Reason"},
            "partner":          {"type": "String",           "display": "Partner"},
            "renewal":          {"type": "String",           "display": "Renewal"},
            "new_logo":         {"type": "String",           "display": "New Logo"},
            "hs_is_closed_won": {"type": "String",           "display": "Closed Won"},
            "hs_is_closed":     {"type": "String",           "display": "Closed"},
        },
    },
    "dim_leads": {
        "primary_key": "lead_id",
        "display_name": "Leads",
        "fields": {
            "hs_lead_status":   {"type": "String",   "display": "Lead Status"},
            "hs_lead_type":     {"type": "String",   "display": "Lead Type"},
            "hubspot_owner_id": {"type": "String",   "display": "Owner ID"},
            "disqualification_reason": {"type": "String", "display": "Disqualification Reason"},
            "hs_lead_call_count": {"type": "Nullable(Float64)", "display": "Call Count"},
            "hs_lead_email_count": {"type": "Nullable(Float64)", "display": "Email Count"},
            "first_outreach_date": {"type": "DateTime", "display": "First Outreach"},
            "contact_last_engagement_date": {"type": "DateTime", "display": "Last Engagement"},
            "createdate":       {"type": "DateTime", "display": "Created"},
        },
    },
    "dim_pipelines": {
        "primary_key": "pipeline_id",
        "display_name": "Pipelines",
        "fields": {
            "label":            {"type": "String",   "display": "Pipeline Name"},
        },
    },
    "dim_pipeline_stages": {
        "primary_key": "stage_id",
        "display_name": "Pipeline Stages",
        "fields": {
            "label":            {"type": "String",   "display": "Stage Name"},
            "pipeline_id":      {"type": "String",   "display": "Pipeline ID"},
            "is_closed":        {"type": "String",   "display": "Is Closed"},
            "display_order":    {"type": "UInt32",   "display": "Display Order"},
            "probability":      {"type": "Nullable(Float64)", "display": "Probability"},
        },
    },
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
}
