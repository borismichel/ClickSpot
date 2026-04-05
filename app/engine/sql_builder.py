"""SQL generation for the associative engine.

Builds ClickHouse SQL from selection state and graph traversal results.
All values are parameterized via f-strings with proper escaping.
"""

from app.config import TABLES

# Allowed aggregation function names (prevents SQL injection)
_ALLOWED_AGGS = {"sum", "count", "avg", "min", "max", "median", "any", "uniq", "uniqExact"}

# Gold tables don't have archived column or use ReplacingMergeTree
_GOLD_TABLES = {t for t, m in TABLES.items() if m.get("database") == "gold"}

# ClickHouse time-bucketing functions by granularity
_TIME_BUCKETS = {
    "day": "toDate",
    "week": "toStartOfWeek",
    "month": "toStartOfMonth",
    "quarter": "toStartOfQuarter",
    "year": "toStartOfYear",
}


def _table_ref(table: str) -> str:
    """Return the fully qualified table reference (database.table)."""
    meta = TABLES.get(table, {})
    db = meta.get("database", "silver")
    return f"{db}.{table}"


def _table_final(table: str) -> str:
    """Return 'FINAL' for silver tables, empty string for gold (MergeTree)."""
    return "" if table in _GOLD_TABLES else "FINAL"


def _archived_condition(table: str) -> str:
    """Return 'archived = 0' for silver tables, '1' (always true) for gold."""
    return "1" if table in _GOLD_TABLES else "archived = 0"


def escape_value(v: str) -> str:
    """Escape a string value for ClickHouse SQL."""
    return v.replace("\\", "\\\\").replace("'", "\\'")


def build_where_clause(table: str, filters: dict[str, list[str]]) -> str:
    """Build a WHERE clause from {column: [values]} filters.

    Within a column: OR (any of the values).
    Across columns: AND.
    Excludes archived records for silver tables.
    """
    conditions = [_archived_condition(table)]

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
    final = _table_final(table)
    return f"SELECT {pk} FROM {_table_ref(table)} {final} WHERE {where}".replace("  ", " ")


