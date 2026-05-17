"""Gold layer assets — analytics-driven aggregates for dashboard components."""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource


def _swap_gold_table(ch: ClickHouseResource, table: str, log):
    """Atomic swap: gold.{table}_tmp -> gold.{table}."""
    tmp = f"{table}_tmp"
    ch.execute_sql(f"CREATE TABLE IF NOT EXISTS gold.{table} AS gold.{tmp}")
    log.info(f"EXCHANGE TABLES gold.{table} AND gold.{tmp}")
    ch.execute_sql(f"EXCHANGE TABLES gold.{table} AND gold.{tmp}")
    ch.execute_sql(f"DROP TABLE IF EXISTS gold.{tmp}")


# ---------------------------------------------------------------------------
# gold.agg_deal_stage_funnel — pipeline stage conversion + velocity
# ---------------------------------------------------------------------------

@asset(
    name="agg_deal_stage_funnel",
    group_name="gold",
    deps=[AssetKey("dim_deals"), AssetKey("dim_pipeline_stages")],
)
def agg_deal_stage_funnel(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    target = "agg_deal_stage_funnel"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding gold.agg_deal_stage_funnel")
    ch_gold.execute_sql(f"DROP TABLE IF EXISTS gold.{tmp}")

    ch_gold.execute_sql(f"""
CREATE TABLE gold.{tmp} (
    pipeline_id LowCardinality(String),
    stage_id String,
    stage_label String,
    display_order UInt32,
    is_closed LowCardinality(String),
    deals_currently_in UInt32,
    total_value Nullable(Float64),
    weighted_value Nullable(Float64),
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at)
ORDER BY (pipeline_id, stage_id)
""".strip())

    ch_gold.execute_sql(f"""
INSERT INTO gold.{tmp}
SELECT
    pipeline AS pipeline_id,
    dealstage AS stage_id,
    dictGet('silver.dict_pipeline_stages', 'label', tuple(dealstage)) AS stage_label,
    dictGet('silver.dict_pipeline_stages', 'display_order', tuple(dealstage)) AS display_order,
    dictGet('silver.dict_pipeline_stages', 'is_closed', tuple(dealstage)) AS is_closed,
    count() AS deals_currently_in,
    sum(amount) AS total_value,
    sum(amount * hs_deal_stage_probability / 100) AS weighted_value,
    now() AS _gold_loaded_at
FROM silver.dim_deals
WHERE archived = 0
GROUP BY pipeline_id, stage_id, stage_label, display_order, is_closed
ORDER BY pipeline_id, display_order
""".strip())

    _swap_gold_table(ch_gold, target, context.log)

    row_count = ch_gold.execute_sql("SELECT count() FROM gold.agg_deal_stage_funnel")
    context.log.info(f"gold.agg_deal_stage_funnel: {row_count} rows")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
    })


# ---------------------------------------------------------------------------
# gold.agg_deal_health — per-deal operational health
# ---------------------------------------------------------------------------

