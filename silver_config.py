# Silver layer field selection config — single source of truth.
# Each dim is a dict with a column list.
# (silver_column_name, bronze_property_key, clickhouse_type)
# To add a property: add a tuple. To remove: delete the tuple.
#
# Two extension paths:
#   1. NEW (preferred): per-portal extras + removals live in
#      ~/.clickspot/customer.json under extraction.silver_properties.<dim>.
#      The Settings → Properties tab edits this. See app/customer/extraction.py.
#   2. LEGACY: a sibling file `silver_config_custom.py` (gitignored). If it
#      exists, its EXTRA_DIM_DEALS / EXTRA_DIM_CONTACTS lists are appended for
#      one release of backward compatibility (with a deprecation warning).

import logging as _logging
_log = _logging.getLogger("silver_config")


def _load_legacy_extras():
    legacy_deals: list = []
    legacy_contacts: list = []
    try:
        from silver_config_custom import EXTRA_DIM_DEALS as legacy_deals  # type: ignore[import]
        _log.warning(
            "silver_config_custom.py is deprecated. Migrate EXTRA_DIM_DEALS to "
            "the Settings → Properties tab (writes to ~/.clickspot/customer.json)."
        )
    except ImportError:
        pass
    try:
        from silver_config_custom import EXTRA_DIM_CONTACTS as legacy_contacts  # type: ignore[import]
        _log.warning(
            "silver_config_custom.py is deprecated. Migrate EXTRA_DIM_CONTACTS to "
            "the Settings → Properties tab."
        )
    except ImportError:
        pass
    return list(legacy_deals), list(legacy_contacts)


_LEGACY_DEALS, _LEGACY_CONTACTS = _load_legacy_extras()


def _user_extras(dim_name: str):
    """Look up extras + removed-property-keys for a dim from customer.json.

    Falls back to empty lists if app.customer.extraction can't be imported
    (e.g. during early Dagster bootstrap before app/ is on sys.path).
    """
    try:
        from app.customer import extraction
        extras, removed = extraction.get_silver_column_overrides(dim_name)
        return extras, set(removed)
    except Exception:
        return [], set()


def _compose_columns(core: list, dim_name: str, legacy: list) -> list:
    """Merge core silver columns with user extras and apply removals.

    Order: core (with removals applied) → legacy (deprecated) → user extras.
    Duplicate column names from extras silently overwrite earlier entries.
    """
    extras, removed = _user_extras(dim_name)
    out = [t for t in core if t[0] not in removed]
    out += legacy
    seen = {t[0] for t in out}
    for tup in extras:
        if tup[0] in seen:
            # Replace existing entry with the user-supplied one
            out = [(c, p, ty) for c, p, ty in out if c != tup[0]]
        out.append(tup)
        seen.add(tup[0])
    return out


# Dims whose column list is user-extensible, keyed by silver table name. Each
# entry holds the dim dict itself, its pristine core column list, and the legacy
# extras appended for that dim. Kept so the composition can be re-run after the
# Settings UI writes a new selection — see `recompose_columns()`.
_COMPOSABLE: dict[str, tuple[dict, list, list]] = {}


def _compose_into(dim: dict, dim_name: str, legacy: list) -> None:
    """Register `dim` as user-extensible and compose its columns for the first time."""
    core = list(dim["columns"])
    _COMPOSABLE[dim_name] = (dim, core, legacy)
    dim["columns"] = _compose_columns(core, dim_name, legacy)


def recompose_columns() -> None:
    """Re-derive every user-extensible dim's columns from the current customer config.

    Called after the Settings UI saves a new property selection so long-running
    processes pick it up without a restart. Composition always starts from the
    pristine core list, never from the previously composed one, so removals and
    replacements do not accumulate across calls. Each dim's list is swapped in a
    single assignment, so a concurrent reader sees either the old list or the new
    one, never a half-built one.
    """
    for dim_name, (dim, core, legacy) in _COMPOSABLE.items():
        dim["columns"] = _compose_columns(core, dim_name, legacy)


_EXTRA_DIM_DEALS: list = []  # placeholder; actual merge happens via _compose_into below
_EXTRA_DIM_CONTACTS: list = []