def build_bridge_traversal(
    source_ids_sql: str,
    bridge: str,
    source_key: str,
    target_key: str,
) -> str:
    """Build SQL to traverse a bridge table from source IDs to target IDs."""
    return (
        f"SELECT DISTINCT {target_key} FROM {_table_ref(bridge)} "
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
    t_final = _table_final(target_table)
    s_final = _table_final(source_table)
    return (
        f"SELECT DISTINCT {target_col} FROM {_table_ref(target_table)} {t_final} "
        f"WHERE {target_col} IN ("
        f"SELECT {source_col} FROM {_table_ref(source_table)} {s_final} "
        f"WHERE {TABLES[source_table]['primary_key']} IN ({source_ids_sql})"
        f")"
    ).replace("  ", " ")


def build_count_query(table: str, pk: str, id_filter_sql: str | None = None) -> str:
    """Build a count query, optionally filtered by an ID set."""
    ref = _table_ref(table)
    final = _table_final(table)
    archived = _archived_condition(table)
    if id_filter_sql:
        return (
            f"SELECT count() FROM {ref} {final} "
            f"WHERE {pk} IN ({id_filter_sql}) AND {archived}"
        ).replace("  ", " ")
    return f"SELECT count() FROM {ref} {final} WHERE {archived}".replace("  ", " ")


def build_field_values_query(
    table: str,
    column: str,
    pk: str,
    id_filter_sql: str | None = None,
    limit: int = 200,
) -> str:
    """Build query to get distinct values + counts for a field, optionally filtered."""
    ref = _table_ref(table)
    final = _table_final(table)
    archived = _archived_condition(table)
    if id_filter_sql:
        return (
            f"SELECT {column} AS value, count() AS cnt "
            f"FROM {ref} {final} "
            f"WHERE {pk} IN ({id_filter_sql}) AND {archived} "
            f"GROUP BY {column} ORDER BY cnt DESC LIMIT {limit}"
        ).replace("  ", " ")
    return (
        f"SELECT {column} AS value, count() AS cnt "
        f"FROM {ref} {final} "
        f"WHERE {archived} "
        f"GROUP BY {column} ORDER BY cnt DESC LIMIT {limit}"
    ).replace("  ", " ")


def build_measure_query(
    table: str,
    column: str,
    agg: str,
    pk: str,
    id_filter_sql: str | None = None,
) -> str:
    """Build an aggregate measure query."""
    ref = _table_ref(table)
    final = _table_final(table)
    archived = _archived_condition(table)
    agg_expr = f"{agg}({column})" if column != pk else "count()"
    if id_filter_sql:
        return (
            f"SELECT {agg_expr} FROM {ref} {final} "
            f"WHERE {pk} IN ({id_filter_sql}) AND {archived}"
        ).replace("  ", " ")
    return f"SELECT {agg_expr} FROM {ref} {final} WHERE {archived}".replace("  ", " ")


def build_list_query(
    table: str,
    columns: list[str],
    pk: str,
    id_filter_sql: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> str:
    """Build a list query returning rows, optionally filtered by ID set."""
    ref = _table_ref(table)
    final = _table_final(table)
    archived = _archived_condition(table)
    cols = ", ".join([pk] + columns)
    where = f"{pk} IN ({id_filter_sql}) AND {archived}" if id_filter_sql else archived
    return (
        f"SELECT {cols} FROM {ref} {final} "
        f"WHERE {where} "
        f"LIMIT {limit} OFFSET {offset}"
    ).replace("  ", " ")


def build_list_count_query(
    table: str,
    pk: str,
    id_filter_sql: str | None = None,
) -> str:
    """Build a count query for list total."""
    ref = _table_ref(table)
    final = _table_final(table)
    archived = _archived_condition(table)
    where = f"{pk} IN ({id_filter_sql}) AND {archived}" if id_filter_sql else archived
    return f"SELECT count() FROM {ref} {final} WHERE {where}".replace("  ", " ")


# ---------------------------------------------------------------------------
# Extension: Conditional aggregates
# ---------------------------------------------------------------------------

def build_conditional_measure_query(
    table: str,
    column: str,
    agg: str,
    condition: str,
    pk: str,
    id_filter_sql: str | None = None,
) -> str:
    """Build a conditional aggregate (sumIf, countIf, etc.)."""
    ref = _table_ref(table)
    final = _table_final(table)
    archived = _archived_condition(table)
    if agg not in _ALLOWED_AGGS:
        raise ValueError(f"Disallowed aggregation function: {agg}")

    if column == pk or agg == "count":
        agg_expr = f"countIf({condition})"
    else:
        agg_expr = f"{agg}If({column}, {condition})"

    where = f"{pk} IN ({id_filter_sql}) AND {archived}" if id_filter_sql else archived
    return f"SELECT {agg_expr} FROM {ref} {final} WHERE {where}".replace("  ", " ")


# ---------------------------------------------------------------------------
# Extension: Grouped measures (GROUP BY)
# ---------------------------------------------------------------------------

_DATE_COLUMNS_DEFAULT = {
    "dim_deals": "closedate",
    "dim_contacts": "createdate",
    "dim_leads": "createdate",
    "fact_activities": "hs_timestamp",
}


def build_grouped_measure_query(
    table: str,
    column: str,
    agg: str,
    group_by: list[str],
    pk: str,
    id_filter_sql: str | None = None,
    limit: int = 50,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Build an aggregate measure grouped by one or more columns."""
    ref = _table_ref(table)
    final = _table_final(table)
    if agg not in _ALLOWED_AGGS:
        raise ValueError(f"Disallowed aggregation function: {agg}")

    agg_expr = f"{agg}({column})" if column != pk else "count()"
    group_cols = ", ".join(group_by)

    conditions = [_archived_condition(table)]
    if id_filter_sql:
        conditions.append(f"{pk} IN ({id_filter_sql})")
    if date_from or date_to:
        date_col = _DATE_COLUMNS_DEFAULT.get(table)
        if date_col:
            if date_from:
                conditions.append(f"{date_col} >= '{escape_value(date_from)}'")
            if date_to:
                conditions.append(f"{date_col} <= '{escape_value(date_to)}'")
            conditions.append(f"{date_col} > '1970-01-02'")

    where = " AND ".join(conditions)
    return (
        f"SELECT {group_cols}, {agg_expr} AS value "
        f"FROM {ref} {final} "
        f"WHERE {where} "
        f"GROUP BY {group_cols} "
        f"ORDER BY value DESC "
        f"LIMIT {limit}"
    ).replace("  ", " ")


# ---------------------------------------------------------------------------
# Extension: Time-series bucketing
# ---------------------------------------------------------------------------

def build_time_series_query(
    table: str,
    measure_column: str,
    agg: str,
    date_column: str,
    granularity: str,
    pk: str,
    id_filter_sql: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> str:
    """Build a time-series query bucketed by date period."""
    ref = _table_ref(table)
    if agg not in _ALLOWED_AGGS:
        raise ValueError(f"Disallowed aggregation function: {agg}")
    if granularity not in _TIME_BUCKETS:
        raise ValueError(f"Unknown granularity: {granularity}")

    bucket_fn = _TIME_BUCKETS[granularity]
    final = _table_final(table)
    agg_expr = f"{agg}({measure_column})" if measure_column != pk else "count()"

    conditions = [_archived_condition(table)]
    if id_filter_sql:
        conditions.append(f"{pk} IN ({id_filter_sql})")
    if date_from:
        conditions.append(f"{date_column} >= '{escape_value(date_from)}'")
    if date_to:
        conditions.append(f"{date_column} <= '{escape_value(date_to)}'")
    # Exclude zero dates
    conditions.append(f"{date_column} > '1970-01-02'")

    where = " AND ".join(conditions)
    return (
        f"SELECT {bucket_fn}({date_column}) AS period, {agg_expr} AS value "
        f"FROM {ref} {final} "
        f"WHERE {where} "
        f"GROUP BY period "
        f"ORDER BY period"
    ).replace("  ", " ")
