"""Silver dim assets — factory-built + the hand-written exceptions.

Hand-written ones (dim_deals, dim_pipeline_stages, dim_lead_pipeline_stages)
either denormalize labels via dictGet or use ARRAY JOIN over nested stages.
Everything else flows through _make_dim_asset.
"""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource
from silver_config import (
    DIM_CONTACTS, DIM_COMPANIES, DIM_DEALS, DIM_LEADS,
    DIM_OWNERS, DIM_PIPELINES, DIM_PIPELINE_STAGES,
    DIM_LEAD_PIPELINES, DIM_LEAD_PIPELINE_STAGES,
)
from .sql import _build_ddl, _build_insert, _cast_expr, _swap_table


# ---------------------------------------------------------------------------
# Factory: dimension assets
# ---------------------------------------------------------------------------

CHUNK_SIZE = 50_000


def _make_dim_asset(name: str, config: dict):
    bronze_table = config["bronze_table"]
    primary_key = config["primary_key"]
    source = config.get("source", "properties")

    @asset(
        name=f"dim_{name}",
        group_name="silver",
        deps=[AssetKey(bronze_table)],
    )
    def _asset(context: AssetExecutionContext, ch_silver: ClickHouseResource):
        target = f"dim_{name}"
        tmp = f"{target}_tmp"

        context.log.info(f"Rebuilding silver.{target}")
        ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

        ddl = _build_ddl(tmp, primary_key, config["columns"], source,
                         order_by=config.get("order_by"),
                         partition_by=config.get("partition_by"),
                         indexes=config.get("indexes"))
        context.log.info(f"DDL: {ddl}")
        ch_silver.execute_sql(ddl)

        # Count unique bronze records to decide chunking (not total rows which includes dupes)
        bronze_count = int(ch_silver.execute_sql(
            f"SELECT uniq(_record_id) FROM bronze.{bronze_table}"
        ))
        context.log.info(f"Bronze {bronze_table}: {bronze_count} unique records")

        insert_sql = _build_insert(tmp, primary_key, config)

        context.log.info(f"INSERT: {insert_sql}")
        ch_silver.execute_sql(insert_sql)

        # Atomic swap
        _swap_table(ch_silver, target, context.log)

        row_count = ch_silver.execute_sql(f"SELECT count() FROM silver.{target}")
        context.log.info(f"silver.{target}: {row_count} rows")

        yield MaterializeResult(
            metadata={
                "row_count": MetadataValue.int(int(row_count)),
                "table": MetadataValue.text(f"silver.{target}"),
            }
        )

    return _asset


# Create standard dim assets
dim_contacts = _make_dim_asset("contacts", DIM_CONTACTS)
dim_companies = _make_dim_asset("companies", DIM_COMPANIES)
dim_leads = _make_dim_asset("leads", DIM_LEADS)
dim_owners = _make_dim_asset("owners", DIM_OWNERS)
dim_pipelines = _make_dim_asset("pipelines", DIM_PIPELINES)
dim_lead_pipelines = _make_dim_asset("lead_pipelines", DIM_LEAD_PIPELINES)


# ---------------------------------------------------------------------------
# Custom dim_deals: standard columns + denormalized labels from lookups
# ---------------------------------------------------------------------------

@asset(
    name="dim_deals",
    group_name="silver",
    deps=[
        AssetKey("hs_deals"),
        AssetKey("dim_pipelines"),
        AssetKey("dim_pipeline_stages"),
        AssetKey("dim_owners"),
    ],
)
def dim_deals(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    """dim_deals with denormalized pipeline_label, stage_label, owner_name."""
    target = "dim_deals"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.dim_deals (with denormalized labels)")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    config = DIM_DEALS
    primary_key = config["primary_key"]
    columns = config["columns"]
    order_by = config.get("order_by", "(deal_id)")
    partition_by = config.get("partition_by")
    indexes = config.get("indexes", [])

    # Build DDL with extra label columns
    col_defs = [f"    {primary_key} String"]
    for col_name, _prop_key, col_type in columns:
        col_defs.append(f"    {col_name} {col_type}")
    col_defs.append("    pipeline_label String")
    col_defs.append("    stage_label String")
    col_defs.append("    owner_name String")
    col_defs.append("    archived UInt8")
    col_defs.append("    _silver_loaded_at DateTime DEFAULT now()")
    for idx in indexes:
        col_defs.append(f"    {idx}")

    partition_clause = f"PARTITION BY {partition_by} " if partition_by else ""
    ddl = (
        f"CREATE TABLE silver.{tmp} (\n"
        + ",\n".join(col_defs)
        + f"\n) ENGINE = ReplacingMergeTree(_silver_loaded_at) "
        + partition_clause
        + f"ORDER BY {order_by}"
    )
    ch_silver.execute_sql(ddl)

    # Build INSERT with dictGet() for denormalized labels (no JOINs)
    select_exprs = [f"    _record_id AS {primary_key}"]
    for col_name, prop_key, col_type in columns:
        expr = _cast_expr(prop_key, col_type, "properties")
        select_exprs.append(f"    {expr} AS {col_name}")
    select_exprs.append("    dictGet('silver.dict_pipelines', 'label', tuple(properties['pipeline'])) AS pipeline_label")
    select_exprs.append("    dictGet('silver.dict_pipeline_stages', 'label', tuple(properties['dealstage'])) AS stage_label")
    select_exprs.append(
        "    concat("
        "dictGet('silver.dict_owners', 'first_name', tuple(properties['hubspot_owner_id'])), "
        "' ', "
        "dictGet('silver.dict_owners', 'last_name', tuple(properties['hubspot_owner_id']))"
        ") AS owner_name"
    )
    select_exprs.append("    JSONExtractBool(_raw, 'archived') AS archived")
    select_exprs.append("    now() AS _silver_loaded_at")

    select_sql = ",\n".join(select_exprs)
    insert_sql = (
        f"INSERT INTO silver.{tmp}\n"
        f"SELECT\n{select_sql}\n"
        f"FROM bronze.hs_deals FINAL"
    )
    context.log.info(f"INSERT: {insert_sql}")
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.dim_deals")
    context.log.info(f"silver.dim_deals: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.dim_deals"),
        }
    )


