"""Silver bridge assets: simple CRM↔CRM bridges + the three bridge_activity_*
unions across activity types.

bridge_activity_{contact,company,deal} compute their deps + UNION ALL source
list dynamically against app.customer.extraction so disabled activity types
don't leak into the asset graph.
"""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource
from silver_config import (
    BRIDGE_TABLES,
    BRIDGE_ACTIVITY_CONTACT, BRIDGE_ACTIVITY_COMPANY, BRIDGE_ACTIVITY_DEAL,
)
from app.customer import extraction as _ext
from .sql import _swap_table


# ---------------------------------------------------------------------------
# Bridge factories
# ---------------------------------------------------------------------------

def _make_bridge_asset(silver_table: str, bronze_table: str, from_key: str, to_key: str):
    @asset(
        name=silver_table,
        group_name="silver",
        deps=[AssetKey(bronze_table)],
    )
    def _asset(context: AssetExecutionContext, ch_silver: ClickHouseResource):
        target = silver_table
        tmp = f"{target}_tmp"

        context.log.info(f"Rebuilding silver.{target}")
        ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

        ddl = f"""
CREATE TABLE silver.{tmp} (
    {from_key} String,
    {to_key} String,
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY ({from_key}, {to_key})
""".strip()
        ch_silver.execute_sql(ddl)

        insert_sql = f"""
INSERT INTO silver.{tmp}
SELECT DISTINCT
    _from_id AS {from_key},
    _to_id AS {to_key},
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL
""".strip()
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


# Create bridge assets from config
_bridge_assets = {
    silver_table: _make_bridge_asset(silver_table, bronze_table, from_key, to_key)
    for silver_table, bronze_table, from_key, to_key in BRIDGE_TABLES
}
bridge_contact_company = _bridge_assets["bridge_contact_company"]
bridge_contact_deal = _bridge_assets["bridge_contact_deal"]
bridge_deal_company = _bridge_assets["bridge_deal_company"]
bridge_lead_contact = _bridge_assets["bridge_lead_contact"]
bridge_deal_lead = _bridge_assets["bridge_deal_lead"]
bridge_lead_company = _bridge_assets["bridge_lead_company"]
bridge_list_contact = _bridge_assets["bridge_list_contact"]
bridge_list_company = _bridge_assets["bridge_list_company"]
bridge_list_deal = _bridge_assets["bridge_list_deal"]
bridge_list_lead = _bridge_assets["bridge_list_lead"]


# ---------------------------------------------------------------------------
# Special bridge: bridge_activity_contact (UNION ALL across 5 assoc tables)
# ---------------------------------------------------------------------------

def _bridge_activity_deps(activity_list):
    enabled_assoc = _ext.get_enabled_assoc_tables()
    return [AssetKey(t) for _, t in activity_list if t in enabled_assoc]


def _enabled_bridge_activity(activity_list):
    enabled_assoc = _ext.get_enabled_assoc_tables()
    return [(at, t) for at, t in activity_list if t in enabled_assoc]


@asset(
    name="bridge_activity_contact",
    group_name="silver",
    deps=_bridge_activity_deps(BRIDGE_ACTIVITY_CONTACT),
)
def bridge_activity_contact(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "bridge_activity_contact"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.bridge_activity_contact")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = f"""
CREATE TABLE silver.{tmp} (
    activity_id String,
    activity_type LowCardinality(String),
    contact_id String,
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY (activity_id, contact_id)
""".strip()
    ch_silver.execute_sql(ddl)

    union_parts = []
    for activity_type, bronze_table in _enabled_bridge_activity(BRIDGE_ACTIVITY_CONTACT):
        part = f"""SELECT
    _from_id AS activity_id,
    '{activity_type}' AS activity_type,
    _to_id AS contact_id,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = f"INSERT INTO silver.{tmp}\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.bridge_activity_contact")
    context.log.info(f"silver.bridge_activity_contact: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.bridge_activity_contact"),
        }
    )


# ---------------------------------------------------------------------------
# Special bridge: bridge_activity_company (UNION ALL across 5 assoc tables)
# ---------------------------------------------------------------------------

@asset(
    name="bridge_activity_company",
    group_name="silver",
    deps=_bridge_activity_deps(BRIDGE_ACTIVITY_COMPANY),
)
def bridge_activity_company(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "bridge_activity_company"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.bridge_activity_company")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = f"""
CREATE TABLE silver.{tmp} (
    activity_id String,
    activity_type LowCardinality(String),
    company_id String,
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY (activity_id, company_id)
""".strip()
    ch_silver.execute_sql(ddl)

    union_parts = []
    for activity_type, bronze_table in _enabled_bridge_activity(BRIDGE_ACTIVITY_COMPANY):
        part = f"""SELECT
    _from_id AS activity_id,
    '{activity_type}' AS activity_type,
    _to_id AS company_id,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = f"INSERT INTO silver.{tmp}\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.bridge_activity_company")
    context.log.info(f"silver.bridge_activity_company: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.bridge_activity_company"),
        }
    )


# ---------------------------------------------------------------------------
# Special bridge: bridge_activity_deal (UNION ALL across 5 assoc tables)
# ---------------------------------------------------------------------------

@asset(
    name="bridge_activity_deal",
    group_name="silver",
    deps=_bridge_activity_deps(BRIDGE_ACTIVITY_DEAL),
)
def bridge_activity_deal(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "bridge_activity_deal"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.bridge_activity_deal")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = f"""
CREATE TABLE silver.{tmp} (
    activity_id String,
    activity_type LowCardinality(String),
    deal_id String,
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY (activity_id, deal_id)
""".strip()
    ch_silver.execute_sql(ddl)

    union_parts = []
    for activity_type, bronze_table in _enabled_bridge_activity(BRIDGE_ACTIVITY_DEAL):
        part = f"""SELECT
    _from_id AS activity_id,
    '{activity_type}' AS activity_type,
    _to_id AS deal_id,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = f"INSERT INTO silver.{tmp}\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.bridge_activity_deal")
    context.log.info(f"silver.bridge_activity_deal: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.bridge_activity_deal"),
        }
    )