@asset(
    name="agg_deal_health",
    group_name="gold",
    deps=[
        AssetKey("dim_deals"),
        AssetKey("bridge_activity_deal"),
        AssetKey("fact_activities"),
    ],
)
def agg_deal_health(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    target = "agg_deal_health"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding gold.agg_deal_health")
    ch_gold.execute_sql(f"DROP TABLE IF EXISTS gold.{tmp}")

    ch_gold.execute_sql(f"""
CREATE TABLE gold.{tmp} (
    deal_id String,
    dealname String,
    dealstage LowCardinality(String),
    stage_label String,
    pipeline LowCardinality(String),
    pipeline_label String,
    hubspot_owner_id String,
    owner_name String,
    amount Nullable(Float64),
    hs_is_closed LowCardinality(String),
    hs_is_closed_won LowCardinality(String),
    days_in_current_stage Nullable(UInt32),
    days_since_last_activity Nullable(UInt32),
    last_activity_date Nullable(DateTime),
    last_activity_type LowCardinality(String),
    has_future_activity UInt8,
    next_activity_date Nullable(DateTime),
    is_stale UInt8,
    missing_amount UInt8,
    missing_closedate UInt8,
    missing_owner UInt8,
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at) ORDER BY (deal_id)
""".strip())

    ch_gold.execute_sql(f"""
INSERT INTO gold.{tmp}
SELECT
    d.deal_id,
    d.dealname,
    d.dealstage,
    COALESCE(d.stage_label, '') AS stage_label,
    d.pipeline,
    COALESCE(d.pipeline_label, '') AS pipeline_label,
    d.hubspot_owner_id,
    concat(
        dictGet('silver.dict_owners', 'first_name', tuple(d.hubspot_owner_id)),
        ' ',
        dictGet('silver.dict_owners', 'last_name', tuple(d.hubspot_owner_id))
    ) AS owner_name,
    d.amount,
    d.hs_is_closed,
    d.hs_is_closed_won,
    dateDiff('day', greatest(
        d.hs_v2_date_entered_closedwon,
        d.hs_v2_date_entered_closedlost,
        d.hs_v2_date_entered_contractsent,
        d.hs_v2_date_entered_qualifiedtobuy,
        d.hs_v2_date_entered_decisionmakerboughtin,
        d.hs_v2_date_entered_presentationscheduled,
        d.createdate
    ), today()) AS days_in_current_stage,
    if(act.last_activity_date > '1970-01-02',
       dateDiff('day', act.last_activity_date, today()),
       NULL) AS days_since_last_activity,
    act.last_activity_date,
    act.last_activity_type,
    act.has_future_activity,
    act.next_activity_date,
    if(
        (d.hs_is_closed = 'false' OR d.hs_is_closed = '')
        AND (act.last_activity_date IS NULL OR dateDiff('day', act.last_activity_date, today()) > 14),
        1, 0
    ) AS is_stale,
    if(d.amount IS NULL OR d.amount = 0, 1, 0) AS missing_amount,
    if(d.closedate <= '1970-01-02', 1, 0) AS missing_closedate,
    if(d.hubspot_owner_id = '', 1, 0) AS missing_owner,
    now() AS _gold_loaded_at
FROM silver.dim_deals d
LEFT JOIN (
    SELECT
        b.deal_id,
        maxIf(a.hs_timestamp, a.hs_timestamp <= now()) AS last_activity_date,
        argMaxIf(a.activity_type, a.hs_timestamp, a.hs_timestamp <= now()) AS last_activity_type,
        if(countIf(a.hs_timestamp > now()) > 0, 1, 0) AS has_future_activity,
        minIf(a.hs_timestamp, a.hs_timestamp > now()) AS next_activity_date
    FROM silver.bridge_activity_deal b
    INNER JOIN silver.fact_activities a ON b.activity_id = a.activity_id
    WHERE a.archived = 0
    GROUP BY b.deal_id
) act ON d.deal_id = act.deal_id
WHERE d.archived = 0
""".strip())

    _swap_gold_table(ch_gold, target, context.log)

    row_count = ch_gold.execute_sql("SELECT count() FROM gold.agg_deal_health")
    context.log.info(f"gold.agg_deal_health: {row_count} rows")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
    })


# ---------------------------------------------------------------------------
# gold.agg_rep_performance — monthly rep scorecard
# ---------------------------------------------------------------------------

