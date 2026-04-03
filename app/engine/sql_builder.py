"""SQL generation for the associative engine.

Builds ClickHouse SQL from selection state and graph traversal results.
All values are parameterized via f-strings with proper escaping.
"""

from app.config import TABLES


def escape_value(v: str) -> str:
    """Escape a string value for ClickHouse SQL."""
    return v.replace("\\", "\\\\").replace("'", "\\'")


def build_where_clause(table: str, filters: dict[str, list[str]]) -> str:
    """Build a WHERE clause from {column: [values]} filters.

    Within a column: OR (any of the values).
    Across columns: AND.
    Always excludes archived records.
    """
    conditions = ["archived = 0"]

    for col, values in filters.items():
        if len(values) == 1:
            conditions.append(f"{col} = '{escape_value(values[0])}'")
        else:
            escaped = ", ".join(f"'{escape_value(v)}'" for v in values)
            conditions.append(f"{col} IN ({escaped})")

    return " AND ".join(conditions)


def build_id_subquery(table: str, pk: str, filters: dict[str, list[str]]) -> str:
    """Build a subquery that returns the primary key IDs matching filters."""
    where = build_where_clause(table, filters)
    return f"SELECT {pk} FROM silver.{table} FINAL WHERE {where}"


def build_bridge_traversal(
    source_ids_sql: str,
    bridge: str,
    source_key: str,
    target_key: str,
) -> str:
    """Build SQL to traverse a bridge table from source IDs to target IDs."""
    return (
        f"SELECT DISTINCT {target_key} FROM silver.{bridge} "
        f"WHERE {source_key} IN ({source_ids_sql})"
    )


def build_fk_traversal(
    source_ids_sql: str,
    source_table: str,
    source_col: str,
    target_table: str,
    target_col: str,
) -> str:
    """Build SQL to traverse a direct FK relationship."""
    return (
        f"SELECT DISTINCT {target_col} FROM silver.{target_table} FINAL "
        f"WHERE {target_col} IN ("
        f"SELECT {source_col} FROM silver.{source_table} FINAL "
        f"WHERE {TABLES[source_table]['primary_key']} IN ({source_ids_sql})"
        f")"
    )


def build_count_query(table: str, pk: str, id_filter_sql: str | None = None) -> str:
    """Build a count query, optionally filtered by an ID set."""
    if id_filter_sql:
        return (
            f"SELECT count() FROM silver.{table} FINAL "
            f"WHERE {pk} IN ({id_filter_sql}) AND archived = 0"
        )
    return f"SELECT count() FROM silver.{table} FINAL WHERE archived = 0"


def build_field_values_query(
    table: str,
    column: str,
    pk: str,
    id_filter_sql: str | None = None,
    limit: int = 200,
) -> str:
    """Build query to get distinct values + counts for a field, optionally filtered."""
    if id_filter_sql:
        return (
            f"SELECT {column} AS value, count() AS cnt "
            f"FROM silver.{table} FINAL "
            f"WHERE {pk} IN ({id_filter_sql}) AND archived = 0 "
            f"GROUP BY {column} ORDER BY cnt DESC LIMIT {limit}"
        )
    return (
        f"SELECT {column} AS value, count() AS cnt "
        f"FROM silver.{table} FINAL "
        f"WHERE archived = 0 "
        f"GROUP BY {column} ORDER BY cnt DESC LIMIT {limit}"
    )


def build_measure_query(
    table: str,
    column: str,
    agg: str,
    pk: str,
    id_filter_sql: str | None = None,
) -> str:
    """Build an aggregate measure query."""
    agg_expr = f"{agg}({column})" if column != pk else f"count()"
    if id_filter_sql:
        return (
            f"SELECT {agg_expr} FROM silver.{table} FINAL "
            f"WHERE {pk} IN ({id_filter_sql}) AND archived = 0"
        )
    return f"SELECT {agg_expr} FROM silver.{table} FINAL WHERE archived = 0"


def build_list_query(
    table: str,
    columns: list[str],
    pk: str,
    id_filter_sql: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Build a list query returning rows, optionally filtered by ID set."""
    cols = ", ".join([pk] + columns)
    where = f"{pk} IN ({id_filter_sql}) AND archived = 0" if id_filter_sql else "archived = 0"
    return (
        f"SELECT {cols} FROM silver.{table} FINAL "
        f"WHERE {where} "
        f"LIMIT {limit} OFFSET {offset}"
    )


def build_list_count_query(
    table: str,
    pk: str,
    id_filter_sql: str | None = None,
) -> str:
    """Build a count query for list total."""
    where = f"{pk} IN ({id_filter_sql}) AND archived = 0" if id_filter_sql else "archived = 0"
    return f"SELECT count() FROM silver.{table} FINAL WHERE {where}"
