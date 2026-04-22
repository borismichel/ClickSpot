"""Silver-anon layer — column-for-column copy of silver.* with PII masked.

Reads from silver.*, writes to silver_anon.*. No bronze dependencies.
Purely additive — the main silver pipeline is unaffected if this job fails.

Activity tables (fact_activities, bridge_activity_*) are NOT copied because
their free-text content cannot be reliably masked. The MCP layer queries
silver_anon / gold_anon so the LLM physically cannot retrieve raw PII.
"""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from app.engine.anon_masking import mask_column
from resources.clickhouse import ClickHouseResource
from silver_config import ANON_PII_COLUMNS, DICT_CONFIGS

ANON_DB = "silver_anon"
SRC_DB = "silver"

# Silver tables to clone into silver_anon. Activity tables are omitted on
# purpose — their text fields cannot be safely masked.
_ANON_TABLES = [
    "dim_contacts", "dim_companies", "dim_deals", "dim_leads",
    "dim_owners",
    "dim_pipelines", "dim_pipeline_stages",
    "dim_lead_pipelines", "dim_lead_pipeline_stages",
    "fact_form_submissions", "fact_stage_history",
    "bridge_contact_company", "bridge_contact_deal", "bridge_deal_company",
    "bridge_lead_contact", "bridge_deal_lead", "bridge_lead_company",
]


# ---------------------------------------------------------------------------
# Dictionary lifecycle — same pattern as silver.py but rooted in silver_anon
# ---------------------------------------------------------------------------

def _anon_dict_ddl(table_name: str, cfg: dict) -> str:
    """CREATE DICTIONARY DDL for silver_anon.<dict> reading silver_anon.<table>."""
    dict_name = "dict_" + table_name.removeprefix("dim_")
    col_defs = []
    for name, ch_type in cfg["keys"]:
        col_defs.append(f"    {name} {ch_type}")
    for entry in cfg["values"]:
        name, ch_type = entry[0], entry[1]
        col_defs.append(f"    {name} {ch_type}")
    cols_sql = ",\n".join(col_defs)
    pk_names = ", ".join(name for name, _ in cfg["keys"])
    layout = "COMPLEX_KEY_HASHED()" if len(cfg["keys"]) > 1 else "HASHED()"
    return (
        f"CREATE DICTIONARY IF NOT EXISTS {ANON_DB}.{dict_name} (\n"
        f"{cols_sql}\n"
        f") PRIMARY KEY {pk_names}\n"
        f"SOURCE(CLICKHOUSE(DB '{ANON_DB}' TABLE '{table_name}' "
        f"WHERE 'archived = 0' USER 'hs2ch' PASSWORD 'hs2ch'))\n"
        f"LIFETIME(MIN 300 MAX 600)\n"
        f"LAYOUT({layout})"
    )


def _supports_final(client, db: str, table: str) -> bool:
    """True if the source table's engine supports FROM ... FINAL.

    Only the Replacing/Collapsing/Summing/Aggregating MergeTree variants honor
    FINAL. Plain MergeTree raises ILLEGAL_FINAL.
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


def _drop_dependent_anon_dicts(table_name: str, ch: ClickHouseResource, log) -> list[str]:
    if table_name not in DICT_CONFIGS:
        return []
    dict_name = "dict_" + table_name.removeprefix("dim_")
    log.info(f"Dropping dependent dictionary {ANON_DB}.{dict_name}")
    ch.execute_sql(f"DROP DICTIONARY IF EXISTS {ANON_DB}.{dict_name}")
    return [table_name]


def _recreate_anon_dicts(table_names: list[str], ch: ClickHouseResource, log):
    for table_name in table_names:
        cfg = DICT_CONFIGS.get(table_name)
        if cfg:
            dict_name = "dict_" + table_name.removeprefix("dim_")
            log.info(f"Recreating dictionary {ANON_DB}.{dict_name}")
            ch.execute_sql(_anon_dict_ddl(table_name, cfg))


def _swap_anon_table(ch: ClickHouseResource, table: str, log):
    tmp = f"{table}_tmp"
    ch.execute_sql(f"CREATE TABLE IF NOT EXISTS {ANON_DB}.{table} AS {ANON_DB}.{tmp}")
    dropped = _drop_dependent_anon_dicts(table, ch, log)
    log.info(f"EXCHANGE TABLES {ANON_DB}.{table} AND {ANON_DB}.{tmp}")
    ch.execute_sql(f"EXCHANGE TABLES {ANON_DB}.{table} AND {ANON_DB}.{tmp}")
    ch.execute_sql(f"DROP TABLE IF EXISTS {ANON_DB}.{tmp}")
    _recreate_anon_dicts(dropped, ch, log)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_anon_table_asset(table: str):
    """Create a Dagster asset that rebuilds silver_anon.<table> from silver.<table>."""

    @asset(
        name=f"anon_{table}",
        group_name="silver_anon",
        deps=[AssetKey(table)],
    )
    def _asset(context: AssetExecutionContext, ch_silver_anon: ClickHouseResource):
        tmp = f"{table}_tmp"

        context.log.info(f"Rebuilding {ANON_DB}.{table}")
        ch_silver_anon.execute_sql(f"DROP TABLE IF EXISTS {ANON_DB}.{tmp}")

        # Clone schema (engine, ORDER BY, DEFAULT expressions all copied verbatim)
        ch_silver_anon.execute_sql(f"CREATE TABLE {ANON_DB}.{tmp} AS {SRC_DB}.{table}")

        # Enumerate source columns via DESCRIBE (returns name, type, default_type, ...)
        client = ch_silver_anon.get_client()
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
        ch_silver_anon.execute_sql(insert_sql)

        _swap_anon_table(ch_silver_anon, table, context.log)

        row_count = ch_silver_anon.execute_sql(f"SELECT count() FROM {ANON_DB}.{table}")
        context.log.info(f"{ANON_DB}.{table}: {row_count} rows")

        yield MaterializeResult(metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text(f"{ANON_DB}.{table}"),
        })

    return _asset


# Build one asset per anon table. Dict recreation is handled inside _swap.
_anon_assets = {t: _make_anon_table_asset(t) for t in _ANON_TABLES}

anon_dim_contacts = _anon_assets["dim_contacts"]
anon_dim_companies = _anon_assets["dim_companies"]
anon_dim_deals = _anon_assets["dim_deals"]
anon_dim_leads = _anon_assets["dim_leads"]
anon_dim_owners = _anon_assets["dim_owners"]
anon_dim_pipelines = _anon_assets["dim_pipelines"]
anon_dim_pipeline_stages = _anon_assets["dim_pipeline_stages"]
anon_dim_lead_pipelines = _anon_assets["dim_lead_pipelines"]
anon_dim_lead_pipeline_stages = _anon_assets["dim_lead_pipeline_stages"]
anon_fact_form_submissions = _anon_assets["fact_form_submissions"]
anon_fact_stage_history = _anon_assets["fact_stage_history"]
anon_bridge_contact_company = _anon_assets["bridge_contact_company"]
anon_bridge_contact_deal = _anon_assets["bridge_contact_deal"]
anon_bridge_deal_company = _anon_assets["bridge_deal_company"]
anon_bridge_lead_contact = _anon_assets["bridge_lead_contact"]
anon_bridge_deal_lead = _anon_assets["bridge_deal_lead"]
anon_bridge_lead_company = _anon_assets["bridge_lead_company"]


all_silver_anon_assets = list(_anon_assets.values())