@asset(
    name="agg_rep_performance",
    group_name="gold",
    deps=[
        AssetKey("dim_deals"),
        AssetKey("fact_activities"),
        AssetKey("dim_owners"),
    ],
)
def agg_rep_performance(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    target = "agg_rep_performance"
    tmp = f"{target}_tmp"

    # Canonical revenue column comes from customer config; default `amount` always
    # exists on every HubSpot portal. Per-portal overrides (e.g. annual_recurring_revenue,
    # total_contract_value) flow in from ~/.clickspot/customer.json.
    from app.customer import config as cc
    canonical_amount = cc.load().get("canonical_amount_col", "amount")

    context.log.info(f"Rebuilding gold.agg_rep_performance (revenue column: {canonical_amount})")
    ch_gold.execute_sql(f"DROP TABLE IF EXISTS gold.{tmp}")

    ch_gold.execute_sql(f"""
CREATE TABLE gold.{tmp} (
    hubspot_owner_id String,
    owner_name String,
    period_start Date,
    deals_won UInt32,
    deals_lost UInt32,
    deals_created UInt32,
    win_rate Nullable(Float64),
    total_arr_closed Nullable(Float64),
    avg_deal_size Nullable(Float64),
    avg_days_to_close Nullable(Float64),
    pipeline_value Nullable(Float64),
    calls_count UInt32,
    meetings_count UInt32,
    emails_count UInt32,
    tasks_count UInt32,
    total_activities UInt32,
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at)
PARTITION BY toYYYYMM(period_start)
ORDER BY (hubspot_owner_id, period_start)
""".strip())

    ch_gold.execute_sql(f"""
INSERT INTO gold.{tmp}
SELECT
    d.hubspot_owner_id,
    concat(
        dictGet('silver.dict_owners', 'first_name', tuple(d.hubspot_owner_id)),
        ' ',
        dictGet('silver.dict_owners', 'last_name', tuple(d.hubspot_owner_id))
    ) AS owner_name,
    toStartOfMonth(d.createdate) AS period_start,
    countIf(d.hs_is_closed_won = 'true') AS deals_won,
    countIf(d.hs_is_closed = 'true' AND d.hs_is_closed_won != 'true') AS deals_lost,
    count() AS deals_created,
    if(countIf(d.hs_is_closed = 'true') > 0,
       countIf(d.hs_is_closed_won = 'true') * 1.0 / countIf(d.hs_is_closed = 'true'),
       NULL) AS win_rate,
    sumIf(d.{canonical_amount}, d.hs_is_closed_won = 'true') AS total_arr_closed,
    avgIf(d.amount, d.hs_is_closed_won = 'true' AND d.amount > 0) AS avg_deal_size,
    avgIf(d.days_to_close, d.hs_is_closed_won = 'true' AND d.days_to_close > 0) AS avg_days_to_close,
    sumIf(d.amount, d.hs_is_closed = 'false' OR d.hs_is_closed = '') AS pipeline_value,
    COALESCE(act.calls_count, 0) AS calls_count,
    COALESCE(act.meetings_count, 0) AS meetings_count,
    COALESCE(act.emails_count, 0) AS emails_count,
    COALESCE(act.tasks_count, 0) AS tasks_count,
    COALESCE(act.total_activities, 0) AS total_activities,
    now() AS _gold_loaded_at
FROM silver.dim_deals d
LEFT JOIN (
    SELECT
        a.hubspot_owner_id,
        toStartOfMonth(a.hs_timestamp) AS period_start,
        countIf(a.activity_type = 'call') AS calls_count,
        countIf(a.activity_type = 'meeting') AS meetings_count,
        countIf(a.activity_type = 'email') AS emails_count,
        countIf(a.activity_type = 'task') AS tasks_count,
        count() AS total_activities
    FROM silver.fact_activities a
    WHERE a.archived = 0 AND a.hubspot_owner_id != '' AND a.hs_timestamp > '1970-01-02'
    GROUP BY a.hubspot_owner_id, toStartOfMonth(a.hs_timestamp)
) act ON d.hubspot_owner_id = act.hubspot_owner_id
    AND toStartOfMonth(d.createdate) = act.period_start
WHERE d.archived = 0 AND d.hubspot_owner_id != '' AND d.createdate > '1970-01-02'
GROUP BY d.hubspot_owner_id, owner_name, toStartOfMonth(d.createdate),
    act.calls_count, act.meetings_count, act.emails_count, act.tasks_count, act.total_activities
""".strip())

    _swap_gold_table(ch_gold, target, context.log)

    row_count = ch_gold.execute_sql("SELECT count() FROM gold.agg_rep_performance")
    context.log.info(f"gold.agg_rep_performance: {row_count} rows")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
    })


