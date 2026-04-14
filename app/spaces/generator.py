"""Generate ClickHouse VIEW SQL from a DataSpaceConfig.

Produces CREATE OR REPLACE VIEW gold.ds_{id} AS SELECT ... statements
that join a grain entity with dimension entities via bridges or FKs.
No FINAL on silver tables (they use EXCHANGE TABLES, no duplicates).
"""

from __future__ import annotations

from app.spaces.config import (
    BridgeDimension,
    BridgeStrategy,
    ComputedColumn,
    DataSpaceConfig,
    DictDimension,
    FKDimension,
)


def _silver_source(entity: str, filter_expr: str | None) -> str:
    """Return a FROM-source expression for a silver table, optionally with WHERE.

    With filter: `(SELECT * FROM silver.X WHERE <filter>)`
    Without filter: `silver.X`
    Wrapping in a subquery lets users write filters with bare column names.
    """
    if filter_expr and filter_expr.strip():
        return f"(SELECT * FROM silver.{entity} WHERE {filter_expr.strip()})"
    return f"silver.{entity}"


def generate_view_sql(config: DataSpaceConfig) -> str:
    """Generate the full CREATE OR REPLACE VIEW statement."""
    select_parts: list[str] = []
    grain_source = _silver_source(config.grain.entity, config.grain.filter)
    from_clause: str = f"{grain_source} AS grain"
    join_clauses: list[str] = []

    # Grain columns — explicit AS alias so ClickHouse VIEW doesn't
    # preserve the "grain." prefix in the column name
    for col in config.grain.columns:
        select_parts.append(f"    grain.{col} AS {col}")

    # Grain PK (always included, first)
    select_parts.insert(0, f"    grain.{config.grain.key} AS {config.grain.key}")

    # Dimensions
    for i, dim in enumerate(config.dimensions):
        if isinstance(dim, BridgeDimension):
            alias = f"dim{i}"
            cols, join = _bridge_join(config.grain, dim, alias)
            select_parts.extend(cols)
            join_clauses.append(join)
        elif isinstance(dim, FKDimension):
            alias = f"fk{i}"
            cols, join = _fk_join(dim, alias)
            select_parts.extend(cols)
            join_clauses.append(join)
        elif isinstance(dim, DictDimension):
            cols = _dict_lookup(dim)
            select_parts.extend(cols)

    # Computed columns
    for comp in config.computed:
        select_parts.append(f"    {comp.expr} AS {comp.alias}")

    # Assemble
    select_sql = ",\n".join(select_parts)
    joins_sql = "\n".join(join_clauses)
    where_clause = f"\nWHERE {config.default_filter}" if config.default_filter else ""

    return (
        f"CREATE OR REPLACE VIEW {config.view_name} AS\n"
        f"SELECT\n{select_sql}\n"
        f"FROM {from_clause}\n"
        f"{joins_sql}"
        f"{where_clause}"
    ).rstrip()


def generate_select_sql(config: DataSpaceConfig) -> str:
    """Generate just the SELECT statement (for preview, without CREATE VIEW)."""
    full = generate_view_sql(config)
    prefix = f"CREATE OR REPLACE VIEW {config.view_name} AS\n"
    if full.startswith(prefix):
        return full[len(prefix):]
    return full


# ---------------------------------------------------------------------------
# Bridge join strategies
# ---------------------------------------------------------------------------

def _bridge_join(
    grain, dim: BridgeDimension, alias: str
) -> tuple[list[str], str]:
    """Generate SELECT columns and JOIN clause for a bridge dimension."""

    strategy = dim.strategy
    grain_key = grain.key

    if strategy == BridgeStrategy.one_to_one:
        return _bridge_one_to_one(grain_key, dim, alias)
    elif strategy == BridgeStrategy.any:
        return _bridge_any(grain_key, dim, alias)
    elif strategy == BridgeStrategy.latest:
        return _bridge_latest(grain_key, dim, alias)
    elif strategy == BridgeStrategy.aggregate:
        return _bridge_aggregate(grain_key, dim, alias)
    elif strategy == BridgeStrategy.fan_out:
        return _bridge_fan_out(grain_key, dim, alias)
    else:
        raise ValueError(f"Unknown bridge strategy: {strategy}")


def _bridge_one_to_one(
    grain_key: str, dim: BridgeDimension, alias: str
) -> tuple[list[str], str]:
    """FULL OUTER JOIN — 1:1 in practice (e.g. lead→deal)."""
    dim_cols = [f"b.{dim.bridge_grain_key}"]
    for col in dim.columns:
        dim_cols.append(f"d.{col}")

    select_cols = [
        f"    {alias}.{col} AS {dim.prefix}{col}" for col in dim.columns
    ]

    dim_source = _silver_source(dim.entity, dim.filter)
    subquery = (
        f"SELECT {', '.join(dim_cols)}\n"
        f"    FROM silver.{dim.bridge} AS b\n"
        f"    JOIN {dim_source} AS d"
        f" ON b.{dim.bridge_dim_key} = d.{dim.dim_key}"
    )

    join = (
        f"FULL OUTER JOIN (\n    {subquery}\n) AS {alias}"
        f" ON grain.{grain_key} = {alias}.{dim.bridge_grain_key}"
    )
    return select_cols, join


