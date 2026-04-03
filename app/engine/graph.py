"""Graph model for the associative engine — knows how tables connect."""

from collections import defaultdict
from app.config import GRAPH_EDGES, REFERENCE_JOINS, TABLES


class AssociativeGraph:
    """Bidirectional graph of table relationships.

    Supports two kinds of edges:
    - Bridge edges: table A ↔ table B through a bridge table (N:M)
    - Reference edges: table A → table B via direct FK column match
    """

    def __init__(self):
        # adjacency: table -> list of (neighbor_table, edge_info)
        self.adjacency: dict[str, list[dict]] = defaultdict(list)
        self._build()

    def _build(self):
        for edge in GRAPH_EDGES:
            # Forward direction
            self.adjacency[edge["from"]].append({
                "target": edge["to"],
                "bridge": edge["bridge"],
                "source_key": edge["from_key"],
                "target_key": edge["to_key"],
            })
            # Reverse direction
            self.adjacency[edge["to"]].append({
                "target": edge["from"],
                "bridge": edge["bridge"],
                "source_key": edge["to_key"],
                "target_key": edge["from_key"],
            })

        for ref in REFERENCE_JOINS:
            self.adjacency[ref["from"]].append({
                "target": ref["to"],
                "bridge": None,  # direct FK
                "source_key": ref["from_col"],
                "target_key": ref["to_col"],
            })
            self.adjacency[ref["to"]].append({
                "target": ref["from"],
                "bridge": None,
                "source_key": ref["to_col"],
                "target_key": ref["from_col"],
            })

    def neighbors(self, table: str) -> list[dict]:
        return self.adjacency.get(table, [])

    def all_tables(self) -> list[str]:
        return list(TABLES.keys())

    def primary_key(self, table: str) -> str:
        return TABLES[table]["primary_key"]

    def bfs_paths(self, start: str) -> dict[str, list[dict]]:
        """BFS from start table, returning shortest path edges to each reachable table.

        Returns: {table: [list of edges from start to table]}
        """
        visited = {start}
        queue = [(start, [])]
        paths = {start: []}

        while queue:
            current, path = queue.pop(0)
            for edge in self.neighbors(current):
                target = edge["target"]
                if target not in visited:
                    visited.add(target)
                    new_path = path + [edge]
                    paths[target] = new_path
                    queue.append((target, new_path))

        return paths
