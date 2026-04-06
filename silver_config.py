# Silver layer field selection config — single source of truth.
# Each dim is a dict with a column list.
# (silver_column_name, bronze_property_key, clickhouse_type)
# To add a property: add a tuple. To remove: delete the tuple.

DIM_CONTACTS = {
    "bronze_table": "hs_contacts",
    "primary_key": "contact_id",
    "columns": [
        ("full_name",                                 "full_name",                                 "String"),
        ("email",                                     "email",                                     "String"),
        ("jobtitle",                                  "jobtitle",                                  "String"),
        ("hs_v2_date_entered_salesqualifiedlead",     "hs_v2_date_entered_salesqualifiedlead",     "DateTime"),
        ("hs_v2_date_entered_marketingqualifiedlead", "hs_v2_date_entered_marketingqualifiedlead", "DateTime"),
        ("hs_analytics_source",                       "hs_analytics_source",                       "String"),
        ("hs_analytics_source_data_1",                "hs_analytics_source_data_1",                "String"),
        ("hs_analytics_source_data_2",                "hs_analytics_source_data_2",                "String"),
        ("hs_object_source_label",                    "hs_object_source_label",                    "String"),
        ("lifecyclestage",                            "lifecyclestage",                            "String"),
        ("createdate",                                "createdate",                                "DateTime"),
        ("hs_analytics_first_timestamp",              "hs_analytics_first_timestamp",              "DateTime"),
    ],
}

DIM_COMPANIES = {
    "bronze_table": "hs_companies",
    "primary_key": "company_id",
    "columns": [
        ("name",                "name",                "String"),
        ("description",         "description",         "String"),
        ("domain",              "domain",              "String"),
        ("website",             "website",              "String"),
        ("phone",               "phone",               "String"),
        ("address",             "address",              "String"),
        ("city",                "city",                "String"),
        ("country",             "country",              "String"),
        ("zip",                 "zip",                 "String"),
        ("industry",            "industry",             "String"),
        ("is_public",           "is_public",            "String"),
        ("numberofemployees",   "numberofemployees",    "String"),
        ("annualrevenue",       "annualrevenue",        "String"),
        ("lifecyclestage",      "lifecyclestage",       "String"),
        ("type",                "type",                "String"),
        ("hubspot_owner_id",    "hubspot_owner_id",     "String"),
        ("hs_object_id",        "hs_object_id",         "String"),
        ("createdate",          "createdate",           "DateTime"),
        ("hs_lastmodifieddate", "hs_lastmodifieddate",  "DateTime"),
        ("notes_last_updated",  "notes_last_updated",   "DateTime"),
    ],
}