def _bridge_any(
    grain_key: str, dim: BridgeDimension, alias: str
) -> tuple[list[str], str]:
    """any() — pick one record per grain key (grain preserved)."""
    agg_cols = [f"any(d.{col}) AS {col}" for col in dim.columns]
    select_cols = [
        f"    {alias}.{col} AS {dim.prefix}{col}" for col in dim.columns
    ]

    dim_source = _silver_source(dim.entity, dim.filter)
    subquery = (
        f"SELECT b.{dim.bridge_grain_key}, {', '.join(agg_cols)}\n"
        f"    FROM silver.{dim.bridge} AS b\n"
        f"    JOIN {dim_source} AS d"
        f" ON b.{dim.bridge_dim_key} = d.{dim.dim_key}\n"
        f"    GROUP BY b.{dim.bridge_grain_key}"
    )

    join = (
        f"LEFT JOIN (\n    {subquery}\n) AS {alias}"
        f" ON grain.{grain_key} = {alias}.{dim.bridge_grain_key}"
    )
    return select_cols, join


def _bridge_latest(
    grain_key: str, dim: BridgeDimension, alias: str
) -> tuple[list[str], str]:
    """argMax(pk, timestamp) — most recent record per grain key."""
    ts = dim.timestamp_col
    # Get the latest dim PK per grain key, then join to get all columns
    latest_cols = [f"argMax(d.{col}, d.{ts}) AS {col}" for col in dim.columns]
    select_cols = [
        f"    {alias}.{col} AS {dim.prefix}{col}" for col in dim.columns
    ]

    dim_source = _silver_source(dim.entity, dim.filter)
    subquery = (
        f"SELECT b.{dim.bridge_grain_key}, {', '.join(latest_cols)}\n"
        f"    FROM silver.{dim.bridge} AS b\n"
        f"    JOIN {dim_source} AS d"
        f" ON b.{dim.bridge_dim_key} = d.{dim.dim_key}\n"
        f"    GROUP BY b.{dim.bridge_grain_key}"
    )

    join = (
        f"LEFT JOIN (\n    {subquery}\n) AS {alias}"
        f" ON grain.{grain_key} = {alias}.{dim.bridge_grain_key}"
    )
    return select_cols, join


def _bridge_aggregate(
    grain_key: str, dim: BridgeDimension, alias: str
) -> tuple[list[str], str]:
    """Aggregate expressions per grain key (count, sum, etc.)."""
    agg_exprs = dim.agg_expressions or []
    agg_parts = [f"{a['expr']} AS {a['alias']}" for a in agg_exprs]
    select_cols = [
        f"    {alias}.{a['alias']} AS {dim.prefix}{a['alias']}" for a in agg_exprs
    ]

    dim_source = _silver_source(dim.entity, dim.filter)
    subquery = (
        f"SELECT b.{dim.bridge_grain_key}, {', '.join(agg_parts)}\n"
        f"    FROM silver.{dim.bridge} AS b\n"
        f"    JOIN {dim_source} AS d"
        f" ON b.{dim.bridge_dim_key} = d.{dim.dim_key}\n"
        f"    GROUP BY b.{dim.bridge_grain_key}"
    )

    join = (
        f"LEFT JOIN (\n    {subquery}\n) AS {alias}"
        f" ON grain.{grain_key} = {alias}.{dim.bridge_grain_key}"
    )
    return select_cols, join


def _bridge_fan_out(
    grain_key: str, dim: BridgeDimension, alias: str
) -> tuple[list[str], str]:
    """Plain LEFT JOIN — rows multiply (fan-out, grain NOT preserved)."""
    select_cols = [
        f"    {alias}.{col} AS {dim.prefix}{col}" for col in dim.columns
    ]

    dim_source = _silver_source(dim.entity, dim.filter)
    join = (
        f"LEFT JOIN silver.{dim.bridge} AS {alias}_b"
        f" ON grain.{grain_key} = {alias}_b.{dim.bridge_grain_key}\n"
        f"LEFT JOIN {dim_source} AS {alias}"
        f" ON {alias}_b.{dim.bridge_dim_key} = {alias}.{dim.dim_key}"
    )
    return select_cols, join


# ---------------------------------------------------------------------------
# FK join
# ---------------------------------------------------------------------------

def _fk_join(dim: FKDimension, alias: str) -> tuple[list[str], str]:
    """Direct FK join (always 1:1, LEFT JOIN)."""
    select_cols = [
        f"    {alias}.{col} AS {dim.prefix}{col}" for col in dim.columns
    ]

    dim_source = _silver_source(dim.entity, dim.filter)
    join = (
        f"LEFT JOIN {dim_source} AS {alias}"
        f" ON grain.{dim.fk_from} = {alias}.{dim.fk_to}"
    )
    return select_cols, join


# ---------------------------------------------------------------------------
# Dict lookup (no JOIN — O(1) in-memory hash)
# ---------------------------------------------------------------------------

def _dict_lookup(dim: DictDimension) -> list[str]:
    """dictGet() lookups — no JOIN clause needed, just SELECT expressions."""
    return [
        f"    dictGet('silver.{dim.dict_name}', '{col}', {dim.key_expr}) AS {dim.prefix}{col}"
        for col in dim.columns
    ]
