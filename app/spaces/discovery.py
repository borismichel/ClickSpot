"""Discover reachable dimensions from a grain entity.

Uses GRAPH_EDGES (bridge connections) and REFERENCE_JOINS (FK connections)
from app/config.py to find entities that can be joined to the grain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import GRAPH_EDGES, REFERENCE_JOINS, TABLES

try:
    from silver_config import DICT_CONFIGS
except ImportError:
    DICT_CONFIGS = {}

# Map dim table → dict name (e.g. "dim_owners" → "dict_owners")
_DIM_TO_DICT: dict[str, tuple[str, list[str]]] = {}
for _table, _cfg in DICT_CONFIGS.items():
    _dict_name = "dict_" + _table.removeprefix("dim_")
    _value_cols = [entry[0] for entry in _cfg["values"]]
    _DIM_TO_DICT[_table] = (_dict_name, _value_cols)


@dataclass
class DiscoveredDimension:
    """A dimension reachable from a grain entity."""

    entity: str
    display_name: str
    join_type: Literal["bridge", "fk"]
    # Bridge fields (None for FK joins)
    bridge: str | None = None
    bridge_grain_key: str | None = None
    bridge_dim_key: str | None = None
    dim_key: str | None = None
    # FK fields (None for bridge joins)
    fk_from: str | None = None
    fk_to: str | None = None
    # Dict fields (populated when a dictionary exists for this entity)
    dict_name: str | None = None
    dict_columns: list[str] | None = None
    # Columns available on the dimension
    columns: list[dict] | None = None


def discover_dimensions(grain_entity: str) -> list[DiscoveredDimension]:
    """Find all dimensions reachable from a grain entity (1-hop only).

    Returns bridge joins and FK joins separately. Does not traverse
    multi-hop paths (e.g. leads → contacts → companies) — those can be
    added as explicit dimensions if needed.
    """
    results: list[DiscoveredDimension] = []
    seen: set[str] = set()

    # Bridge connections (N:M)
    for edge in GRAPH_EDGES:
        dim_entity: str | None = None
        bridge_grain_key: str | None = None
        bridge_dim_key: str | None = None

        if edge["from"] == grain_entity:
            dim_entity = edge["to"]
            bridge_grain_key = edge["from_key"]
            bridge_dim_key = edge["to_key"]
        elif edge["to"] == grain_entity:
            dim_entity = edge["from"]
            bridge_grain_key = edge["to_key"]
            bridge_dim_key = edge["from_key"]

        if dim_entity and dim_entity not in seen:
            seen.add(dim_entity)
            meta = TABLES.get(dim_entity, {})
            results.append(DiscoveredDimension(
                entity=dim_entity,
                display_name=meta.get("display_name", dim_entity),
                join_type="bridge",
                bridge=edge["bridge"],
                bridge_grain_key=bridge_grain_key,
                bridge_dim_key=bridge_dim_key,
                dim_key=meta.get("primary_key"),
                columns=_entity_columns(dim_entity),
            ))

    # FK connections (1:1)
    for ref in REFERENCE_JOINS:
        if ref["from"] == grain_entity:
            dim_entity = ref["to"]
            if dim_entity not in seen:
                seen.add(dim_entity)
                meta = TABLES.get(dim_entity, {})
                # Check if a dictionary exists for this entity
                dict_info = _DIM_TO_DICT.get(dim_entity)
                results.append(DiscoveredDimension(
                    entity=dim_entity,
                    display_name=meta.get("display_name", dim_entity),
                    join_type="fk",
                    dim_key=meta.get("primary_key"),
                    fk_from=ref["from_col"],
                    fk_to=ref["to_col"],
                    dict_name=dict_info[0] if dict_info else None,
                    dict_columns=dict_info[1] if dict_info else None,
                    columns=_entity_columns(dim_entity),
                ))

    return results


def get_grain_entities() -> list[dict]:
    """Return entities suitable as grain (fact center) of a data space.

    Excludes lookup tables (pipelines, stages, owners) — those are
    typically dimensions, not grains.
    """
    grain_entities = []
    exclude = {
        "dim_pipelines", "dim_pipeline_stages", "dim_owners",
        "dim_lead_pipelines", "dim_lead_pipeline_stages",
    }
    for table_name, meta in TABLES.items():
        if meta.get("database") == "gold":
            continue
        if table_name in exclude:
            continue
        grain_entities.append({
            "entity": table_name,
            "display_name": meta.get("display_name", table_name),
            "primary_key": meta.get("primary_key"),
            "columns": _entity_columns(table_name),
        })
    return grain_entities


def get_available_dicts() -> list[dict]:
    """Return all available ClickHouse dictionaries with their columns."""
    results = []
    for table, (dict_name, value_cols) in _DIM_TO_DICT.items():
        cfg = DICT_CONFIGS.get(table, {})
        keys = [k[0] for k in cfg.get("keys", [])]
        results.append({
            "dict_name": dict_name,
            "entity": table,
            "display_name": TABLES.get(table, {}).get("display_name", table),
            "keys": keys,
            "columns": value_cols,
        })
    return results


def _entity_columns(entity: str) -> list[dict]:
    """Return column metadata for an entity from TABLES config."""
    meta = TABLES.get(entity, {})
    fields = meta.get("fields", {})
    return [
        {"name": name, "type": info["type"], "display": info["display"]}
        for name, info in fields.items()
    ]
