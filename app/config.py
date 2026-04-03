"""Graph topology and field metadata for the associative analytics engine.

This mirrors the silver_config.py schema but encodes the *relationships*
between tables (bridges, FK joins) and which fields are filterable in the UI.
"""

# Each edge is bidirectional — the engine can traverse in either direction.
GRAPH_EDGES = [
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
        "from": "dim_contacts",
        "to": "fact_activities",
        "bridge": "bridge_activity_contact",
        "from_key": "contact_id",
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
            "hs_analytics_source": {"type": "String",  "display": "Analytics Source"},
            "hs_analytics_source_data_1": {"type": "String", "display": "Source Detail 1"},
            "hs_object_source_label": {"type": "String", "display": "Object Source"},
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
            "hs_manual_forecast_category": {"type": "String", "display": "Forecast Category"},
            "closedlost_reason": {"type": "String",          "display": "Lost Reason"},
            "won_reason":       {"type": "String",           "display": "Won Reason"},
            "partner":          {"type": "String",           "display": "Partner"},
            "renewal":          {"type": "String",           "display": "Renewal"},
            "new_logo":         {"type": "String",           "display": "New Logo"},
        },
    },
    "dim_leads": {
        "primary_key": "lead_id",
        "display_name": "Leads",
        "fields": {
            "hs_lead_status":   {"type": "String",   "display": "Lead Status"},
            "hs_lead_type":     {"type": "String",   "display": "Lead Type"},
            "hubspot_owner_id": {"type": "String",   "display": "Owner ID"},
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
        },
    },
}
