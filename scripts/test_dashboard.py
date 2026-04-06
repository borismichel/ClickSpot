#!/usr/bin/env python3
"""Simulate the frontend dashboard queries against the API and sanity-check results.

Sends the exact same payload the React app sends (from App.tsx), then validates
that every data key each view expects actually exists and has reasonable data.

Usage:
    python scripts/test_dashboard.py [--api http://localhost:8192]
"""

import argparse
import json
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError

# ---------- colours ----------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

ok_count = 0
warn_count = 0
fail_count = 0


def ok(msg):
    global ok_count
    ok_count += 1
    print(f"  {GREEN}OK{RESET}  {msg}")


def warn(msg):
    global warn_count
    warn_count += 1
    print(f"  {YELLOW}WARN{RESET}  {msg}")


def fail(msg):
    global fail_count
    fail_count += 1
    print(f"  {RED}FAIL{RESET}  {msg}")


def section(title):
    print(f"\n{BOLD}{CYAN}{'=' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 60}{RESET}")


def subsection(title):
    print(f"\n  {BOLD}--- {title} ---{RESET}")


def post_json(url, payload):
    data = json.dumps(payload).encode()
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(req) as resp:
        return json.loads(resp.read())


def get_json(url):
    with urlopen(url) as resp:
        return json.loads(resp.read())


def check_metric(metrics, key, label, allow_zero=False, allow_null=False):
    val = metrics.get(key)
    if val is None:
        if allow_null:
            warn(f"{label} ({key}): null (may be expected)")
        else:
            fail(f"{label} ({key}): missing or null")
    elif val == 0 and not allow_zero:
        warn(f"{label} ({key}): 0 (may be expected, but double-check)")
    else:
        ok(f"{label} ({key}): {val:,.2f}" if isinstance(val, float) else f"{label} ({key}): {val}")


def check_grouped(gm, key, label, min_rows=1):
    rows = gm.get(key)
    if rows is None:
        fail(f"{label} ({key}): missing")
        return []
    elif len(rows) == 0:
        warn(f"{label} ({key}): empty (0 rows)")
        return []
    else:
        top3 = rows[:3]
        preview = ", ".join(
            f"{list(r['groups'].values())[0]}={r['value']}" for r in top3
        )
        ok(f"{label} ({key}): {len(rows)} rows — top: {preview}")
        return rows


def check_time_series(ts, key, label, min_points=1):
    points = ts.get(key)
    if points is None:
        fail(f"{label} ({key}): missing")
        return []
    elif len(points) == 0:
        warn(f"{label} ({key}): empty (0 data points)")
        return []
    else:
        first, last = points[0], points[-1]
        ok(f"{label} ({key}): {len(points)} points — {first['period']}..{last['period']}")
        return points