# ---------------------------------------------------------------------------
# gold.agg_source_attribution — marketing source funnel
# ---------------------------------------------------------------------------

@asset(
    name="agg_source_attribution",
    group_name="gold",
    deps=[
        AssetKey("dim_contacts"),
        AssetKey("bridge_contact_deal"),
        AssetKey("dim_deals"),
    ],
)
def agg_source_attribution(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    target = "agg_source_attribution"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding gold.agg_source_attribution")
    ch_gold.execute_sql(f"DROP TABLE IF EXISTS gold.{tmp}")

    ch_gold.execute_sql(f"""
CREATE TABLE gold.{tmp} (
    hs_analytics_source LowCardinality(String),
    hs_analytics_source_data_1 String,
    contacts_count UInt32,
    mql_count UInt32,
    sql_count UInt32,
    deals_associated UInt32,
    deals_won UInt32,
    pipeline_value Nullable(Float64),
    closed_won_value Nullable(Float64),
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at)
ORDER BY (hs_analytics_source, hs_analytics_source_data_1)
""".strip())

    ch_gold.execute_sql(f"""
INSERT INTO gold.{tmp}
SELECT
    c.hs_analytics_source,
    c.hs_analytics_source_data_1,
    count() AS contacts_count,
    countIf(c.hs_v2_date_entered_marketingqualifiedlead > '1970-01-02') AS mql_count,
    countIf(c.hs_v2_date_entered_salesqualifiedlead > '1970-01-02') AS sql_count,
    countIf(deals.has_deal = 1) AS deals_associated,
    countIf(deals.has_won_deal = 1) AS deals_won,
    sumIf(deals.total_deal_amount, deals.has_deal = 1) AS pipeline_value,
    sumIf(deals.won_deal_amount, deals.has_won_deal = 1) AS closed_won_value,
    now() AS _gold_loaded_at
FROM silver.dim_contacts c
LEFT JOIN (
    SELECT
        b.contact_id,
        1 AS has_deal,
        if(countIf(d.hs_is_closed_won = 'true') > 0, 1, 0) AS has_won_deal,
        sum(d.amount) AS total_deal_amount,
        sumIf(d.amount, d.hs_is_closed_won = 'true') AS won_deal_amount
    FROM silver.bridge_contact_deal b
    INNER JOIN silver.dim_deals d ON b.deal_id = d.deal_id
    WHERE d.archived = 0
    GROUP BY b.contact_id
) deals ON c.contact_id = deals.contact_id
WHERE c.archived = 0 AND c.hs_analytics_source != ''
GROUP BY c.hs_analytics_source, c.hs_analytics_source_data_1
""".strip())

    _swap_gold_table(ch_gold, target, context.log)

    row_count = ch_gold.execute_sql("SELECT count() FROM gold.agg_source_attribution")
    context.log.info(f"gold.agg_source_attribution: {row_count} rows")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
    })


# ---------------------------------------------------------------------------
# gold.agg_lead_health — per-lead operational health
# ---------------------------------------------------------------------------