DIM_CONTACTS = {
    "bronze_table": "hs_contacts",
    "primary_key": "contact_id",
    "order_by": "(archived, lifecyclestage, toDate(createdate), contact_id)",
    "partition_by": "toYYYYMM(toDate(createdate))",
    "indexes": [
        "INDEX idx_email email TYPE bloom_filter(0.01) GRANULARITY 4",
    ],
    "columns": [
        ("full_name",                                 "full_name",                                 "String"),
        ("email",                                     "email",                                     "String"),
        ("jobtitle",                                  "jobtitle",                                  "String"),
        ("hs_v2_date_entered_salesqualifiedlead",     "hs_v2_date_entered_salesqualifiedlead",     "DateTime"),
        ("hs_v2_date_entered_marketingqualifiedlead", "hs_v2_date_entered_marketingqualifiedlead", "DateTime"),
        ("hs_analytics_source",                       "hs_analytics_source",                       "LowCardinality(String)"),
        ("hs_analytics_source_data_1",                "hs_analytics_source_data_1",                "String"),
        ("hs_analytics_source_data_2",                "hs_analytics_source_data_2",                "String"),
        ("hs_object_source_label",                    "hs_object_source_label",                    "LowCardinality(String)"),
        ("lifecyclestage",                            "lifecyclestage",                            "LowCardinality(String)"),
        ("createdate",                                "createdate",                                "DateTime"),
        ("hs_analytics_first_timestamp",              "hs_analytics_first_timestamp",              "DateTime"),
        # Conversion dates
        ("first_conversion_date",                     "first_conversion_date",                     "DateTime"),
        ("recent_conversion_date",                    "recent_conversion_date",                    "DateTime"),
        ("first_deal_created_date",                   "first_deal_created_date",                   "DateTime"),
        ("closedate",                                 "closedate",                                 "DateTime"),
        # Analytics timestamps
        ("hs_analytics_first_visit_timestamp",        "hs_analytics_first_visit_timestamp",        "DateTime"),
        ("hs_analytics_last_timestamp",               "hs_analytics_last_timestamp",               "DateTime"),
        ("hs_analytics_last_visit_timestamp",         "hs_analytics_last_visit_timestamp",         "DateTime"),
        ("hs_latest_source_timestamp",                "hs_latest_source_timestamp",                "DateTime"),
        # Sales activity
        ("hs_last_sales_activity_date",               "hs_last_sales_activity_date",               "DateTime"),
        ("hs_last_sales_activity_timestamp",          "hs_last_sales_activity_timestamp",          "DateTime"),
        ("hs_last_sales_activity_type",               "hs_last_sales_activity_type",               "LowCardinality(String)"),
        ("hs_sa_first_engagement_date",               "hs_sa_first_engagement_date",               "DateTime"),
        ("first_outreach_date",                       "hs_first_outreach_date",                    "DateTime"),
        # Email activity
        ("hs_email_first_send_date",                  "hs_email_first_send_date",                  "DateTime"),
        ("hs_email_last_send_date",                   "hs_email_last_send_date",                   "DateTime"),
        ("hs_email_first_open_date",                  "hs_email_first_open_date",                  "DateTime"),
        ("hs_email_last_open_date",                   "hs_email_last_open_date",                   "DateTime"),
        ("hs_email_first_click_date",                 "hs_email_first_click_date",                 "DateTime"),
        ("hs_email_last_click_date",                  "hs_email_last_click_date",                  "DateTime"),
        # Sequences
        ("hs_latest_sequence_enrolled_date",          "hs_latest_sequence_enrolled_date",          "DateTime"),
        ("hs_latest_sequence_ended_date",             "hs_latest_sequence_ended_date",             "DateTime"),
        ("hs_latest_sequence_finished_date",          "hs_latest_sequence_finished_date",          "DateTime"),
        ("hs_latest_sequence_unenrolled_date",        "hs_latest_sequence_unenrolled_date",        "DateTime"),
        # Lead dates
        ("hs_latest_open_lead_date",                  "hs_latest_open_lead_date",                  "DateTime"),
        ("hs_latest_qualified_lead_date",             "hs_latest_qualified_lead_date",             "DateTime"),
        ("hs_latest_disqualified_lead_date",          "hs_latest_disqualified_lead_date",          "DateTime"),
        # Notes / next activity
        ("notes_last_updated",                        "notes_last_updated",                        "DateTime"),
        ("notes_next_activity_date",                  "notes_next_activity_date",                  "DateTime"),
        ("hs_notes_next_activity_type",               "hs_notes_next_activity_type",               "LowCardinality(String)"),
        # Owner
        ("hubspot_owner_id",                          "hubspot_owner_id",                          "String"),
        ("hubspot_owner_assigneddate",                "hubspot_owner_assigneddate",                "DateTime"),
        ("recent_deal_close_date",                    "recent_deal_close_date",                    "DateTime"),
    ],
}
_compose_into(DIM_CONTACTS, "dim_contacts", _LEGACY_CONTACTS)