DIM_DEALS = {
    "bronze_table": "hs_deals",
    "primary_key": "deal_id",
    "columns": [
        ("dealname",                          "dealname",                          "String"),
        ("dealstage",                         "dealstage",                         "String"),
        ("pipeline",                          "pipeline",                          "String"),
        ("hubspot_owner_id",                  "hubspot_owner_id",                  "String"),
        ("hubspot_team_id",                   "hubspot_team_id",                   "String"),
        ("company_name",                      "company_name",                      "String"),
        ("amount",                            "amount",                            "Nullable(Float64)"),
        ("deal_currency_code",                "deal_currency_code",                "String"),
        ("hs_exchange_rate",                  "hs_exchange_rate",                  "Nullable(Float64)"),
        ("hs_forecast_amount",                "hs_forecast_amount",                "Nullable(Float64)"),
        ("hs_projected_amount",               "hs_projected_amount",               "Nullable(Float64)"),
        ("annual_contract_value",            "annual_contract_value",            "Nullable(Float64)"),
        ("total_contract_value",                       "total_contract_value",                       "Nullable(Float64)"),
        ("gross_profit",                  "gross_profit",                  "Nullable(Float64)"),
        ("services_revenue",                 "services_revenue",                 "Nullable(Float64)"),
        ("mrr_average",                     "mrr_average",                     "Nullable(Float64)"),
        ("renewal_revenue",                "renewal_revenue",                "Nullable(Float64)"),
        ("upsell_revenue",                 "upsell_revenue",                 "Nullable(Float64)"),
        ("annual_recurring_revenue",                "annual_recurring_revenue",                "Nullable(Float64)"),
        ("license_margin",                    "license_margin",                    "Nullable(Float64)"),
        ("services_margin",     "services_margin",     "Nullable(Float64)"),
        ("services_days",   "services_days",   "Nullable(Float64)"),
        ("hs_deal_score",                     "hs_deal_score",                     "Nullable(Float64)"),
        ("hs_deal_stage_probability",         "hs_deal_stage_probability",         "Nullable(Float64)"),
        ("fc_probability",                    "fc_probability",                    "Nullable(Float64)"),
        ("hs_forecast_probability",           "hs_forecast_probability",           "Nullable(Float64)"),
        ("hs_manual_forecast_category",       "hs_manual_forecast_category",       "String"),
        ("contract_months",        "contract_months",        "Nullable(Float64)"),
        ("start_of_term",                     "start_of_term",                     "DateTime"),
        ("closedate",                         "closedate",                         "DateTime"),
        ("days_to_close",                     "days_to_close",                     "Nullable(Float64)"),
        ("hs_v2_date_entered_closedwon",              "hs_v2_date_entered_closedwon",              "DateTime"),
        ("hs_v2_date_entered_closedlost",             "hs_v2_date_entered_closedlost",             "DateTime"),
        ("hs_v2_date_entered_contractsent",           "hs_v2_date_entered_contractsent",           "DateTime"),
        ("hs_v2_date_entered_qualifiedtobuy",         "hs_v2_date_entered_qualifiedtobuy",         "DateTime"),
        ("hs_v2_date_entered_decisionmakerboughtin",  "hs_v2_date_entered_decisionmakerboughtin",  "DateTime"),
        ("hs_v2_date_entered_custom_stage",             "hs_v2_date_entered_custom_stage",             "DateTime"),
        ("hs_v2_date_entered_presentationscheduled",  "hs_v2_date_entered_presentationscheduled",  "DateTime"),
        ("closedlost_reason",                 "closedlost_reason",                 "String"),
        ("closedlost_reason_description",     "closedlost_reason_description",     "String"),
        ("won_reason",                        "won_reason",                        "String"),
        ("deal_source_details",               "deal_source_details",               "String"),
        ("partner",                           "partner",                           "String"),
        ("partner_involvement",                   "partner_involvement",                   "String"),
        ("rfi_rfp",                           "rfi_rfp",                           "String"),
        ("renewal",                           "renewal",                           "String"),
        ("new_logo",                          "new_logo",                          "String"),
        ("hs_object_id",                      "hs_object_id",                      "String"),
        ("createdate",                        "createdate",                        "DateTime"),
        ("hs_lastmodifieddate",               "hs_lastmodifieddate",               "DateTime"),
        ("notes_last_updated",                "notes_last_updated",                "DateTime"),
        ("hs_is_closed_won",                  "hs_is_closed_won",                  "String"),
        ("hs_is_closed",                      "hs_is_closed",                      "String"),
    ],
}

DIM_LEADS = {
    "bronze_table": "hs_leads",
    "primary_key": "lead_id",
    "columns": [
        ("hubspot_owner_id",              "hubspot_owner_id",              "String"),
        ("created_by_user_id",            "created_by_user_id",            "String"),
        ("hs_pipeline",                   "hs_pipeline",                   "String"),
        ("hs_lead_status",                "hs_lead_status",                "String"),
        ("hs_lead_type",                  "hs_lead_type",                  "String"),
        ("disqualification_reason",       "disqualification_reason",       "String"),
        ("hs_lead_call_count",            "hs_lead_call_count",            "Nullable(Float64)"),
        ("hs_lead_email_count",           "hs_lead_email_count",           "Nullable(Float64)"),
        ("first_outreach_date",           "first_outreach_date",           "DateTime"),
        ("contact_last_engagement_date",  "contact_last_engagement_date",  "DateTime"),
        ("associated_deals",              "associated_deals",              "String"),
        ("closed_won_deal_amount",        "closed_won_deal_amount",        "Nullable(Float64)"),
        ("createdate",                    "createdate",                    "DateTime"),
    ],
}