@asset(
    name="agg_lead_health",
    group_name="gold",
    deps=[AssetKey("dim_leads"), AssetKey("dim_owners"), AssetKey("dim_lead_pipelines"), AssetKey("dim_lead_pipeline_stages")],
)
def agg_lead_health(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    target = "agg_lead_health"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding gold.agg_lead_health")
    ch_gold.execute_sql(f"DROP TABLE IF EXISTS gold.{tmp}")

    ch_gold.execute_sql(f"""
CREATE TABLE gold.{tmp} (
    lead_id String,
    lead_name String,
    hubspot_owner_id String,
    owner_name String,
    hs_pipeline LowCardinality(String),
    pipeline_label LowCardinality(String),
    hs_pipeline_stage LowCardinality(String),
    stage_label LowCardinality(String),
    hs_lead_status LowCardinality(String),
    hs_lead_type LowCardinality(String),
    createdate DateTime,
    date_entered_current_stage DateTime,
    days_in_current_stage Nullable(UInt32),
    days_since_creation UInt32,
    days_since_last_engagement Nullable(UInt32),
    has_outreach UInt8,
    days_to_first_outreach Nullable(UInt32),
    has_associated_deal UInt8,
    is_stale UInt8,
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at) ORDER BY (lead_id)
""".strip())

    ch_gold.execute_sql(f"""
INSERT INTO gold.{tmp}
SELECT
    l.lead_id,
    l.hs_lead_name AS lead_name,
    l.hubspot_owner_id,
    concat(
        dictGet('silver.dict_owners', 'first_name', tuple(l.hubspot_owner_id)),
        ' ',
        dictGet('silver.dict_owners', 'last_name', tuple(l.hubspot_owner_id))
    ) AS owner_name,
    l.hs_pipeline,
    dictGet('silver.dict_lead_pipelines', 'label', tuple(l.hs_pipeline)) AS pipeline_label,
    l.hs_pipeline_stage,
    dictGet('silver.dict_lead_pipeline_stages', 'label', tuple(l.hs_pipeline, l.hs_pipeline_stage)) AS stage_label,
    l.hs_lead_status,
    l.hs_lead_type,
    l.createdate,
    l.date_entered_current_stage,
    if(l.date_entered_current_stage > '1970-01-02',
       dateDiff('day', l.date_entered_current_stage, today()),
       NULL) AS days_in_current_stage,
    dateDiff('day', l.createdate, today()) AS days_since_creation,
    if(l.last_engagement_date > '1970-01-02',
       dateDiff('day', l.last_engagement_date, today()),
       NULL) AS days_since_last_engagement,
    if(l.first_outreach_date > '1970-01-02', 1, 0) AS has_outreach,
    if(l.first_outreach_date > '1970-01-02',
       dateDiff('day', l.createdate, l.first_outreach_date),
       NULL) AS days_to_first_outreach,
    if(l.associated_deals != '', 1, 0) AS has_associated_deal,
    if(dictGet('silver.dict_lead_pipeline_stages', 'is_closed', tuple(l.hs_pipeline, l.hs_pipeline_stage)) != 'true'
       AND (l.last_engagement_date <= '1970-01-02'
            OR dateDiff('day', l.last_engagement_date, today()) > 7),
       1, 0) AS is_stale,
    now() AS _gold_loaded_at
FROM silver.dim_leads l
WHERE l.archived = 0
""".strip())

    _swap_gold_table(ch_gold, target, context.log)

    row_count = ch_gold.execute_sql("SELECT count() FROM gold.agg_lead_health")
    context.log.info(f"gold.agg_lead_health: {row_count} rows")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
    })


# ---------------------------------------------------------------------------
# gold.agg_deal_cohorts — creation-month cohort analysis
# ---------------------------------------------------------------------------

