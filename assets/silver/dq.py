"""Silver data-quality metrics asset.

dq_metrics depends on every silver table via AssetKey but tolerates missing
ones at runtime — when an object is disabled the corresponding row counts /
null checks / orphan checks are simply skipped instead of failing the whole
silver job.
"""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource
from app.customer import extraction as _ext


# ---------------------------------------------------------------------------
# DQ metrics (append-only)
# ---------------------------------------------------------------------------

_ALL_SILVER_DIM_ASSETS_FULL = [
    "dim_contacts", "dim_companies", "dim_deals", "dim_leads",
    "dim_owners",
    "dim_pipelines", "dim_pipeline_stages",
    "dim_lead_pipelines", "dim_lead_pipeline_stages",
]
_ALL_SILVER_FACT_ASSETS_FULL = ["fact_activities", "fact_form_submissions"]
_ALL_SILVER_BRIDGE_ASSETS_FULL = [
    "bridge_contact_company", "bridge_contact_deal", "bridge_deal_company",
    "bridge_lead_contact", "bridge_deal_lead", "bridge_lead_company",
    "bridge_activity_contact", "bridge_activity_company", "bridge_activity_deal",
]


def _enabled_silver_dq_tables():
    """Silver tables that exist on this portal (the only ones we should DQ-check)."""
    enabled = _ext.get_enabled_silver_tables()
    full = _ALL_SILVER_DIM_ASSETS_FULL + _ALL_SILVER_FACT_ASSETS_FULL + _ALL_SILVER_BRIDGE_ASSETS_FULL
    return [t for t in full if t in enabled]


# All possible (bridge_table, bridge_col, dim_table, dim_col) orphan checks.
# Each row is filtered at runtime against the enabled silver-table set.
_ALL_ORPHAN_CHECKS = [
    ("bridge_contact_company", "contact_id", "dim_contacts", "contact_id"),
    ("bridge_contact_company", "company_id", "dim_companies", "company_id"),
    ("bridge_contact_deal", "contact_id", "dim_contacts", "contact_id"),
    ("bridge_contact_deal", "deal_id", "dim_deals", "deal_id"),
    ("bridge_deal_company", "deal_id", "dim_deals", "deal_id"),
    ("bridge_deal_company", "company_id", "dim_companies", "company_id"),
    ("bridge_lead_contact", "lead_id", "dim_leads", "lead_id"),
    ("bridge_lead_contact", "contact_id", "dim_contacts", "contact_id"),
    ("bridge_deal_lead", "deal_id", "dim_deals", "deal_id"),
    ("bridge_deal_lead", "lead_id", "dim_leads", "lead_id"),
    ("bridge_lead_company", "lead_id", "dim_leads", "lead_id"),
    ("bridge_lead_company", "company_id", "dim_companies", "company_id"),
    ("bridge_activity_contact", "activity_id", "fact_activities", "activity_id"),
    ("bridge_activity_contact", "contact_id", "dim_contacts", "contact_id"),
    ("bridge_activity_company", "activity_id", "fact_activities", "activity_id"),
    ("bridge_activity_company", "company_id", "dim_companies", "company_id"),
    ("bridge_activity_deal", "activity_id", "fact_activities", "activity_id"),
    ("bridge_activity_deal", "deal_id", "dim_deals", "deal_id"),
]


# dq_metrics depends only on silver tables that actually exist on this portal.
# Listing disabled assets as deps would cause Dagster to re-materialize them as
# external source-asset stubs in the graph (which is what the user sees as
# "leads still showing in Dagster after disabling").
_DQ_DEP_TABLES = [
    t for t in _ALL_SILVER_DIM_ASSETS_FULL + _ALL_SILVER_FACT_ASSETS_FULL + _ALL_SILVER_BRIDGE_ASSETS_FULL
    if t in _ext.get_enabled_silver_tables()
]


@asset(
    name="dq_metrics",
    group_name="silver",
    deps=[AssetKey(t) for t in _DQ_DEP_TABLES],
)
def dq_metrics(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    context.log.info("Running data quality checks")

    enabled_tables = set(_enabled_silver_dq_tables())
    context.log.info(f"DQ scope: {sorted(enabled_tables)}")

    # Create table if not exists (never drop)
    ch_silver.execute_sql("""
CREATE TABLE IF NOT EXISTS silver.dq_metrics (
    measured_at DateTime,
    table_name LowCardinality(String),
    metric_name LowCardinality(String),
    metric_value Float64,
    detail String
) ENGINE = MergeTree() ORDER BY (table_name, metric_name, measured_at) TTL measured_at + INTERVAL 90 DAY
""".strip())

    metrics = []

    # Row counts — only for tables that actually exist on this portal
    for table in sorted(enabled_tables):
        try:
            count = int(ch_silver.execute_sql(f"SELECT count() FROM silver.{table}"))
        except Exception:
            count = 0
        metrics.append(f"(now(), '{table}', 'row_count', {count}, '')")

    # Null rate checks for dims (skip if dim is disabled)
    null_checks = [
        ("dim_contacts", "email", "null_rate_email"),
        ("dim_companies", "name", "null_rate_name"),
        ("dim_deals", "dealname", "null_rate_dealname"),
    ]
    for table, col, metric_name in null_checks:
        if table not in enabled_tables:
            continue
        try:
            rate = float(ch_silver.execute_sql(
                f"SELECT countIf({col} = '') / count() FROM silver.{table}"
            ))
        except Exception:
            rate = 0.0
        metrics.append(f"(now(), '{table}', '{metric_name}', {rate}, '')")

    # Archived rate for enabled dim tables
    for table in _ALL_SILVER_DIM_ASSETS_FULL:
        if table not in enabled_tables:
            continue
        try:
            rate = float(ch_silver.execute_sql(
                f"SELECT countIf(archived = 1) / count() FROM silver.{table}"
            ))
        except Exception:
            rate = 0.0
        metrics.append(f"(now(), '{table}', 'archived_rate', {rate}, '')")

    # Orphan checks for bridges — skip any that reference a disabled table
    for bridge_table, bridge_col, dim_table, dim_col in _ALL_ORPHAN_CHECKS:
        if bridge_table not in enabled_tables or dim_table not in enabled_tables:
            continue
        try:
            count = int(ch_silver.execute_sql(
                f"SELECT count() FROM silver.{bridge_table} "
                f"WHERE {bridge_col} NOT IN (SELECT {dim_col} FROM silver.{dim_table})"
            ))
        except Exception:
            count = 0
        metrics.append(
            f"(now(), '{bridge_table}', 'orphan_count_{bridge_col}', {count}, "
            f"'{bridge_col} NOT IN {dim_table}.{dim_col}')"
        )

    # Insert all metrics
    if metrics:
        values = ",\n".join(metrics)
        ch_silver.execute_sql(
            f"INSERT INTO silver.dq_metrics VALUES {values}"
        )

    total_metrics = len(metrics)
    context.log.info(f"Inserted {total_metrics} DQ metrics")

    yield MaterializeResult(
        metadata={
            "metrics_count": MetadataValue.int(total_metrics),
        }
    )
