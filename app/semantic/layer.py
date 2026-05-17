"""Semantic layer — enriches ClickHouse column metadata with HubSpot property labels and descriptions.

Fetches HubSpot property metadata, filters to only columns that exist in our silver tables,
and caches to disk. Used by the schema prompt builder to give the LLM rich business context.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from silver_config import (
    DIM_CONTACTS, DIM_COMPANIES, DIM_DEALS, DIM_LEADS,
)

log = logging.getLogger("app.semantic")

CACHE_DIR = Path.home() / ".clickspot"
CACHE_FILE = CACHE_DIR / "schema_cache.json"

# Maps HubSpot object types to their silver configs.
# Only these objects have properties fetched from HubSpot.
_OBJECT_CONFIGS = {
    "contacts": {"config": DIM_CONTACTS, "silver_table": "dim_contacts"},
    "companies": {"config": DIM_COMPANIES, "silver_table": "dim_companies"},
    "deals": {"config": DIM_DEALS, "silver_table": "dim_deals"},
    "leads": {"config": DIM_LEADS, "silver_table": "dim_leads"},
}

# Association pairs to fetch type metadata for
_ASSOCIATION_PAIRS = [
    ("contacts", "companies"),
    ("contacts", "deals"),
    ("companies", "deals"),
    ("leads", "contacts"),
    ("leads", "deals"),
    ("leads", "companies"),
]


@dataclass
class PropertyMeta:
    silver_column: str
    bronze_key: str
    ch_type: str
    label: str = ""
    description: str = ""
    hs_type: str = ""
    group_name: str = ""
    options: list[dict] = field(default_factory=list)


@dataclass
class TableMeta:
    object_type: str
    silver_table: str
    properties: dict[str, PropertyMeta] = field(default_factory=dict)


@dataclass
class AssociationTypeMeta:
    from_type: str
    to_type: str
    type_id: int = 0
    label: str = ""
    category: str = ""


@dataclass
class SemanticLayer:
    tables: dict[str, TableMeta] = field(default_factory=dict)
    associations: list[AssociationTypeMeta] = field(default_factory=list)
    built_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "tables": {k: asdict(v) for k, v in self.tables.items()},
            "associations": [asdict(a) for a in self.associations],
            "built_at": self.built_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SemanticLayer":
        layer = cls()
        layer.built_at = data.get("built_at", 0.0)
        for name, tdata in data.get("tables", {}).items():
            tm = TableMeta(
                object_type=tdata["object_type"],
                silver_table=tdata["silver_table"],
            )
            for pname, pdata in tdata.get("properties", {}).items():
                tm.properties[pname] = PropertyMeta(**pdata)
            layer.tables[name] = tm
        for adata in data.get("associations", []):
            layer.associations.append(AssociationTypeMeta(**adata))
        return layer


def _build_bronze_key_set(config: dict) -> dict[str, tuple[str, str]]:
    """Build {bronze_property_key: (silver_column, ch_type)} from a silver config."""
    result = {}
    for col_tuple in config.get("columns", []):
        if len(col_tuple) == 3:
            silver_name, bronze_key, ch_type = col_tuple
            result[bronze_key] = (silver_name, ch_type)
    return result


def build_semantic_layer(hubspot_resource) -> SemanticLayer:
    """Fetch HubSpot property metadata and build the semantic layer.

    Only keeps properties that match columns in our silver tables.
    """
    layer = SemanticLayer(built_at=time.time())

    for hs_object, meta in _OBJECT_CONFIGS.items():
        config = meta["config"]
        silver_table = meta["silver_table"]
        bronze_keys = _build_bronze_key_set(config)

        table_meta = TableMeta(object_type=hs_object, silver_table=silver_table)

        try:
            hs_properties = hubspot_resource.fetch_properties(hs_object)
            log.info(f"Fetched {len(hs_properties)} properties for {hs_object}")
        except Exception as e:
            log.warning(f"Failed to fetch properties for {hs_object}: {e}")
            hs_properties = []

        # Build lookup of HubSpot property name -> metadata
        hs_lookup = {}
        for prop in hs_properties:
            name = prop.get("name", "")
            if name:
                hs_lookup[name] = prop

        # Enrich only columns that exist in silver config
        for bronze_key, (silver_col, ch_type) in bronze_keys.items():
            hs_prop = hs_lookup.get(bronze_key, {})
            options = []
            for opt in hs_prop.get("options", []):
                options.append({
                    "label": opt.get("label", ""),
                    "value": opt.get("value", ""),
                })

            table_meta.properties[silver_col] = PropertyMeta(
                silver_column=silver_col,
                bronze_key=bronze_key,
                ch_type=ch_type,
                label=hs_prop.get("label", silver_col),
                description=hs_prop.get("description", ""),
                hs_type=hs_prop.get("type", ""),
                group_name=hs_prop.get("groupName", ""),
                options=options[:20] if options else [],  # Cap options to keep prompt small
            )

        layer.tables[silver_table] = table_meta

    # Fetch association type metadata
    for from_type, to_type in _ASSOCIATION_PAIRS:
        try:
            types = hubspot_resource.fetch_association_types(from_type, to_type)
            for at in types:
                layer.associations.append(AssociationTypeMeta(
                    from_type=from_type,
                    to_type=to_type,
                    type_id=at.get("typeId", 0),
                    label=at.get("label", ""),
                    category=at.get("category", ""),
                ))
        except Exception as e:
            log.warning(f"Failed to fetch association types {from_type}->{to_type}: {e}")

    return layer


def save_cache(layer: SemanticLayer) -> None:
    """Save semantic layer to disk cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(layer.to_dict(), indent=2))
    log.info(f"Semantic layer cached to {CACHE_FILE}")


def load_cache() -> SemanticLayer | None:
    """Load semantic layer from disk cache, or None if not available."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        layer = SemanticLayer.from_dict(data)
        log.info(f"Loaded semantic layer from cache (built at {layer.built_at})")
        return layer
    except Exception as e:
        log.warning(f"Failed to load semantic cache: {e}")
        return None
