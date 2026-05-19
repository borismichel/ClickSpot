"""SQL helpers + dictionary lifecycle for silver assets.

Extracted from the old assets/silver.py monolith; the dim/fact/bridge/dq
submodules all import from here. Public symbols (_cast_expr, _build_ddl,
_build_insert) are re-exported from assets.silver.__init__ so the existing
tests/test_silver_assets.py imports keep working.
"""

from resources.clickhouse import ClickHouseResource
from silver_config import DICTIONARIES



# ---------------------------------------------------------------------------
# Helpers: dictionary lifecycle + atomic table swap
# ---------------------------------------------------------------------------

def _drop_dependent_dicts(table_name: str, ch: ClickHouseResource, log) -> list[str]:
    """Drop dictionaries that depend on this table. Returns list of dict names dropped."""
    if table_name not in DICTIONARIES:
        return []
    dict_name = "dict_" + table_name.removeprefix("dim_")
    log.info(f"Dropping dependent dictionary silver.{dict_name}")
    ch.execute_sql(f"DROP DICTIONARY IF EXISTS silver.{dict_name}")
    return [table_name]


def _recreate_dicts(table_names: list[str], ch: ClickHouseResource, log):
    """Recreate dictionaries for the given table names."""
    for table_name in table_names:
        ddl = DICTIONARIES.get(table_name)
        if ddl:
            dict_name = "dict_" + table_name.removeprefix("dim_")
            log.info(f"Recreating dictionary silver.{dict_name}")
            ch.execute_sql(ddl.strip())


def _swap_table(ch: ClickHouseResource, table: str, log):
    """Atomic swap: silver.{table}_tmp -> silver.{table}. Handles dict lifecycle."""
    tmp = f"{table}_tmp"
    # Ensure target exists (first run) — same schema as tmp
    ch.execute_sql(f"CREATE TABLE IF NOT EXISTS silver.{table} AS silver.{tmp}")
    # Drop dependent dicts before swap
    dropped = _drop_dependent_dicts(table, ch, log)
    # Atomic swap — zero downtime
    log.info(f"EXCHANGE TABLES silver.{table} AND silver.{tmp}")
    ch.execute_sql(f"EXCHANGE TABLES silver.{table} AND silver.{tmp}")
    ch.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")
    # Recreate dicts pointing at new data
    _recreate_dicts(dropped, ch, log)


# ---------------------------------------------------------------------------
# Helpers: SQL generation from config
# ---------------------------------------------------------------------------

def _cast_expr(prop_key: str, ch_type: str, source: str = "properties") -> str:
    """Generate a ClickHouse SELECT expression with type casting."""
    if source == "json":
        raw_expr = f"JSONExtractString(_raw, '{prop_key}')"
    else:
        raw_expr = f"properties['{prop_key}']"

    # Strip LowCardinality wrapper — casting is the same, encoding handled by DDL
    inner_type = ch_type
    if ch_type.startswith("LowCardinality("):
        inner_type = ch_type[len("LowCardinality("):-1]

    if inner_type == "String":
        return raw_expr
    elif inner_type == "DateTime":
        return f"parseDateTimeBestEffortOrZero({raw_expr})"
    elif inner_type == "Nullable(Float64)":
        return f"toFloat64OrNull({raw_expr})"
    elif inner_type == "UInt32":
        return f"toUInt32OrZero({raw_expr})"
    elif inner_type == "Nullable(Int64)":
        return f"toInt64OrNull({raw_expr})"
    else:
        return raw_expr


def _build_ddl(
    table_name: str,
    primary_key: str,
    columns: list,
    source: str = "properties",
    *,
    order_by: str | None = None,
    partition_by: str | None = None,
    indexes: list[str] | None = None,
) -> str:
    """Build CREATE TABLE DDL from config."""
    col_defs = [f"    {primary_key} String"]

    if source == "nested_stages":
        # columns are (name, type) tuples for nested_stages
        for col_name, col_type in columns:
            col_defs.append(f"    {col_name} {col_type}")
    else:
        # columns are (name, prop_key, type) tuples
        for col_name, _prop_key, col_type in columns:
            col_defs.append(f"    {col_name} {col_type}")

    col_defs.append("    archived UInt8")
    col_defs.append("    _silver_loaded_at DateTime DEFAULT now()")

    for idx in indexes or []:
        col_defs.append(f"    {idx}")

    cols_sql = ",\n".join(col_defs)
    order_clause = order_by or f"({primary_key})"
    partition_clause = f"PARTITION BY {partition_by} " if partition_by else ""
    return (
        f"CREATE TABLE silver.{table_name} (\n"
        f"{cols_sql}\n"
        f") ENGINE = ReplacingMergeTree(_silver_loaded_at) "
        f"{partition_clause}ORDER BY {order_clause}"
    )


def _build_insert(table_name: str, primary_key: str, config: dict) -> str:
    """Build INSERT INTO ... SELECT from bronze."""
    bronze_table = config["bronze_table"]
    source = config.get("source", "properties")
    columns = config["columns"]

    select_exprs = [f"    _record_id AS {primary_key}"]

    if source == "properties":
        for col_name, prop_key, col_type in columns:
            expr = _cast_expr(prop_key, col_type, "properties")
            select_exprs.append(f"    {expr} AS {col_name}")
    elif source == "json":
        for col_name, json_key, col_type in columns:
            expr = _cast_expr(json_key, col_type, "json")
            select_exprs.append(f"    {expr} AS {col_name}")

    select_exprs.append("    JSONExtractBool(_raw, 'archived') AS archived")
    select_exprs.append("    now() AS _silver_loaded_at")

    select_sql = ",\n".join(select_exprs)
    return (
        f"INSERT INTO silver.{table_name}\n"
        f"SELECT\n{select_sql}\n"
        f"FROM bronze.{bronze_table} FINAL"
    )


