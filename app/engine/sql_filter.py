"""Rule-based SQL filter injection for dashboard global filters.

Parses SQL with sqlglot, identifies table references, and injects
WHERE conditions based on the dashboard filter state. No AI involved —
purely AST-based rewriting.
"""

import logging
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

log = logging.getLogger("app.sql_filter")

# ---------------------------------------------------------------------------
# Filter specification
# ---------------------------------------------------------------------------

@dataclass
class DashboardFilters:
    date_from: str | None = None
    date_to: str | None = None
    owner_ids: list[str] = field(default_factory=list)
    owner_names: list[str] = field(default_factory=list)
    pipeline_ids: list[str] = field(default_factory=list)
    pipeline_labels: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return (
            not self.date_from
            and not self.date_to
            and not self.owner_ids
            and not self.pipeline_ids
        )


# ---------------------------------------------------------------------------
# Table → filterable column registry
# ---------------------------------------------------------------------------

# Maps "database.table" to the column name for each filter dimension.
# None means the table doesn't have that dimension.
FILTER_COLUMNS: dict[str, dict[str, str | None]] = {
    # Silver dimensions
    "silver.dim_deals":          {"date": "closedate",    "owner": "hubspot_owner_id", "pipeline": "pipeline"},
    "silver.dim_contacts":       {"date": "createdate",   "owner": None,               "pipeline": None},
    "silver.dim_companies":      {"date": "createdate",   "owner": "hubspot_owner_id", "pipeline": None},
    "silver.dim_leads":          {"date": "createdate",   "owner": "hubspot_owner_id", "pipeline": "hs_pipeline"},
    "silver.fact_activities":    {"date": "hs_timestamp",  "owner": "hubspot_owner_id", "pipeline": None},
    "silver.fact_stage_history": {"date": "entered_at",    "owner": None,               "pipeline": "pipeline_id"},
    # Gold tables
    "gold.agg_rep_performance":     {"date": "period_start",   "owner": "owner_name",  "pipeline": None},
    "gold.agg_deal_health":         {"date": None,             "owner": "owner_name",  "pipeline": "pipeline_label"},
    "gold.agg_lead_health":         {"date": "createdate",     "owner": "owner_name",  "pipeline": "pipeline_label"},
    "gold.agg_deal_stage_funnel":   {"date": None,             "owner": None,          "pipeline": "pipeline_id"},
    "gold.fact_pipeline_snapshots": {"date": "snapshot_date",  "owner": None,          "pipeline": "pipeline"},
    "gold.agg_deal_cohorts":        {"date": "cohort_month",   "owner": None,          "pipeline": "pipeline"},
}

# Owner columns that use IDs (vs name strings)
_ID_OWNER_COLS = {"hubspot_owner_id"}


# ---------------------------------------------------------------------------
# AST node builders (safe — no user values parsed as SQL)
# ---------------------------------------------------------------------------

def _col_ref(col_name: str, alias: str | None) -> exp.Column:
    """Build a Column reference, optionally qualified with a table alias."""
    if alias:
        return exp.Column(this=exp.to_identifier(col_name), table=exp.to_identifier(alias))
    return exp.Column(this=exp.to_identifier(col_name))


def _lit(value: str) -> exp.Literal:
    """Build a string literal (safe — value is never parsed as SQL)."""
    return exp.Literal.string(value)


def _eq(col: exp.Column, value: str) -> exp.EQ:
    return exp.EQ(this=col, expression=_lit(value))


def _gte(col: exp.Column, value: str) -> exp.GTE:
    return exp.GTE(this=col, expression=_lit(value))


def _lt(col: exp.Column, value: str) -> exp.LT:
    return exp.LT(this=col, expression=_lit(value))


def _gt(col: exp.Column, value: str) -> exp.GT:
    return exp.GT(this=col, expression=_lit(value))


def _in(col: exp.Column, values: list[str]) -> exp.In:
    return exp.In(this=col, expressions=[_lit(v) for v in values])


# ---------------------------------------------------------------------------
# Condition builders
# ---------------------------------------------------------------------------