# Owners -- flat structure from /crm/v3/owners (no properties map)
DIM_OWNERS = {
    "bronze_table": "hs_owners",
    "primary_key": "owner_id",
    "source": "json",  # extract from _raw, not properties map
    "columns": [
        ("email",                      "email",                      "String"),
        ("type",                       "type",                       "String"),
        ("first_name",                 "firstName",                  "String"),
        ("last_name",                  "lastName",                   "String"),
        ("user_id",                    "userId",                     "String"),
        ("user_id_including_inactive", "userIdIncludingInactive",    "String"),
        ("created_at",                 "createdAt",                  "DateTime"),
        ("updated_at",                 "updatedAt",                  "DateTime"),
    ],
}

# Pipelines -- extracted from /crm/v3/pipelines/deals
DIM_PIPELINES = {
    "bronze_table": "hs_pipelines",
    "primary_key": "pipeline_id",
    "source": "json",
    "columns": [
        ("label",          "label",         "String"),
        ("display_order",  "displayOrder",  "UInt32"),
        ("created_at",     "createdAt",     "DateTime"),
        ("updated_at",     "updatedAt",     "DateTime"),
    ],
}

# Pipeline stages -- flattened from stages[] array nested in pipeline JSON
# Special handling: not a simple property extraction
DIM_PIPELINE_STAGES = {
    "bronze_table": "hs_pipelines",
    "primary_key": "stage_id",
    "source": "nested_stages",  # custom extraction logic
    "columns": [
        ("pipeline_id",    "String"),
        ("label",          "String"),
        ("display_order",  "UInt32"),
        ("is_closed",      "String"),
        ("probability",    "Nullable(Float64)"),
        ("created_at",     "DateTime"),
        ("updated_at",     "DateTime"),
    ],
}

FACT_ACTIVITIES = {
    # Maps activity_type -> {silver_column: bronze_property_key}
    "calls":    {"subject": "hs_call_title",    "disposition": "hs_call_disposition", "duration": "hs_call_duration"},
    "meetings": {"subject": "hs_meeting_title", "disposition": "",                   "duration": "hs_meeting_duration"},
    "emails":   {"subject": "hs_email_subject", "disposition": "",                   "duration": ""},
    "notes":    {"subject": "",                  "disposition": "",                   "duration": ""},
    "tasks":    {"subject": "hs_task_subject",   "disposition": "hs_task_status",     "duration": ""},
}

BRIDGE_TABLES = [
    # (silver_table, bronze_table, from_key, to_key)
    # CRM ↔ CRM
    ("bridge_contact_company", "hs_assoc_contact_company", "contact_id", "company_id"),
    ("bridge_contact_deal",    "hs_assoc_contact_deal",    "contact_id", "deal_id"),
    ("bridge_deal_company",    "hs_assoc_deal_company",    "deal_id",    "company_id"),
    ("bridge_lead_contact",    "hs_assoc_lead_contact",    "lead_id",    "contact_id"),
    ("bridge_deal_lead",       "hs_assoc_deal_lead",       "deal_id",    "lead_id"),
    ("bridge_lead_company",    "hs_assoc_lead_company",    "lead_id",    "company_id"),
]

BRIDGE_ACTIVITY_CONTACT = [
    # (activity_type, bronze_assoc_table)
    ("call",    "hs_assoc_call_contact"),
    ("meeting", "hs_assoc_meeting_contact"),
    ("email",   "hs_assoc_email_contact"),
    ("note",    "hs_assoc_note_contact"),
    ("task",    "hs_assoc_task_contact"),
]

BRIDGE_ACTIVITY_COMPANY = [
    # (activity_type, bronze_assoc_table)
    ("call",    "hs_assoc_call_company"),
    ("meeting", "hs_assoc_meeting_company"),
    ("email",   "hs_assoc_email_company"),
    ("note",    "hs_assoc_note_company"),
    ("task",    "hs_assoc_task_company"),
]

# Lead pipelines -- extracted from /crm/v3/pipelines/leads
DIM_LEAD_PIPELINES = {
    "bronze_table": "hs_lead_pipelines",
    "primary_key": "pipeline_id",
    "source": "json",
    "columns": [
        ("label",          "label",         "String"),
        ("display_order",  "displayOrder",  "UInt32"),
        ("created_at",     "createdAt",     "DateTime"),
        ("updated_at",     "updatedAt",     "DateTime"),
    ],
}

