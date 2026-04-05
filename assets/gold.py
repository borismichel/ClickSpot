"""Gold layer assets — analytics-driven aggregates for dashboard components."""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource


# ---------------------------------------------------------------------------
# gold.agg_deal_stage_funnel — pipeline stage conversion + velocity
# ---------------------------------------------------------------------------

@asset(
    name="agg_deal_stage_funnel",
    group_name="gold",
    deps=[AssetKey("dim_deals"), AssetKey("dim_pipeline_stages")],
)
def agg_deal_stage_funnel(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    context.log.info("Rebuilding gold.agg_deal_stage_funnel")
    ch_gold.execute_sql("DROP TABLE IF EXISTS gold.agg_deal_stage_funnel")

    ch_gold.execute_sql("""
CREATE TABLE gold.agg_deal_stage_funnel (
    pipeline_id String,
    stage_id String,
    stage_label String,
    display_order UInt32,
    is_closed String,
    deals_currently_in UInt32,
    total_value Nullable(Float64),
    weighted_value Nullable(Float64),
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at)
ORDER BY (pipeline_id, stage_id)
""".strip())

    ch_gold.execute_sql("""
INSERT INTO gold.agg_deal_stage_funnel
SELECT
    COALESCE(s.pipeline_id, d.pipeline) AS pipeline_id,
    COALESCE(s.stage_id, d.dealstage) AS stage_id,
    COALESCE(s.label, d.dealstage) AS stage_label,
    COALESCE(s.display_order, 999) AS display_order,
    COALESCE(s.is_closed, '') AS is_closed,
    count() AS deals_currently_in,
    sum(d.amount) AS total_value,
    sum(d.amount * d.hs_deal_stage_probability / 100) AS weighted_value,
    now() AS _gold_loaded_at
FROM silver.dim_deals d FINAL
LEFT JOIN silver.dim_pipeline_stages s FINAL ON d.dealstage = s.stage_id
WHERE d.archived = 0
GROUP BY pipeline_id, stage_id, stage_label, display_order, is_closed
ORDER BY pipeline_id, display_order
""".strip())

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
    context.log.info("Rebuilding gold.agg_deal_health")
    ch_gold.execute_sql("DROP TABLE IF EXISTS gold.agg_deal_health")

    ch_gold.execute_sql("""
CREATE TABLE gold.agg_deal_health (
    deal_id String,
    dealname String,
    dealstage String,
    stage_label String,
    pipeline String,
    pipeline_label String,
    hubspot_owner_id String,
    owner_name String,
    amount Nullable(Float64),
    days_in_current_stage Nullable(UInt32),
    days_since_last_activity Nullable(UInt32),
    last_activity_date Nullable(DateTime),
    last_activity_type String,
    has_future_activity UInt8,
    next_activity_date Nullable(DateTime),
    is_stale UInt8,
    missing_amount UInt8,
    missing_closedate UInt8,
    missing_owner UInt8,
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at) ORDER BY (deal_id)
""".strip())

    ch_gold.execute_sql("""
INSERT INTO gold.agg_deal_health
SELECT
    d.deal_id,
    d.dealname,
    d.dealstage,
    COALESCE(d.stage_label, '') AS stage_label,
    d.pipeline,
    COALESCE(d.pipeline_label, '') AS pipeline_label,
    d.hubspot_owner_id,
    COALESCE(d.owner_name, '') AS owner_name,
    d.amount,
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
FROM silver.dim_deals d FINAL
LEFT JOIN (
    SELECT
        b.deal_id,
        maxIf(a.hs_timestamp, a.hs_timestamp <= now()) AS last_activity_date,
        argMaxIf(a.activity_type, a.hs_timestamp, a.hs_timestamp <= now()) AS last_activity_type,
        if(countIf(a.hs_timestamp > now()) > 0, 1, 0) AS has_future_activity,
        minIf(a.hs_timestamp, a.hs_timestamp > now()) AS next_activity_date
    FROM silver.bridge_activity_deal b
    INNER JOIN silver.fact_activities a FINAL ON b.activity_id = a.activity_id
    WHERE a.archived = 0
    GROUP BY b.deal_id
) act ON d.deal_id = act.deal_id
WHERE d.archived = 0
""".strip())

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
    context.log.info("Rebuilding gold.agg_rep_performance")
    ch_gold.execute_sql("DROP TABLE IF EXISTS gold.agg_rep_performance")

    ch_gold.execute_sql("""
CREATE TABLE gold.agg_rep_performance (
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
ORDER BY (hubspot_owner_id, period_start)
""".strip())

    ch_gold.execute_sql("""
INSERT INTO gold.agg_rep_performance
SELECT
    d.hubspot_owner_id,
    COALESCE(d.owner_name, '') AS owner_name,
    toStartOfMonth(d.createdate) AS period_start,
    countIf(d.hs_is_closed_won = 'true') AS deals_won,
    countIf(d.hs_is_closed = 'true' AND d.hs_is_closed_won != 'true') AS deals_lost,
    count() AS deals_created,
    if(countIf(d.hs_is_closed = 'true') > 0,
       countIf(d.hs_is_closed_won = 'true') * 1.0 / countIf(d.hs_is_closed = 'true'),
       NULL) AS win_rate,
    sumIf(d.annual_recurring_revenue, d.hs_is_closed_won = 'true') AS total_arr_closed,
    avgIf(d.amount, d.hs_is_closed_won = 'true' AND d.amount > 0) AS avg_deal_size,
    avgIf(d.days_to_close, d.hs_is_closed_won = 'true' AND d.days_to_close > 0) AS avg_days_to_close,
    sumIf(d.amount, d.hs_is_closed = 'false' OR d.hs_is_closed = '') AS pipeline_value,
    COALESCE(act.calls_count, 0) AS calls_count,
    COALESCE(act.meetings_count, 0) AS meetings_count,
    COALESCE(act.emails_count, 0) AS emails_count,
    COALESCE(act.tasks_count, 0) AS tasks_count,
    COALESCE(act.total_activities, 0) AS total_activities,
    now() AS _gold_loaded_at
FROM silver.dim_deals d FINAL
LEFT JOIN (
    SELECT
        a.hubspot_owner_id,
        toStartOfMonth(a.hs_timestamp) AS period_start,
        countIf(a.activity_type = 'call') AS calls_count,
        countIf(a.activity_type = 'meeting') AS meetings_count,
        countIf(a.activity_type = 'email') AS emails_count,
        countIf(a.activity_type = 'task') AS tasks_count,
        count() AS total_activities
    FROM silver.fact_activities a FINAL
    WHERE a.archived = 0 AND a.hubspot_owner_id != '' AND a.hs_timestamp > '1970-01-02'
    GROUP BY a.hubspot_owner_id, toStartOfMonth(a.hs_timestamp)
) act ON d.hubspot_owner_id = act.hubspot_owner_id
    AND toStartOfMonth(d.createdate) = act.period_start
WHERE d.archived = 0 AND d.hubspot_owner_id != '' AND d.createdate > '1970-01-02'
GROUP BY d.hubspot_owner_id, d.owner_name, toStartOfMonth(d.createdate),
    act.calls_count, act.meetings_count, act.emails_count, act.tasks_count, act.total_activities
""".strip())

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
    context.log.info("Rebuilding gold.agg_source_attribution")
    ch_gold.execute_sql("DROP TABLE IF EXISTS gold.agg_source_attribution")

    ch_gold.execute_sql("""
CREATE TABLE gold.agg_source_attribution (
    hs_analytics_source String,
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

    ch_gold.execute_sql("""
INSERT INTO gold.agg_source_attribution
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
FROM silver.dim_contacts c FINAL
LEFT JOIN (
    SELECT
        b.contact_id,
        1 AS has_deal,
        if(countIf(d.hs_is_closed_won = 'true') > 0, 1, 0) AS has_won_deal,
        sum(d.amount) AS total_deal_amount,
        sumIf(d.amount, d.hs_is_closed_won = 'true') AS won_deal_amount
    FROM silver.bridge_contact_deal b
    INNER JOIN silver.dim_deals d FINAL ON b.deal_id = d.deal_id
    WHERE d.archived = 0
    GROUP BY b.contact_id
) deals ON c.contact_id = deals.contact_id
WHERE c.archived = 0 AND c.hs_analytics_source != ''
GROUP BY c.hs_analytics_source, c.hs_analytics_source_data_1
""".strip())

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
    deps=[AssetKey("dim_leads"), AssetKey("dim_owners")],
)
def agg_lead_health(context: AssetExecutionContext, ch_gold: ClickHouseResource):
    context.log.info("Rebuilding gold.agg_lead_health")
    ch_gold.execute_sql("DROP TABLE IF EXISTS gold.agg_lead_health")

    ch_gold.execute_sql("""
CREATE TABLE gold.agg_lead_health (
    lead_id String,
    hubspot_owner_id String,
    owner_name String,
    hs_lead_status String,
    hs_lead_type String,
    createdate DateTime,
    days_since_creation UInt32,
    days_since_last_engagement Nullable(UInt32),
    has_outreach UInt8,
    days_to_first_outreach Nullable(UInt32),
    has_associated_deal UInt8,
    is_stale UInt8,
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at) ORDER BY (lead_id)
""".strip())

    ch_gold.execute_sql("""
INSERT INTO gold.agg_lead_health
SELECT
    l.lead_id,
    l.hubspot_owner_id,
    COALESCE(concat(o.first_name, ' ', o.last_name), '') AS owner_name,
    l.hs_lead_status,
    l.hs_lead_type,
    l.createdate,
    dateDiff('day', l.createdate, today()) AS days_since_creation,
    if(l.contact_last_engagement_date > '1970-01-02',
       dateDiff('day', l.contact_last_engagement_date, today()),
       NULL) AS days_since_last_engagement,
    if(l.first_outreach_date > '1970-01-02', 1, 0) AS has_outreach,
    if(l.first_outreach_date > '1970-01-02',
       dateDiff('day', l.createdate, l.first_outreach_date),
       NULL) AS days_to_first_outreach,
    if(l.associated_deals != '', 1, 0) AS has_associated_deal,
    if(l.hs_lead_status NOT IN ('DISQUALIFIED', 'CONVERTED')
       AND (l.contact_last_engagement_date <= '1970-01-02'
            OR dateDiff('day', l.contact_last_engagement_date, today()) > 7),
       1, 0) AS is_stale,
    now() AS _gold_loaded_at
FROM silver.dim_leads l FINAL
LEFT JOIN silver.dim_owners o FINAL ON l.hubspot_owner_id = o.owner_id
WHERE l.archived = 0
""".strip())

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
    context.log.info("Rebuilding gold.agg_deal_cohorts")
    ch_gold.execute_sql("DROP TABLE IF EXISTS gold.agg_deal_cohorts")

    ch_gold.execute_sql("""
CREATE TABLE gold.agg_deal_cohorts (
    cohort_month Date,
    pipeline String,
    deal_origin String,
    deals_created UInt32,
    deals_won UInt32,
    deals_lost UInt32,
    deals_still_open UInt32,
    total_created_value Nullable(Float64),
    total_won_value Nullable(Float64),
    avg_days_to_close Nullable(Float64),
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_gold_loaded_at)
ORDER BY (cohort_month, pipeline, deal_origin)
""".strip())

    ch_gold.execute_sql("""
INSERT INTO gold.agg_deal_cohorts
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
FROM silver.dim_deals FINAL
WHERE archived = 0 AND createdate > '1970-01-02'
GROUP BY toStartOfMonth(createdate), pipeline, deal_origin
""".strip())

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
    pipeline String,
    total_open_deals UInt32,
    total_pipeline_value Nullable(Float64),
    weighted_pipeline_value Nullable(Float64),
    commit_value Nullable(Float64),
    best_case_value Nullable(Float64),
    closed_won_value Nullable(Float64),
    closed_won_count UInt32,
    _gold_loaded_at DateTime DEFAULT now()
) ENGINE = MergeTree()
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
FROM silver.dim_deals FINAL
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