DIM_COMPANIES = {
    "bronze_table": "hs_companies",
    "primary_key": "company_id",
    "order_by": "(archived, toDate(createdate), company_id)",
    "partition_by": "toYYYYMM(toDate(createdate))",
    "columns": [
        ("name",                "name",                "String"),
        ("description",         "description",         "String"),
        ("domain",              "domain",              "String"),
        ("website",             "website",              "String"),
        ("phone",               "phone",               "String"),
        ("address",             "address",              "String"),
        ("city",                "city",                "String"),
        ("country",             "country",              "LowCardinality(String)"),
        ("zip",                 "zip",                 "String"),
        ("industry",            "industry",             "LowCardinality(String)"),
        ("is_public",           "is_public",            "LowCardinality(String)"),
        ("numberofemployees",   "numberofemployees",    "String"),
        ("annualrevenue",       "annualrevenue",        "String"),
        ("lifecyclestage",      "lifecyclestage",       "LowCardinality(String)"),
        ("type",                "type",                "LowCardinality(String)"),
        ("hubspot_owner_id",    "hubspot_owner_id",     "String"),
        ("hs_object_id",        "hs_object_id",         "String"),
        ("createdate",          "createdate",           "DateTime"),
        ("hs_lastmodifieddate", "hs_lastmodifieddate",  "DateTime"),
        ("notes_last_updated",  "notes_last_updated",   "DateTime"),
        # Contact/deal dates
        ("first_contact_createdate",             "first_contact_createdate",             "DateTime"),
        ("first_deal_created_date",              "first_deal_created_date",              "DateTime"),
        ("first_conversion_date",                "first_conversion_date",                "DateTime"),
        ("recent_conversion_date",               "recent_conversion_date",               "DateTime"),
        ("closedate",                            "closedate",                            "DateTime"),
        ("recent_deal_close_date",               "recent_deal_close_date",               "DateTime"),
        # Analytics timestamps
        ("hs_analytics_first_timestamp",         "hs_analytics_first_timestamp",         "DateTime"),
        ("hs_analytics_first_visit_timestamp",   "hs_analytics_first_visit_timestamp",   "DateTime"),
        ("hs_analytics_last_timestamp",          "hs_analytics_last_timestamp",          "DateTime"),
        ("hs_analytics_last_visit_timestamp",    "hs_analytics_last_visit_timestamp",    "DateTime"),
        ("hs_analytics_latest_source_timestamp", "hs_analytics_latest_source_timestamp", "DateTime"),
        # Sales activity
        ("hs_last_sales_activity_date",          "hs_last_sales_activity_date",          "DateTime"),
        ("hs_last_sales_activity_timestamp",     "hs_last_sales_activity_timestamp",     "DateTime"),
        ("hs_last_sales_activity_type",          "hs_last_sales_activity_type",          "LowCardinality(String)"),
        ("hs_last_booked_meeting_date",          "hs_last_booked_meeting_date",          "DateTime"),
        ("hs_last_logged_call_date",             "hs_last_logged_call_date",             "DateTime"),
        ("hs_last_logged_outgoing_email_date",   "hs_last_logged_outgoing_email_date",   "DateTime"),
        ("hs_last_open_task_date",               "hs_last_open_task_date",               "DateTime"),
        # Notes / next activity
        ("notes_next_activity_date",             "notes_next_activity_date",             "DateTime"),
        ("hs_notes_next_activity_type",          "hs_notes_next_activity_type",          "LowCardinality(String)"),
        # Owner
        ("hubspot_owner_assigneddate",           "hubspot_owner_assigneddate",           "DateTime"),
    ],
}
_compose_into(DIM_COMPANIES, "dim_companies", [])