# ---------------------------------------------------------------------------
# Special asset: dim_pipeline_stages (ARRAY JOIN)
# ---------------------------------------------------------------------------

@asset(
    name="dim_pipeline_stages",
    group_name="silver",
    deps=[AssetKey("hs_pipelines")],
)
def dim_pipeline_stages(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "dim_pipeline_stages"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.dim_pipeline_stages")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = _build_ddl(tmp, "stage_id", DIM_PIPELINE_STAGES["columns"], "nested_stages")
    context.log.info(f"DDL: {ddl}")
    ch_silver.execute_sql(ddl)

    insert_sql = f"""
INSERT INTO silver.{tmp}
SELECT
    JSONExtractString(stage, 'id') AS stage_id,
    _record_id AS pipeline_id,
    JSONExtractString(stage, 'label') AS label,
    toUInt32OrZero(JSONExtractString(stage, 'displayOrder')) AS display_order,
    JSONExtractString(stage, 'metadata', 'isClosed') AS is_closed,
    toFloat64OrNull(JSONExtractString(stage, 'metadata', 'probability')) AS probability,
    parseDateTimeBestEffortOrZero(JSONExtractString(stage, 'createdAt')) AS created_at,
    parseDateTimeBestEffortOrZero(JSONExtractString(stage, 'updatedAt')) AS updated_at,
    JSONExtractBool(_raw, 'archived') AS archived,
    now() AS _silver_loaded_at
FROM bronze.hs_pipelines FINAL
ARRAY JOIN JSONExtractArrayRaw(_raw, 'stages') AS stage
""".strip()
    context.log.info(f"INSERT: {insert_sql}")
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.dim_pipeline_stages")
    context.log.info(f"silver.dim_pipeline_stages: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.dim_pipeline_stages"),
        }
    )


# ---------------------------------------------------------------------------
# Special asset: dim_lead_pipeline_stages (ARRAY JOIN from lead pipelines)
# ---------------------------------------------------------------------------

@asset(
    name="dim_lead_pipeline_stages",
    group_name="silver",
    deps=[AssetKey("hs_lead_pipelines")],
)
def dim_lead_pipeline_stages(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "dim_lead_pipeline_stages"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.dim_lead_pipeline_stages")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = _build_ddl(tmp, "stage_id", DIM_LEAD_PIPELINE_STAGES["columns"], "nested_stages")
    ch_silver.execute_sql(ddl)

    insert_sql = f"""
INSERT INTO silver.{tmp}
SELECT
    JSONExtractString(stage, 'id') AS stage_id,
    _record_id AS pipeline_id,
    JSONExtractString(stage, 'label') AS label,
    toUInt32OrZero(JSONExtractString(stage, 'displayOrder')) AS display_order,
    JSONExtractString(stage, 'metadata', 'isClosed') AS is_closed,
    toFloat64OrNull(JSONExtractString(stage, 'metadata', 'probability')) AS probability,
    parseDateTimeBestEffortOrZero(JSONExtractString(stage, 'createdAt')) AS created_at,
    parseDateTimeBestEffortOrZero(JSONExtractString(stage, 'updatedAt')) AS updated_at,
    JSONExtractBool(_raw, 'archived') AS archived,
    now() AS _silver_loaded_at
FROM bronze.hs_lead_pipelines FINAL
ARRAY JOIN JSONExtractArrayRaw(_raw, 'stages') AS stage
""".strip()
    ch_silver.execute_sql(insert_sql)

    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.dim_lead_pipeline_stages")
    context.log.info(f"silver.dim_lead_pipeline_stages: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.dim_lead_pipeline_stages"),
        }
    )