# Lead pipeline stages -- flattened from stages[] array nested in lead pipeline JSON
DIM_LEAD_PIPELINE_STAGES = {
    "bronze_table": "hs_lead_pipelines",
    "primary_key": "stage_id",
    "source": "nested_stages",
    "columns": [
        ("pipeline_id",    "String"),
        ("label",          "String"),
        ("display_order",  "UInt32"),
        ("is_closed",      "String"),
        ("probability",    "Nullable(Float64)"),
        ("created_at",     "DateTime"),
        ("updated_at",     "DateTime"),
    ],
}

BRIDGE_ACTIVITY_DEAL = [
    # (activity_type, bronze_assoc_table)
    ("call",    "hs_assoc_call_deal"),
    ("meeting", "hs_assoc_meeting_deal"),
    ("email",   "hs_assoc_email_deal"),
    ("note",    "hs_assoc_note_deal"),
    ("task",    "hs_assoc_task_deal"),
]

# ---------------------------------------------------------------------------
# Form submissions — flattened from form-integrations/v1 API
# ---------------------------------------------------------------------------

FACT_FORM_SUBMISSIONS = {
    "bronze_table": "hs_form_submissions",
    "primary_key": "submission_id",
    "columns": [
        ("form_id",       "form_id",       "String"),
        ("form_name",     "form_name",     "String"),
        ("submitted_at",  "submitted_at",  "DateTime"),
        ("page_url",      "page_url",      "String"),
        ("email",         "email",         "String"),
        ("firstname",     "firstname",     "String"),
        ("lastname",      "lastname",      "String"),
        ("company",       "company",       "String"),
        ("jobtitle",      "jobtitle",      "String"),
        ("phone",         "phone",         "String"),
    ],
}

# ---------------------------------------------------------------------------
# Dictionaries — in-memory lookups backed by silver tables.
# Maps silver table name → CREATE DICTIONARY DDL.
# These are dropped before table refresh and recreated after.
# ---------------------------------------------------------------------------

DICTIONARIES = {
    "dim_owners": """
CREATE DICTIONARY IF NOT EXISTS silver.dict_owners (
    owner_id String,
    first_name String,
    last_name String,
    email String
) PRIMARY KEY owner_id
SOURCE(CLICKHOUSE(DB 'silver' TABLE 'dim_owners' WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED())
""",
    "dim_pipelines": """
CREATE DICTIONARY IF NOT EXISTS silver.dict_pipelines (
    pipeline_id String,
    label String
) PRIMARY KEY pipeline_id
SOURCE(CLICKHOUSE(DB 'silver' TABLE 'dim_pipelines' WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED())
""",
    "dim_pipeline_stages": """
CREATE DICTIONARY IF NOT EXISTS silver.dict_pipeline_stages (
    stage_id String,
    label String,
    pipeline_id String,
    is_closed String,
    display_order UInt32
) PRIMARY KEY stage_id
SOURCE(CLICKHOUSE(DB 'silver' TABLE 'dim_pipeline_stages' WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED())
""",
    "dim_contacts": """
CREATE DICTIONARY IF NOT EXISTS silver.dict_contacts (
    contact_id String,
    full_name String,
    email String
) PRIMARY KEY contact_id
SOURCE(CLICKHOUSE(DB 'silver' TABLE 'dim_contacts' WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED())
""",
    "dim_companies": """
CREATE DICTIONARY IF NOT EXISTS silver.dict_companies (
    company_id String,
    name String,
    domain String,
    industry String
) PRIMARY KEY company_id
SOURCE(CLICKHOUSE(DB 'silver' TABLE 'dim_companies' WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED())
""",
    "dim_deals": """
CREATE DICTIONARY IF NOT EXISTS silver.dict_deals (
    deal_id String,
    dealname String,
    amount Nullable(Float64),
    owner_name String
) PRIMARY KEY deal_id
SOURCE(CLICKHOUSE(DB 'silver' TABLE 'dim_deals' WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))
LIFETIME(MIN 300 MAX 600)
LAYOUT(COMPLEX_KEY_HASHED())
""",
}
