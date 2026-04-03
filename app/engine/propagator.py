"""Selection propagator — the heart of the associative engine.

Given a SelectionState, computes the reachable ID set for every table
by traversing the graph via bridge tables.
"""

from app.engine.graph import AssociativeGraph
from app.engine.state import SelectionState
from app.engine import sql_builder
from app.config import TABLES


class Propagator:
    """Propagates selections through the associative graph.

    Produces a dict of {table: SQL subquery returning reachable IDs}.
    These subqueries can be used as IN filters for counts, field values, etc.
    """

    def __init__(self, graph: AssociativeGraph):
        self.graph = graph

    def propagate(self, state: SelectionState) -> dict[str, str | None]:
        """Compute reachable ID subqueries for all tables.

        Returns: {table: SQL_subquery | None}
          - None means "no filter" (all records are reachable)
          - SQL string means "only IDs returned by this subquery are reachable"
        """
        if state.is_empty():
            return {t: None for t in self.graph.all_tables()}

        selected_tables = state.tables_with_selections()

        # Step 1: For each table with direct selections, build the ID subquery
        direct_id_queries: dict[str, str] = {}
        for table in selected_tables:
            pk = self.graph.primary_key(table)
            filters = state.filters_for_table(table)
            direct_id_queries[table] = sql_builder.build_id_subquery(table, pk, filters)

        # Step 2: For each selected table, propagate outward via BFS
        # Each selected table produces a set of reachable ID subqueries for other tables
        per_source_reachable: dict[str, dict[str, str]] = {}

        for source_table, source_ids_sql in direct_id_queries.items():
            reachable = {source_table: source_ids_sql}
            paths = self.graph.bfs_paths(source_table)

            for target_table, edges in paths.items():
                if target_table == source_table:
                    continue
                # Build chained traversal SQL
                current_sql = source_ids_sql
                current_key = self.graph.primary_key(source_table)

                for edge in edges:
                    if edge["bridge"]:
                        current_sql = sql_builder.build_bridge_traversal(
                            current_sql,
                            edge["bridge"],
                            edge["source_key"],
                            edge["target_key"],
                        )
                    else:
                        # FK join: need to go from current IDs through source table's FK column
                        # to find matching target IDs
                        source_t = self._find_table_for_edge(edge, edges, target_table)
                        current_sql = self._build_fk_step(
                            current_sql, current_key, edge
                        )
                    current_key = edge["target_key"]

                reachable[target_table] = current_sql

            per_source_reachable[source_table] = reachable

        # Step 3: Intersect across selected tables (AND semantics)
        all_tables = self.graph.all_tables()
        result: dict[str, str | None] = {}

        for table in all_tables:
            subqueries = []
            for source_table in selected_tables:
                if table in per_source_reachable.get(source_table, {}):
                    subqueries.append(per_source_reachable[source_table][table])

            if not subqueries:
                result[table] = None
            elif len(subqueries) == 1:
                result[table] = subqueries[0]
            else:
                # Intersect: IDs must be in ALL subqueries
                pk = self.graph.primary_key(table)
                intersected = subqueries[0]
                for sq in subqueries[1:]:
                    intersected = (
                        f"SELECT {pk} FROM ({intersected}) "
                        f"WHERE {pk} IN ({sq})"
                    )
                result[table] = intersected

        return result

    def _find_table_for_edge(self, edge: dict, edges: list[dict], target: str) -> str:
        """Find which table an edge originates from."""
        # Walk edges to find the table that owns source_key
        for t, meta in TABLES.items():
            if meta["primary_key"] == edge["source_key"]:
                return t
        return target

    def _build_fk_step(self, current_ids_sql: str, current_key: str, edge: dict) -> str:
        """Build SQL for an FK traversal step.

        For FK joins, we need to find target PKs that match values
        from a column in the source table.
        """
        source_key = edge["source_key"]
        target_key = edge["target_key"]

        # Find which table the target_key belongs to
        target_table = None
        for t, meta in TABLES.items():
            if meta["primary_key"] == target_key:
                target_table = t
                break

        # Find which table the source_key column belongs to
        source_table = None
        for t, meta in TABLES.items():
            if meta["primary_key"] == current_key or meta["primary_key"] == source_key:
                source_table = t
                break

        if target_table and source_table:
            return (
                f"SELECT DISTINCT {target_key} FROM silver.{target_table} FINAL "
                f"WHERE {target_key} IN ("
                f"SELECT {source_key} FROM silver.{source_table} FINAL "
                f"WHERE {TABLES[source_table]['primary_key']} IN ({current_ids_sql})"
                f")"
            )

        # Fallback: simple column match
        return (
            f"SELECT DISTINCT {target_key} FROM silver.{edge['target']} FINAL "
            f"WHERE {target_key} IN ({current_ids_sql})"
        )