DIM_DEALS = {
    "bronze_table": "hs_deals",
    "primary_key": "deal_id",
    "order_by": "(pipeline, archived, toDate(closedate), deal_id)",
    # Partition on createdate (bounded) — closedate has 1970/2106 sentinel values that
    # would explode into hundreds of partitions.
    "partition_by": "toYYYYMM(toDate(createdate))",
    "indexes": [
        "INDEX idx_owner hubspot_owner_id TYPE bloom_filter(0.01) GRANULARITY 4",
    ],
    "columns": [
        ("dealname",                          "dealname",                          "String"),
        ("dealstage",                         "dealstage",                         "LowCardinality(String)"),
        ("pipeline",                          "pipeline",                          "LowCardinality(String)"),
        ("hubspot_owner_id",                  "hubspot_owner_id",                  "String"),
        ("hubspot_team_id",                   "hubspot_team_id",                   "String"),
        ("company_name",                      "company_name",                      "String"),
        ("amount",                            "amount",                            "Nullable(Float64)"),
        ("deal_currency_code",                "deal_currency_code",                "LowCardinality(String)"),
        ("hs_exchange_rate",                  "hs_exchange_rate",                  "Nullable(Float64)"),
        ("hs_forecast_amount",                "hs_forecast_amount",                "Nullable(Float64)"),
        ("hs_projected_amount",               "hs_projected_amount",               "Nullable(Float64)"),
        ("hs_deal_score",                     "hs_deal_score",                     "Nullable(Float64)"),
        ("hs_deal_stage_probability",         "hs_deal_stage_probability",         "Nullable(Float64)"),
        ("hs_forecast_probability",           "hs_forecast_probability",           "Nullable(Float64)"),
        ("hs_manual_forecast_category",       "hs_manual_forecast_category",       "LowCardinality(String)"),
        ("start_of_term",                     "start_of_term",                     "DateTime"),
        ("closedate",                         "closedate",                         "DateTime"),
        ("days_to_close",                     "days_to_close",                     "Nullable(Float64)"),
        ("hs_v2_date_entered_closedwon",              "hs_v2_date_entered_closedwon",              "DateTime"),
        ("hs_v2_date_entered_closedlost",             "hs_v2_date_entered_closedlost",             "DateTime"),
        ("hs_v2_date_entered_contractsent",           "hs_v2_date_entered_contractsent",           "DateTime"),
        ("hs_v2_date_entered_qualifiedtobuy",         "hs_v2_date_entered_qualifiedtobuy",         "DateTime"),
        ("hs_v2_date_entered_decisionmakerboughtin",  "hs_v2_date_entered_decisionmakerboughtin",  "DateTime"),
        ("hs_v2_date_entered_presentationscheduled",  "hs_v2_date_entered_presentationscheduled",  "DateTime"),
        ("closedlost_reason",                 "closedlost_reason",                 "LowCardinality(String)"),
        ("won_reason",                        "won_reason",                        "LowCardinality(String)"),
        ("hs_object_id",                      "hs_object_id",                      "String"),
        ("createdate",                        "createdate",                        "DateTime"),
        ("hs_lastmodifieddate",               "hs_lastmodifieddate",               "DateTime"),
        ("notes_last_updated",                "notes_last_updated",                "DateTime"),
        ("hs_is_closed_won",                  "hs_is_closed_won",                  "LowCardinality(String)"),
        ("hs_is_closed",                      "hs_is_closed",                      "LowCardinality(String)"),
        # Additional deal dates
        ("hs_closed_deal_close_date",         "hs_closed_deal_close_date",         "DateTime"),
        ("hs_closed_deal_create_date",        "hs_closed_deal_create_date",        "DateTime"),
        ("hs_closed_won_date",                "hs_closed_won_date",                "DateTime"),
        ("hs_open_deal_create_date",          "hs_open_deal_create_date",          "DateTime"),
        # Analytics timestamps
        ("hs_analytics_latest_source_timestamp",         "hs_analytics_latest_source_timestamp",         "DateTime"),
        ("hs_analytics_latest_source_timestamp_company", "hs_analytics_latest_source_timestamp_company", "DateTime"),
        ("hs_analytics_latest_source_timestamp_contact", "hs_analytics_latest_source_timestamp_contact", "DateTime"),
        # Sales email activity
        ("hs_latest_marketing_email_open_date",   "hs_latest_marketing_email_open_date",   "DateTime"),
        ("hs_latest_marketing_email_click_date",  "hs_latest_marketing_email_click_date",  "DateTime"),
        ("hs_latest_sales_email_open_date",       "hs_latest_sales_email_open_date",       "DateTime"),
        ("hs_latest_sales_email_reply_date",      "hs_latest_sales_email_reply_date",      "DateTime"),
        # Stalled / next step
        ("hs_is_stalled_after_timestamp",     "hs_is_stalled_after_timestamp",     "DateTime"),
        ("hs_next_step_updated_at",           "hs_next_step_updated_at",           "DateTime"),
        # Notes / next activity
        ("notes_next_activity_date",          "notes_next_activity_date",          "DateTime"),
        ("hs_notes_next_activity_type",       "hs_notes_next_activity_type",       "LowCardinality(String)"),
        # Owner
        ("hubspot_owner_assigneddate",        "hubspot_owner_assigneddate",        "DateTime"),
    ],
}
_compose_into(DIM_DEALS, "dim_deals", _LEGACY_DEALS)

