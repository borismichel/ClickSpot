"""Column-based space filters — arbitrary WHERE injection for data space VIEWs.

Unlike DashboardFilters (hardcoded date/owner/pipeline), space filters are
dynamic: any column from the VIEW can be filtered with any supported operator.
Uses the same sqlglot AST rewriting pattern as sql_filter.py.
"""

import logging
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

log = logging.getLogger("app.spaces.space_filter")


@dataclass
class SpaceFilter:
    column: str
    operator: str  # eq, neq, in, gt, gte, lt, lte, between, like
    values: list[str]


# ---------------------------------------------------------------------------
# AST node builders
# ---------------------------------------------------------------------------

def _col(name: str, alias: str | None = None) -> exp.Column:
    if alias:
        return exp.Column(this=exp.to_identifier(name), table=exp.to_identifier(alias))
    return exp.Column(this=exp.to_identifier(name))


def _lit(value: str) -> exp.Literal:
    return exp.Literal.string(value)


def _build_condition(f: SpaceFilter, alias: str | None) -> exp.Expression | None:
    col = _col(f.column, alias)
    op = f.operator
    vals = f.values

    if not vals:
        return None

    if op == "eq":
        return exp.EQ(this=col, expression=_lit(vals[0]))
    if op == "neq":
        return exp.NEQ(this=col, expression=_lit(vals[0]))
    if op == "gt":
        return exp.GT(this=col, expression=_lit(vals[0]))
    if op == "gte":
        return exp.GTE(this=col, expression=_lit(vals[0]))
    if op == "lt":
        return exp.LT(this=col, expression=_lit(vals[0]))
    if op == "lte":
        return exp.LTE(this=col, expression=_lit(vals[0]))
    if op == "in":
        return exp.In(this=col, expressions=[_lit(v) for v in vals])
    if op == "between" and len(vals) >= 2:
        return exp.Between(this=col, low=_lit(vals[0]), high=_lit(vals[1]))
    if op == "like":
        return exp.Like(this=col, expression=_lit(vals[0]))

    log.warning(f"Unknown space filter operator: {op}")
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_space_filters(sql: str, filters: list[SpaceFilter], view_name: str) -> str:
    """Inject space filter conditions into SQL referencing a data space VIEW.

    Finds table references matching view_name and injects WHERE clauses.
    Returns modified SQL. On failure, returns original SQL unchanged.
    """
    if not filters:
        return sql

    try:
        tree = sqlglot.parse(sql, dialect="clickhouse")[0]
    except Exception as e:
        log.warning(f"sqlglot parse failed for space filters: {e}")
        return sql

    # Parse view_name into db.table
    parts = view_name.split(".")
    target_db = parts[0] if len(parts) > 1 else None
    target_table = parts[-1]

    # Build conditions for each filter
    conditions = []
    table_alias = None

    for table in tree.find_all(exp.Table):
        if table.name == target_table and (not target_db or table.db == target_db):
            table_alias = table.alias or None
            break

    for f in filters:
        cond = _build_condition(f, table_alias)
        if cond:
            conditions.append(cond)

    if not conditions:
        return sql

    # Find the outermost SELECT and inject conditions
    select_node = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if not select_node:
        return sql

    where = select_node.find(exp.Where)
    if where:
        combined = where.args["this"]
        for cond in conditions:
            combined = exp.And(this=combined, expression=cond)
        select_node.set("where", exp.Where(this=combined))
    else:
        combined = conditions[0]
        for cond in conditions[1:]:
            combined = exp.And(this=combined, expression=cond)
        select_node.set("where", exp.Where(this=combined))

    try:
        return tree.sql(dialect="clickhouse")
    except Exception as e:
        log.warning(f"sqlglot generate failed for space filters: {e}")
        return sql
