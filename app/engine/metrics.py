"""Computed metrics registry — named business metrics with SQL expressions.

Each metric is a pre-validated SQL expression that can be wrapped with
the standard WHERE clause from the propagator.
"""

COMPUTED_METRICS = {
    "win_rate": {
        "label": "Win Rate",
        "format": "percent",
        "table": "dim_deals",
        "sql": (
            "countIf(hs_is_closed_won = 'true') * 1.0 / "
            "nullIf(countIf(hs_is_closed = 'true'), 0)"
        ),
    },
    "weighted_pipeline": {
        "label": "Weighted Pipeline",
        "format": "currency",
        "table": "dim_deals",
        "sql": "sum(amount * hs_deal_stage_probability / 100)",
    },
    "avg_deal_size": {
        "label": "Avg Deal Size",
        "format": "currency",
        "table": "dim_deals",
        "sql": "avgIf(amount, hs_is_closed_won = 'true' AND amount > 0)",
    },
    "avg_days_to_close": {
        "label": "Avg Days to Close",
        "format": "number",
        "table": "dim_deals",
        "sql": "avgIf(days_to_close, hs_is_closed_won = 'true' AND days_to_close > 0)",
    },
    "total_arr_closed": {
        "label": "Total ARR Closed",
        "format": "currency",
        "table": "dim_deals",
        # `{canonical_amount_col}` is interpolated at prompt-build time from
        # customer_config.canonical_amount_col. Defaults to 'amount' on fresh portals.
        "sql": "sumIf({canonical_amount_col}, hs_is_closed_won = 'true')",
    },
    "pipeline_value": {
        "label": "Open Pipeline Value",
        "format": "currency",
        "table": "dim_deals",
        "sql": "sumIf(amount, hs_is_closed = 'false' OR hs_is_closed = '')",
    },
    "new_logo_count": {
        "label": "New Logos Won",
        "format": "number",
        "table": "dim_deals",
        "sql": "countIf(hs_is_closed_won = 'true' AND new_logo != '')",
    },
    "deals_missing_amount": {
        "label": "Deals Missing Amount",
        "format": "number",
        "table": "dim_deals",
        "sql": "countIf(amount IS NULL OR amount = 0)",
    },
    "contacts_missing_email": {
        "label": "Contacts Missing Email",
        "format": "number",
        "table": "dim_contacts",
        "sql": "countIf(email = '')",
    },
    "lead_conversion_rate": {
        "label": "Lead Conversion Rate",
        "format": "percent",
        "table": "dim_leads",
        "sql": (
            "countIf(associated_deals != '') * 1.0 / "
            "nullIf(count(), 0)"
        ),
    },
    "leads_without_outreach": {
        "label": "Leads Without Outreach",
        "format": "number",
        "table": "dim_leads",
        "sql": "countIf(first_outreach_date = '1970-01-01 00:00:00')",
    },
    "total_leads": {
        "label": "Total Leads",
        "format": "number",
        "table": "dim_leads",
        "sql": "count()",
    },
    "total_mqls": {
        "label": "Total MQLs",
        "format": "number",
        "table": "dim_contacts",
        "sql": "countIf(hs_v2_date_entered_marketingqualifiedlead != toDateTime(0))",
    },
    "total_sqls": {
        "label": "Total SQLs",
        "format": "number",
        "table": "dim_contacts",
        "sql": "countIf(hs_v2_date_entered_salesqualifiedlead != toDateTime(0))",
    },
    "mql_to_sql_rate": {
        "label": "MQL → SQL Rate",
        "format": "percent",
        "table": "dim_contacts",
        "sql": (
            "countIf(hs_v2_date_entered_salesqualifiedlead != toDateTime(0)) * 1.0 / "
            "nullIf(countIf(hs_v2_date_entered_marketingqualifiedlead != toDateTime(0)), 0)"
        ),
    },
    "total_deals_closed_won": {
        "label": "Deals Closed Won",
        "format": "number",
        "table": "dim_deals",
        "sql": "countIf(hs_is_closed_won = 'true')",
    },
    "total_deals_closed_lost": {
        "label": "Deals Closed Lost",
        "format": "number",
        "table": "dim_deals",
        "sql": "countIf(hs_is_closed_won = 'false' AND hs_is_closed = 'true')",
    },
    "total_closed_won_amount": {
        "label": "Total Closed Won Amount",
        "format": "currency",
        "table": "dim_deals",
        "sql": "sumIf(amount, hs_is_closed_won = 'true')",
    },
    "forecast_commit": {
        "label": "Forecast Commit",
        "format": "currency",
        "table": "dim_deals",
        "sql": "sumIf(amount, hs_manual_forecast_category = 'COMMIT')",
    },
    "forecast_best_case": {
        "label": "Forecast Best Case",
        "format": "currency",
        "table": "dim_deals",
        "sql": "sumIf(amount, hs_manual_forecast_category IN ('COMMIT', 'BEST_CASE', 'MOST_LIKELY'))",
    },
    "total_open_deals": {
        "label": "Open Deals",
        "format": "number",
        "table": "dim_deals",
        "sql": "countIf(hs_is_closed = 'false' OR hs_is_closed = '')",
    },
    "total_activities": {
        "label": "Total Activities",
        "format": "number",
        "table": "fact_activities",
        "sql": "count()",
    },
}