def _build_date_conditions(col_name: str, alias: str | None, filters: DashboardFilters) -> list[exp.Expression]:
    """Build date range conditions."""
    col = _col_ref(col_name, alias)
    conditions = []
    if filters.date_from:
        conditions.append(_gte(col, filters.date_from))
    if filters.date_to:
        conditions.append(_lt(_col_ref(col_name, alias), filters.date_to))
    if conditions:
        conditions.append(_gt(_col_ref(col_name, alias), "1970-01-02"))
    return conditions


def _build_owner_conditions(col_name: str, alias: str | None, filters: DashboardFilters) -> list[exp.Expression]:
    """Build owner filter conditions."""
    if col_name in _ID_OWNER_COLS:
        values = filters.owner_ids
    else:
        values = filters.owner_names
    if not values:
        return []

    col = _col_ref(col_name, alias)
    if len(values) == 1:
        return [_eq(col, values[0])]
    return [_in(col, values)]


def _build_pipeline_conditions(col_name: str, alias: str | None, filters: DashboardFilters) -> list[exp.Expression]:
    """Build pipeline filter conditions."""
    if "label" in col_name:
        values = filters.pipeline_labels
    else:
        values = filters.pipeline_ids
    if not values:
        return []

    col = _col_ref(col_name, alias)
    if len(values) == 1:
        return [_eq(col, values[0])]
    return [_in(col, values)]


# ---------------------------------------------------------------------------
# AST manipulation
# ---------------------------------------------------------------------------

def _inject_conditions(select_node: exp.Select, conditions: list[exp.Expression]) -> None:
    """Inject conditions into a Select node's WHERE clause."""
    if not conditions:
        return
    where = select_node.find(exp.Where)
    if where:
        combined = where.args["this"]
        for cond in conditions:
            combined = exp.And(this=combined, expression=cond)
        select_node.set("where", exp.Where(this=combined))
    else:
        if len(conditions) == 1:
            select_node.set("where", exp.Where(this=conditions[0]))
        else:
            combined = conditions[0]
            for cond in conditions[1:]:
                combined = exp.And(this=combined, expression=cond)
            select_node.set("where", exp.Where(this=combined))


def _find_enclosing_select(node: exp.Expression) -> exp.Select | None:
    """Walk up the AST to find the nearest enclosing Select."""
    current = node.parent
    while current:
        if isinstance(current, exp.Select):
            return current
        current = current.parent
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_filters(sql: str, filters: DashboardFilters) -> str:
    """Apply dashboard filters to a SQL query by rewriting the AST.

    Returns the modified SQL string. If parsing fails, returns the
    original SQL unchanged.
    """
    if filters.is_empty():
        return sql

    try:
        tree = sqlglot.parse(sql, dialect="clickhouse")[0]
    except Exception as e:
        log.warning(f"sqlglot parse failed, returning unfiltered SQL: {e}")
        return sql

    # Collect all real table references (skip CTE aliases — they have no db)
    # Group by enclosing Select to avoid double-injection
    select_conditions: dict[int, list[exp.Expression]] = {}

    for table in tree.find_all(exp.Table):
        db = table.db
        name = table.name
        if not db:
            continue  # CTE alias or unqualified — skip

        full_name = f"{db}.{name}"
        col_map = FILTER_COLUMNS.get(full_name)
        if not col_map:
            continue  # Table not in registry — no filters apply

        alias = table.alias or None
        select_node = _find_enclosing_select(table)
        if not select_node:
            continue

        sid = id(select_node)
        if sid not in select_conditions:
            select_conditions[sid] = []

        # Build conditions for each active filter dimension
        if (filters.date_from or filters.date_to) and col_map.get("date"):
            select_conditions[sid].extend(
                _build_date_conditions(col_map["date"], alias, filters)
            )

        if filters.owner_ids and col_map.get("owner"):
            select_conditions[sid].extend(
                _build_owner_conditions(col_map["owner"], alias, filters)
            )

        if filters.pipeline_ids and col_map.get("pipeline"):
            select_conditions[sid].extend(
                _build_pipeline_conditions(col_map["pipeline"], alias, filters)
            )

    # Inject all collected conditions
    # We need to map sid back to the Select node — walk the tree again
    for select_node in tree.find_all(exp.Select):
        sid = id(select_node)
        if sid in select_conditions:
            _inject_conditions(select_node, select_conditions[sid])

    try:
        return tree.sql(dialect="clickhouse")
    except Exception as e:
        log.warning(f"sqlglot generate failed, returning unfiltered SQL: {e}")
        return sql