DIM_LEADS = {
    "bronze_table": "hs_leads",
    "primary_key": "lead_id",
    "order_by": "(archived, hs_pipeline, toDate(createdate), lead_id)",
    "partition_by": "toYYYYMM(toDate(createdate))",
    "indexes": [
        "INDEX idx_owner hubspot_owner_id TYPE bloom_filter(0.01) GRANULARITY 4",
    ],
    "columns": [
        ("hs_lead_name",                  "hs_lead_name",                  "String"),
        ("hubspot_owner_id",              "hubspot_owner_id",              "String"),
        ("created_by_user_id",            "created_by_user_id",            "String"),
        ("hs_pipeline",                   "hs_pipeline",                   "LowCardinality(String)"),
        ("hs_pipeline_stage",              "hs_pipeline_stage",             "LowCardinality(String)"),
        ("hs_lead_status",                "hs_lead_status",                "LowCardinality(String)"),
        ("hs_lead_type",                  "hs_lead_type",                  "LowCardinality(String)"),
        ("disqualification_reason",       "disqualification_reason",       "LowCardinality(String)"),
        ("hs_lead_call_count",            "hs_lead_call_count",            "Nullable(Float64)"),
        ("hs_lead_email_count",           "hs_lead_email_count",           "Nullable(Float64)"),
        ("first_outreach_date",           "hs_lead_first_outreach_date",   "DateTime"),
        # Lead-level engagement/activity
        ("last_engagement_date",          "hs_last_engagement_timestamp",  "DateTime"),
        ("last_engagement_type",          "hs_last_engagement_type",       "LowCardinality(String)"),
        ("last_activity_date",            "hs_last_activity_date",         "DateTime"),
        ("next_activity_date",            "hs_next_activity_date",         "DateTime"),
        ("next_activity_type",            "hs_next_activity_type",         "LowCardinality(String)"),
        ("last_webpage_visit",            "hs_last_webpage_visit_timestamp", "DateTime"),
        # Contact-level (inherited from associated contact)
        ("contact_last_activity_date",    "hs_contact_last_activity_date", "DateTime"),
        ("contact_last_engagement_date",  "hs_contact_last_engagement_timestamp", "DateTime"),
        ("contact_last_engagement_type",  "hs_contact_last_engagement_type", "LowCardinality(String)"),
        ("contact_last_webpage_visit",    "hs_contact_last_webpage_visit_timestamp", "DateTime"),
        ("contact_next_activity_date",    "hs_contact_next_activity_date", "DateTime"),
        ("contact_next_activity_type",    "hs_contact_next_activity_type", "LowCardinality(String)"),
        # Company-level (inherited from associated company)
        ("company_last_activity_date",    "hs_company_last_activity_date", "DateTime"),
        ("company_last_engagement_date",  "hs_company_last_engagement_timestamp", "DateTime"),
        ("company_last_engagement_type",  "hs_company_last_engagement_type", "LowCardinality(String)"),
        ("company_last_webpage_visit",    "hs_company_last_webpage_visit_timestamp", "DateTime"),
        ("company_next_activity_date",    "hs_company_next_activity_date", "DateTime"),
        ("company_next_activity_type",    "hs_company_next_activity_type", "LowCardinality(String)"),
        # Pipeline/ownership timestamps
        ("pipeline_stage_last_updated",   "hs_pipeline_stage_last_updated", "DateTime"),
        ("owner_assigned_date",           "hubspot_owner_assigneddate",    "DateTime"),
        ("associated_deals",              "associated_deals",              "String"),
        ("closed_won_deal_amount",        "closed_won_deal_amount",        "Nullable(Float64)"),
        ("date_entered_current_stage",    "hs_v2_date_entered_current_stage", "DateTime"),
        ("createdate",                    "hs_createdate",                 "DateTime"),
    ],
}
_compose_into(DIM_LEADS, "dim_leads", [])