def check_list(lists, key, label, expected_cols=None):
    lst = lists.get(key)
    if lst is None:
        fail(f"{label} ({key}): missing")
        return []
    rows = lst.get("rows", [])
    total = lst.get("total", 0)
    if len(rows) == 0:
        warn(f"{label} ({key}): 0 rows (total={total})")
    else:
        cols = list(rows[0].keys()) if rows else []
        ok(f"{label} ({key}): {len(rows)} rows (total={total}), cols: {cols[:6]}")
        if expected_cols:
            missing = [c for c in expected_cols if c not in cols]
            if missing:
                warn(f"  Missing expected columns: {missing}")
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8192")
    args = parser.parse_args()
    base = args.api.rstrip("/")

    # =============================================
    # 1. Health + Schema + Metadata
    # =============================================
    section("1. API Health & Schema")

    try:
        health = get_json(f"{base}/health")
        ok(f"Health: {health}")
    except URLError as e:
        fail(f"API not reachable at {base}: {e}")
        print(f"\n{RED}Cannot continue without API. Start it with: uvicorn app.main:app --port 8192{RESET}")
        sys.exit(1)

    schema = get_json(f"{base}/api/v1/schema")
    tables = list(schema["tables"].keys())
    ok(f"Schema: {len(tables)} tables — {tables}")
    ok(f"Edges: {len(schema['edges'])} graph edges")

    metadata = get_json(f"{base}/api/v1/metadata")
    subsection("Row counts")
    for t, cnt in metadata["row_counts"].items():
        if cnt == 0:
            warn(f"  {t}: 0 rows")
        else:
            ok(f"  {t}: {cnt:,} rows")

    metrics_catalog = get_json(f"{base}/api/v1/metrics-catalog")
    ok(f"Metrics catalog: {len(metrics_catalog)} metrics — {list(metrics_catalog.keys())}")

    # =============================================
    # 2. Main query (mirrors App.tsx payload)
    # =============================================
    section("2. Main Query (App.tsx payload)")

    payload = {
        "selections": {},
        "counts": True,
        "field_values": [
            f"{t}.{c}"
            for t, meta in schema["tables"].items()
            for c in list(meta["fields"].keys())[:3]  # first 3 fields per table
        ],
        "measures": [
            {"table": "dim_deals", "column": "amount", "agg": "sum"},
            {"table": "dim_deals", "column": "deal_id", "agg": "count"},
            {"table": "fact_activities", "column": "activity_id", "agg": "count"},
        ],
        "grouped_measures": [
            {"table": "dim_deals", "column": "deal_id", "agg": "count", "group_by": ["dealstage"], "limit": 30},
            {"table": "dim_deals", "column": "amount", "agg": "sum", "group_by": ["hs_manual_forecast_category"], "limit": 10},
            {"table": "dim_deals", "column": "deal_id", "agg": "count", "group_by": ["hubspot_owner_id"], "limit": 20},
            {"table": "fact_activities", "column": "activity_id", "agg": "count", "group_by": ["activity_type"], "limit": 10},
            {"table": "dim_leads", "column": "lead_id", "agg": "count", "group_by": ["hs_lead_status"], "limit": 10},
            {"table": "dim_leads", "column": "lead_id", "agg": "count", "group_by": ["disqualification_reason"], "limit": 10},
            {"table": "dim_contacts", "column": "contact_id", "agg": "count", "group_by": ["hs_analytics_source"], "limit": 15},
        ],
        "time_series": [
            {"table": "dim_deals", "measure_column": "amount", "agg": "sum", "date_column": "closedate", "granularity": "month"},
            {"table": "dim_deals", "measure_column": "deal_id", "agg": "count", "date_column": "createdate", "granularity": "month"},
        ],
        "computed_metrics": [
            "win_rate", "total_arr_closed", "pipeline_value",
            "avg_deal_size", "avg_days_to_close", "new_logo_count",
            "deals_missing_amount", "contacts_missing_email",
            "lead_conversion_rate", "leads_without_outreach",
            "weighted_pipeline",
        ],
        "lists": {
            "dim_deals": {
                "columns": ["dealname", "amount", "dealstage", "pipeline", "hubspot_owner_id",
                            "closedate", "hs_is_closed_won", "hs_is_closed",
                            "hs_manual_forecast_category", "days_to_close"],
                "limit": 50,
            },
            "dim_leads": {
                "columns": ["hs_lead_status", "hs_lead_type", "hubspot_owner_id",
                            "first_outreach_date", "contact_last_engagement_date", "createdate"],
                "limit": 50,
            },
        },
    }

    print(f"\n  Sending query with {len(payload['computed_metrics'])} metrics, "
          f"{len(payload['grouped_measures'])} grouped measures, "
          f"{len(payload['time_series'])} time series, "
          f"{len(payload['lists'])} lists...")

    data = post_json(f"{base}/api/v1/query", payload)

    # =============================================
    # 3. Validate per-view data
    # =============================================
    counts = data.get("reachable_counts", {})
    metrics = data.get("computed_metrics", {})
    gm = data.get("grouped_measures", {})
    ts = data.get("time_series", {})
    fv = data.get("field_values", {})
    measures = data.get("measures", {})
    lists = data.get("lists", {})

    # --- Reachable counts ---
    subsection("Reachable Counts")
    for t, cnt in counts.items():
        if cnt == 0:
            warn(f"{t}: 0 reachable")
        else:
            ok(f"{t}: {cnt:,}")

    # --- Measures ---
    subsection("Aggregate Measures")
    for key, val in measures.items():
        if val is None or val == 0:
            warn(f"{key}: {val}")
        else:
            ok(f"{key}: {val:,.2f}")

    # --- Field values ---
    subsection("Field Values (sample)")
    populated = sum(1 for v in fv.values() if len(v.get("possible", [])) > 0)
    empty = sum(1 for v in fv.values() if len(v.get("possible", [])) == 0)
    ok(f"{populated} fields have values, {empty} empty")
    # Show a few
    for key in list(fv.keys())[:3]:
        vals = fv[key]
        top = vals["possible"][:3]
        preview = ", ".join(f"{v['value']}({v['count']})" for v in top)
        print(f"       {DIM}{key}: {preview}...{RESET}")

    # =============================================
    # View: Executive Summary
    # =============================================
    section("3. Executive Summary View")
    check_metric(metrics, "total_arr_closed", "ARR Closed")
    check_metric(metrics, "pipeline_value", "Pipeline Value")
    check_metric(metrics, "win_rate", "Win Rate")
    check_metric(metrics, "avg_days_to_close", "Avg Days to Close", allow_zero=True)
    check_metric(metrics, "new_logo_count", "New Logos", allow_zero=True)
    check_metric(metrics, "avg_deal_size", "Avg Deal Size")

    subsection("Charts")
    # The view looks for ts["deal_amount_by_month"] but actual key is built by engine
    ts_key_amount = "dim_deals.amount.sum.by.closedate.month"
    check_time_series(ts, ts_key_amount, "Deal Amount by Month (closedate)")

    gm_key_stage = "dim_deals.deal_id.count.by.dealstage"
    check_grouped(gm, gm_key_stage, "Deals by Stage")

    # =============================================
    # View: Deal Pipeline
    # =============================================
    section("4. Deal Pipeline View")
    check_metric(metrics, "pipeline_value", "Pipeline Value")
    check_metric(metrics, "weighted_pipeline", "Weighted Pipeline", allow_null=True)

    subsection("Charts")
    check_grouped(gm, gm_key_stage, "Deals by Stage (funnel)")
    gm_key_fc = "dim_deals.amount.sum.by.hs_manual_forecast_category"
    check_grouped(gm, gm_key_fc, "Forecast Category Breakdown")

    subsection("Deal List")
    check_list(lists, "dim_deals", "Deals",
               expected_cols=["dealname", "amount", "dealstage", "closedate", "hs_manual_forecast_category"])

    # =============================================
    # View: Lead Pipeline
    # =============================================
    section("5. Lead Pipeline View")
    check_metric(metrics, "lead_conversion_rate", "Lead Conversion Rate", allow_null=True)
    check_metric(metrics, "leads_without_outreach", "Leads Without Outreach", allow_zero=True)

    subsection("Charts")
    gm_key_ls = "dim_leads.lead_id.count.by.hs_lead_status"
    check_grouped(gm, gm_key_ls, "Leads by Status")
    gm_key_dq = "dim_leads.lead_id.count.by.disqualification_reason"
    check_grouped(gm, gm_key_dq, "DQ Reasons")

    subsection("Lead List")
    check_list(lists, "dim_leads", "Leads",
               expected_cols=["hs_lead_status", "hubspot_owner_id", "createdate"])

    # =============================================
    # View: Rep Performance
    # =============================================
    section("6. Rep Performance View")
    check_metric(metrics, "win_rate", "Team Win Rate")
    check_metric(metrics, "avg_deal_size", "Avg Deal Size")
    check_metric(metrics, "avg_days_to_close", "Avg Days to Close", allow_zero=True)

    subsection("Charts")
    gm_key_act = "fact_activities.activity_id.count.by.activity_type"
    check_grouped(gm, gm_key_act, "Activity Type Breakdown")

    gm_key_rep = "dim_deals.deal_id.count.by.hubspot_owner_id"
    check_grouped(gm, gm_key_rep, "Deals by Owner")

    # =============================================
    # View: Forecasting
    # =============================================
    section("7. Forecasting View")
    check_metric(metrics, "pipeline_value", "Pipeline Value")
    check_metric(metrics, "total_arr_closed", "Closed Won to Date")

    subsection("Charts")
    check_grouped(gm, gm_key_fc, "Forecast Category Breakdown")
    ts_key_close = "dim_deals.amount.sum.by.closedate.month"
    check_time_series(ts, ts_key_close, "Deals Closing by Month")

    # =============================================
    # View: Attribution
    # =============================================
    section("8. Attribution View")

    subsection("Charts")
    gm_key_src = "dim_contacts.contact_id.count.by.hs_analytics_source"
    check_grouped(gm, gm_key_src, "Contacts by Source")

    # =============================================
    # View: Data Quality
    # =============================================
    section("9. Data Quality View")
    check_metric(metrics, "deals_missing_amount", "Deals Missing Amount", allow_zero=True)
    check_metric(metrics, "contacts_missing_email", "Contacts Missing Email", allow_zero=True)
    check_metric(metrics, "leads_without_outreach", "Leads Without Outreach", allow_zero=True)

    # =============================================
    # Key mismatches: views expect friendly keys, engine produces qualified keys
    # =============================================
    section("10. Frontend Key Mapping Check")

    print(f"\n  The views reference data by friendly keys like 'deals_by_stage'.")
    print(f"  The engine produces qualified keys like 'dim_deals.deal_id.count.by.dealstage'.")
    print(f"  Checking if the frontend maps these correctly...\n")

    # Views use findGM(gm, groupByCol) which matches keys ending with ".by.<col>"
    # Views use findTS(ts, dateCol) which matches keys ending with ".by.<col>.month"
    view_gm_lookups = {
        "ExecutiveSummary": ["dealstage"],
        "DealPipeline": ["dealstage", "hs_manual_forecast_category"],
        "LeadPipeline": ["hs_lead_status", "disqualification_reason"],
        "RepPerformance": ["activity_type"],
        "Forecasting": ["hs_manual_forecast_category"],
        "Attribution": ["hs_analytics_source"],
    }
    view_ts_lookups = {
        "ExecutiveSummary": [("closedate", "month")],
        "Forecasting": [("closedate", "month")],
    }
    view_list_keys = {
        "RepPerformance": "rep_leaderboard",
        "Forecasting": "deals_closing_this_month",
        "Attribution": "attribution_summary",
        "DataQuality": "dq_issues",
    }

    actual_gm_keys = list(gm.keys())
    actual_ts_keys = list(ts.keys())
    actual_list_keys = list(lists.keys())

    print(f"  {BOLD}Actual grouped_measures keys:{RESET} {actual_gm_keys}")
    print(f"  {BOLD}Actual time_series keys:{RESET}      {actual_ts_keys}")
    print(f"  {BOLD}Actual lists keys:{RESET}             {actual_list_keys}")
    print()

    # Check grouped measures (suffix match, same as findGM)
    for view, cols in view_gm_lookups.items():
        for col in cols:
            suffix = f".by.{col}"
            match = [k for k in actual_gm_keys if k.endswith(suffix)]
            if match:
                ok(f"{view} findGM(*, '{col}') → {match[0]}")
            else:
                fail(f"{view} findGM(*, '{col}') — no key ending with '{suffix}'")

    # Check time series (suffix match, same as findTS)
    for view, lookups in view_ts_lookups.items():
        for date_col, gran in lookups:
            suffix = f".by.{date_col}.{gran}"
            match = [k for k in actual_ts_keys if k.endswith(suffix)]
            if match:
                ok(f"{view} findTS(*, '{date_col}') → {match[0]}")
            else:
                fail(f"{view} findTS(*, '{date_col}') — no key ending with '{suffix}'")

    # Check lists (these are aspirational — views show empty gracefully)
    for view, k in view_list_keys.items():
        if k not in lists:
            warn(f"{view} lists['{k}'] — not in query (view shows empty state)")
        else:
            ok(f"{view} lists['{k}'] found")

    # =============================================
    # Summary
    # =============================================
    section("SUMMARY")
    print(f"\n  {GREEN}{ok_count} passed{RESET}  |  {YELLOW}{warn_count} warnings{RESET}  |  {RED}{fail_count} failures{RESET}\n")

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
