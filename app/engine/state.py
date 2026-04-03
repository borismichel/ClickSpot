"""Selection state — the core data structure for the associative engine."""

from dataclasses import dataclass, field


@dataclass
class SelectionState:
    """Represents the current user selections.

    Keys are "table.column" (e.g., "dim_companies.industry").
    Values are lists of selected values (OR within a field).
    Multiple keys = AND across fields/tables.
    """
    selections: dict[str, list[str]] = field(default_factory=dict)

    def tables_with_selections(self) -> set[str]:
        """Return set of table names that have active selections."""
        return {key.split(".")[0] for key in self.selections if self.selections[key]}

    def filters_for_table(self, table: str) -> dict[str, list[str]]:
        """Return {column: [values]} for selections on a specific table."""
        result = {}
        for key, values in self.selections.items():
            t, col = key.split(".", 1)
            if t == table and values:
                result[col] = values
        return result

    def is_empty(self) -> bool:
        return not any(v for v in self.selections.values())