# Owners -- flat structure from /crm/v3/owners (no properties map)
DIM_OWNERS = {
    "bronze_table": "hs_owners",
    "primary_key": "owner_id",
    "source": "json",  # extract from _raw, not properties map
    "columns": [
        ("email",                      "email",                      "String"),
        ("type",                       "type",                       "LowCardinality(String)"),
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

# Lists / segments -- flat JSON catalog from /crm/v3/lists/search
DIM_LISTS = {
    "bronze_table": "hs_lists",
    "primary_key": "list_id",
    "source": "json",
    "columns": [
        ("name",               "name",             "String"),
        ("list_type",          "listType",         "LowCardinality(String)"),
        ("processing_type",    "processingType",   "LowCardinality(String)"),
        ("object_type_id",     "objectTypeId",     "LowCardinality(String)"),
        ("processing_status",  "processingStatus", "LowCardinality(String)"),
        ("created_by_id",      "createdById",      "String"),
        ("updated_by_id",      "updatedById",      "String"),
        ("created_at",         "createdAt",        "DateTime"),
        ("updated_at",         "updatedAt",        "DateTime"),
        ("filters_updated_at", "filtersUpdatedAt", "DateTime"),
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
        ("is_closed",      "LowCardinality(String)"),
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
    # Lists ↔ CRM
    ("bridge_list_contact",    "hs_assoc_list_contact",    "list_id",    "contact_id"),
    ("bridge_list_company",    "hs_assoc_list_company",    "list_id",    "company_id"),
    ("bridge_list_deal",       "hs_assoc_list_deal",       "list_id",    "deal_id"),
    ("bridge_list_lead",       "hs_assoc_list_lead",       "list_id",    "lead_id"),
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
        ("is_closed",      "LowCardinality(String)"),
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
    "order_by": "(form_id, toDate(submitted_at), submission_id)",
    "partition_by": "toYYYYMM(toDate(submitted_at))",
    "columns": [
        ("form_id",       "form_id",       "LowCardinality(String)"),
        ("form_name",     "form_name",     "LowCardinality(String)"),
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

DICT_CONFIGS = {
    "dim_owners": {
        "description": "Sales rep / owner lookup",
        "keys": [("owner_id", "String")],
        "values": [
            ("first_name", "String", "Owner first name"),
            ("last_name",  "String", "Owner last name"),
            ("email",      "String", "Owner email"),
        ],
        "used_by": {
            "dim_deals":     {"owner_id": "hubspot_owner_id"},
            "dim_contacts":  {"owner_id": "hubspot_owner_id"},
            "dim_leads":     {"owner_id": "hubspot_owner_id"},
            "dim_companies": {"owner_id": "hubspot_owner_id"},
            "agg_rep_performance": {"owner_id": "hubspot_owner_id"},
            "agg_deal_health":     {"owner_id": "hubspot_owner_id"},
            "agg_lead_health":     {"owner_id": "hubspot_owner_id"},
        },
        "patterns": {
            "full_name": "concat(dictGet('{dict}', 'first_name', {keys}), ' ', dictGet('{dict}', 'last_name', {keys}))",
        },
    },
    "dim_pipelines": {
        "description": "Deal pipeline lookup (deal pipelines)",
        "keys": [("pipeline_id", "String")],
        "values": [("label", "String", "Pipeline name")],
        "used_by": {
            "dim_deals":         {"pipeline_id": "pipeline"},
            "agg_deal_health":   {"pipeline_id": "pipeline"},
            "agg_deal_cohorts":  {"pipeline_id": "pipeline"},
        },
    },
    "dim_pipeline_stages": {
        "description": "Deal pipeline stage lookup",
        "keys": [("stage_id", "String")],
        "values": [
            ("label",         "String", "Stage name (German)"),
            ("pipeline_id",   "String", "Which pipeline this stage belongs to"),
            ("is_closed",     "String", "'true'/'false' whether stage is terminal"),
            ("display_order", "UInt32", "Stage sort order"),
        ],
        "used_by": {
            "dim_deals":            {"stage_id": "dealstage"},
            "agg_deal_health":      {"stage_id": "dealstage"},
            "agg_deal_stage_funnel": {"stage_id": "dealstage"},
        },
    },
    "dim_contacts": {
        "description": "Contact lookup",
        "keys": [("contact_id", "String")],
        "values": [
            ("full_name", "String", "Contact full name"),
            ("email",     "String", "Contact email"),
        ],
        "used_by": {
            "bridge_contact_deal":    {"contact_id": "contact_id"},
            "bridge_contact_company": {"contact_id": "contact_id"},
            "bridge_lead_contact":    {"contact_id": "contact_id"},
            "bridge_activity_contact": {"contact_id": "contact_id"},
        },
    },
    "dim_companies": {
        "description": "Company lookup",
        "keys": [("company_id", "String")],
        "values": [
            ("name",     "String", "Company name"),
            ("domain",   "String", "Website domain"),
            ("industry", "String", "Industry classification"),
        ],
        "used_by": {
            "bridge_contact_company":  {"company_id": "company_id"},
            "bridge_deal_company":     {"company_id": "company_id"},
            "bridge_lead_company":     {"company_id": "company_id"},
            "bridge_activity_company": {"company_id": "company_id"},
        },
    },
    "dim_deals": {
        "description": "Deal lookup",
        "keys": [("deal_id", "String")],
        "values": [
            ("dealname",   "String",           "Deal name"),
            ("amount",     "Nullable(Float64)", "Deal value in EUR"),
            ("owner_name", "String",            "Deal owner full name"),
        ],
        "used_by": {
            "bridge_contact_deal":  {"deal_id": "deal_id"},
            "bridge_deal_company":  {"deal_id": "deal_id"},
            "bridge_deal_lead":     {"deal_id": "deal_id"},
            "bridge_activity_deal": {"deal_id": "deal_id"},
        },
    },
    "dim_lead_pipelines": {
        "description": "Lead pipeline lookup",
        "keys": [("pipeline_id", "String")],
        "values": [("label", "String", "Lead pipeline name")],
        "used_by": {
            "dim_leads":       {"pipeline_id": "hs_pipeline"},
            "agg_lead_health": {"pipeline_id": "hs_pipeline"},
        },
    },
    "dim_lists": {
        "description": "HubSpot list / segment metadata lookup",
        "keys": [("list_id", "String")],
        "values": [
            ("name",           "String", "List/segment name"),
            ("list_type",      "String", "STATIC | DYNAMIC"),
            ("object_type_id", "String", "Member object type (0-1 contacts, 0-2 companies, 0-3 deals, 0-136 leads)"),
        ],
        "used_by": {
            "bridge_list_contact": {"list_id": "list_id"},
            "bridge_list_company": {"list_id": "list_id"},
            "bridge_list_deal":    {"list_id": "list_id"},
            "bridge_list_lead":    {"list_id": "list_id"},
        },
    },
    "dim_lead_pipeline_stages": {
        "description": "Lead pipeline stage lookup (composite key: pipeline + stage)",
        "keys": [("pipeline_id", "String"), ("stage_id", "String")],
        "values": [
            ("label",         "String", "Stage name"),
            ("display_order", "UInt32", "Stage sort order"),
            ("is_closed",     "String", "'true'/'false' whether stage is terminal"),
        ],
        "used_by": {
            "dim_leads":       {"pipeline_id": "hs_pipeline", "stage_id": "hs_pipeline_stage"},
            "agg_lead_health": {"pipeline_id": "hs_pipeline", "stage_id": "hs_pipeline_stage"},
        },
    },
}


# ---------------------------------------------------------------------------
# Generate DDL from structured config (keeps DDL and metadata in sync)
# ---------------------------------------------------------------------------

def _build_dict_ddl(table_name: str, config: dict) -> str:
    """Generate CREATE DICTIONARY DDL from structured config."""
    dict_name = "dict_" + table_name.removeprefix("dim_")
    all_cols = []
    for name, ch_type in config["keys"]:
        all_cols.append(f"    {name} {ch_type}")
    for entry in config["values"]:
        name, ch_type = entry[0], entry[1]
        all_cols.append(f"    {name} {ch_type}")
    cols_str = ",\n".join(all_cols)
    pk_names = ", ".join(name for name, _ in config["keys"])
    layout = "COMPLEX_KEY_HASHED()" if len(config["keys"]) > 1 else "HASHED()"
    return f"""CREATE DICTIONARY IF NOT EXISTS silver.{dict_name} (
{cols_str}
) PRIMARY KEY {pk_names}
SOURCE(CLICKHOUSE(DB 'silver' TABLE '{table_name}' WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))
LIFETIME(MIN 300 MAX 600)
LAYOUT({layout})"""


# Computed DDL lookup — backward compatible with silver.py helpers
DICTIONARIES = {name: _build_dict_ddl(name, cfg) for name, cfg in DICT_CONFIGS.items()}


# ---------------------------------------------------------------------------
# Anonymization registry — columns to mask when materializing silver_anon /
# gold_anon copies. Consumed only by assets/silver_anon.py and
# assets/gold_anon.py; the main pipeline ignores this block entirely.
# Kind is one of: "text" | "email" | "phone" (see app/engine/anon_masking.py).
# Tables not listed here are copied column-for-column with no masking.
# dim_owners is intentionally absent — owner data stays visible.
# ---------------------------------------------------------------------------

ANON_PII_COLUMNS: dict[str, list[tuple[str, str]]] = {
    # Silver dims
    "dim_contacts": [
        ("full_name", "text"),
        ("email",     "email"),
        ("jobtitle",  "text"),
    ],
    "dim_companies": [
        ("name",    "text"),
        ("domain",  "text"),
        ("website", "text"),
        ("phone",   "phone"),
        ("address", "text"),
        ("city",    "text"),
        ("zip",     "text"),
    ],
    "dim_deals": [
        ("dealname",     "text"),
        ("company_name", "text"),
    ],
    "dim_leads": [
        ("hs_lead_name", "text"),
    ],
    "dim_lists": [
        # Segment names can leak business strategy ("VIP customers Q3",
        # "Churn risk - Enterprise"). Mask in the anon mirror so MCP
        # clients only see synthetic labels.
        ("name", "text"),
    ],
    "dict_lists": [
        ("name", "text"),
    ],
    # Silver facts
    "fact_form_submissions": [
        ("page_url",   "text"),
        ("email",      "email"),
        ("firstname",  "text"),
        ("lastname",   "text"),
        ("company",    "text"),
        ("jobtitle",   "text"),
        ("phone",      "phone"),
    ],
    # Silver dictionaries (masked at the dict source so dictGet() returns masked values)
    "dict_contacts": [
        ("full_name", "text"),
        ("email",     "email"),
    ],
    "dict_companies": [
        ("name",   "text"),
        ("domain", "text"),
    ],
    "dict_deals": [
        ("dealname", "text"),
    ],
    # Gold aggregates
    "agg_deal_health": [
        ("dealname", "text"),
    ],
    "agg_lead_health": [
        ("lead_name", "text"),
    ],
}
