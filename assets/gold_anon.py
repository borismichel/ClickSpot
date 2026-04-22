"""Gold-anon layer — column-for-column copy of gold.* with PII masked.

Reads from gold.*, writes to gold_anon.*. No silver/bronze dependencies.
Purely additive — the main gold pipeline is unaffected if this job fails.
"""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from app.engine.anon_masking import mask_column
from resources.clickhouse import ClickHouseResource
from silver_config import ANON_PII_COLUMNS

ANON_DB = "gold_anon"
SRC_DB = "gold"

# All gold tables are cloned. Only agg_deal_health.dealname and
# agg_lead_health.lead_name carry PII (per ANON_PII_COLUMNS); the rest are
# owner/label/metric-only.
_ANON_TABLES = [
    "agg_deal_stage_funnel",
    "agg_deal_health",
    "agg_rep_performance",
    "agg_source_attribution",
    "agg_lead_health",
    "agg_deal_cohorts",
    "fact_pipeline_snapshots",
]


def _supports_final(client, db: str, table: str) -> bool:
    """True if the source table's engine supports FROM ... FINAL.

    Only the Replacing/Collapsing/Summing/Aggregating/VersionedCollapsing
    MergeTree variants honor FINAL. Plain MergeTree (used by append-only
    fact_pipeline_snapshots) raises ILLEGAL_FINAL.
    """
    res = client.query(
        "SELECT engine FROM system.tables "
        "WHERE database = %(db)s AND name = %(table)s",
        parameters={"db": db, "table": table},
    )
    if not res.result_rows:
        return False
    engine = res.result_rows[0][0] or ""
    return any(
        marker in engine
        for marker in ("Replacing", "Collapsing", "Summing", "Aggregating")
    )


def _swap_anon_table(ch: ClickHouseResource, table: str, log):
    tmp = f"{table}_tmp"
    ch.execute_sql(f"CREATE TABLE IF NOT EXISTS {ANON_DB}.{table} AS {ANON_DB}.{tmp}")
    log.info(f"EXCHANGE TABLES {ANON_DB}.{table} AND {ANON_DB}.{tmp}")
    ch.execute_sql(f"EXCHANGE TABLES {ANON_DB}.{table} AND {ANON_DB}.{tmp}")
    ch.execute_sql(f"DROP TABLE IF EXISTS {ANON_DB}.{tmp}")


def _make_anon_gold_asset(table: str):
    """Create a Dagster asset that rebuilds gold_anon.<table> from gold.<table>."""

    @asset(
        name=f"anon_{table}",
        group_name="gold_anon",
        deps=[AssetKey(table)],
    )
    def _asset(context: AssetExecutionContext, ch_gold_anon: ClickHouseResource):
        tmp = f"{table}_tmp"

        context.log.info(f"Rebuilding {ANON_DB}.{table}")
        ch_gold_anon.execute_sql(f"DROP TABLE IF EXISTS {ANON_DB}.{tmp}")

        ch_gold_anon.execute_sql(f"CREATE TABLE {ANON_DB}.{tmp} AS {SRC_DB}.{table}")

        client = ch_gold_anon.get_client()
        desc = client.query(f"DESCRIBE TABLE {SRC_DB}.{table}").result_rows
        cols = [r[0] for r in desc]

        pii_map = {name: kind for name, kind in ANON_PII_COLUMNS.get(table, [])}
        select_exprs = []
        for col in cols:
            if col in pii_map:
                select_exprs.append(f"    {mask_column(col, pii_map[col])} AS {col}")
            else:
                select_exprs.append(f"    {col}")
        select_sql = ",\n".join(select_exprs)

        final_clause = " FINAL" if _supports_final(client, SRC_DB, table) else ""
        insert_sql = (
            f"INSERT INTO {ANON_DB}.{tmp}\n"
            f"SELECT\n{select_sql}\n"
            f"FROM {SRC_DB}.{table}{final_clause}"
        )
        context.log.info(f"INSERT: {insert_sql}")
        ch_gold_anon.execute_sql(insert_sql)

        _swap_anon_table(ch_gold_anon, table, context.log)

        row_count = ch_gold_anon.execute_sql(f"SELECT count() FROM {ANON_DB}.{table}")
        context.log.info(f"{ANON_DB}.{table}: {row_count} rows")

        yield MaterializeResult(metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text(f"{ANON_DB}.{table}"),
        })

    return _asset


_anon_assets = {t: _make_anon_gold_asset(t) for t in _ANON_TABLES}

anon_agg_deal_stage_funnel = _anon_assets["agg_deal_stage_funnel"]
anon_agg_deal_health = _anon_assets["agg_deal_health"]
anon_agg_rep_performance = _anon_assets["agg_rep_performance"]
anon_agg_source_attribution = _anon_assets["agg_source_attribution"]
anon_agg_lead_health = _anon_assets["agg_lead_health"]
anon_agg_deal_cohorts = _anon_assets["agg_deal_cohorts"]
anon_fact_pipeline_snapshots = _anon_assets["fact_pipeline_snapshots"]


all_gold_anon_assets = list(_anon_assets.values())