@asset(
    name="agg_deal_cohorts",
    group_name="gold",
    deps=[AssetKey("dim_deals")],
)
def agg_deal_cohorts(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    target = "agg_deal_cohorts"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding gold.agg_deal_cohorts")
    ch_gold.execute_sql(f"DROP TABLE IF EXISTS gold.{tmp}")

    ch_gold.execute_sql(f"""
CREATE TABLE gold.{tmp} (
    cohort_month Date,
    pipeline LowCardinality(String),
    deal_origin LowCardinality(String),
    deals_created UInt32,
    deals_won UInt32,
    deals_lost UInt32,
    deals_still_open UInt32,
    total_created_value Nullable(Float64),
    total_won_value Nullable(Float64),
    avg_days_to_close Nullable(Float64),
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at)
PARTITION BY toYYYYMM(cohort_month)
ORDER BY (cohort_month, pipeline, deal_origin)
""".strip())

    ch_gold.execute_sql(f"""
INSERT INTO gold.{tmp}
SELECT
    toStartOfMonth(createdate) AS cohort_month,
    pipeline,
    multiIf(
        renewal != '', 'renewal',
        new_logo != '', 'new_logo',
        'other'
    ) AS deal_origin,
    count() AS deals_created,
    countIf(hs_is_closed_won = 'true') AS deals_won,
    countIf(hs_is_closed = 'true' AND hs_is_closed_won != 'true') AS deals_lost,
    countIf(hs_is_closed = 'false' OR hs_is_closed = '') AS deals_still_open,
    sum(amount) AS total_created_value,
    sumIf(amount, hs_is_closed_won = 'true') AS total_won_value,
    avgIf(days_to_close, hs_is_closed_won = 'true' AND days_to_close > 0) AS avg_days_to_close,
    now() AS _gold_loaded_at
FROM silver.dim_deals
WHERE archived = 0 AND createdate > '1970-01-02'
GROUP BY toStartOfMonth(createdate), pipeline, deal_origin
""".strip())

    _swap_gold_table(ch_gold, target, context.log)

    row_count = ch_gold.execute_sql("SELECT count() FROM gold.agg_deal_cohorts")
    context.log.info(f"gold.agg_deal_cohorts: {row_count} rows")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
    })


# ---------------------------------------------------------------------------
# gold.fact_pipeline_snapshots — daily append-only
# ---------------------------------------------------------------------------

@asset(
    name="fact_pipeline_snapshots",
    group_name="gold",
    deps=[AssetKey("dim_deals"), AssetKey("dim_pipeline_stages")],
)
def fact_pipeline_snapshots(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    context.log.info("Appending to gold.fact_pipeline_snapshots")

    ch_gold.execute_sql("""
CREATE TABLE IF NOT EXISTS gold.fact_pipeline_snapshots (
    snapshot_date Date,
    pipeline LowCardinality(String),
    total_open_deals UInt32,
    total_pipeline_value Nullable(Float64),
    weighted_pipeline_value Nullable(Float64),
    commit_value Nullable(Float64),
    best_case_value Nullable(Float64),
    closed_won_value Nullable(Float64),
    closed_won_count UInt32,
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = MergeTree()
PARTITION BY toYYYYMM(snapshot_date)
ORDER BY (pipeline, snapshot_date)
TTL snapshot_date + INTERVAL 2 YEAR
""".strip())

    ch_gold.execute_sql("""
INSERT INTO gold.fact_pipeline_snapshots
SELECT
    today() AS snapshot_date,
    pipeline,
    countIf(hs_is_closed = 'false' OR hs_is_closed = '') AS total_open_deals,
    sumIf(amount, hs_is_closed = 'false' OR hs_is_closed = '') AS total_pipeline_value,
    sumIf(amount * hs_deal_stage_probability / 100, hs_is_closed = 'false' OR hs_is_closed = '') AS weighted_pipeline_value,
    sumIf(amount, hs_manual_forecast_category = 'commit') AS commit_value,
    sumIf(amount, hs_manual_forecast_category IN ('commit', 'best_case')) AS best_case_value,
    sumIf(amount, hs_is_closed_won = 'true') AS closed_won_value,
    countIf(hs_is_closed_won = 'true') AS closed_won_count,
    now() AS _gold_loaded_at
FROM silver.dim_deals
WHERE archived = 0
GROUP BY pipeline
""".strip())

    row_count = ch_gold.execute_sql("SELECT count() FROM gold.fact_pipeline_snapshots")
    context.log.info(f"gold.fact_pipeline_snapshots: {row_count} total rows")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
    })


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

all_gold_assets = [
    agg_deal_stage_funnel,
    agg_deal_health,
    agg_rep_performance,
    agg_source_attribution,
    agg_lead_health,
    agg_deal_cohorts,
    fact_pipeline_snapshots,
]
