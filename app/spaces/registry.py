"""Data space registry — CRUD operations + dynamic system registration.

Persists configs as JSON files in ~/.clickspot/spaces/. On create/update,
executes CREATE OR REPLACE VIEW in ClickHouse. On delete, drops the VIEW.
Registers data space VIEWs in FILTER_COLUMNS and ALLOWED_TABLES so the
filter engine and SQL validator recognize them automatically.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.db import get_client, query_rows, query_value
from app.spaces.config import DataSpaceConfig
from app.spaces.generator import generate_view_sql, generate_select_sql

log = logging.getLogger("app.spaces.registry")

SPACES_DIR = Path.home() / ".clickspot" / "spaces"

# In-memory registry of active data spaces
_spaces: dict[str, DataSpaceConfig] = {}


def _ensure_dir():
    SPACES_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _config_path(space_id: str) -> Path:
    return SPACES_DIR / f"{space_id}.json"


def _save_config(config: DataSpaceConfig):
    _ensure_dir()
    _config_path(config.id).write_text(config.model_dump_json(indent=2))


def _delete_config(space_id: str):
    path = _config_path(space_id)
    if path.exists():
        path.unlink()


def _load_all_configs() -> list[DataSpaceConfig]:
    _ensure_dir()
    configs = []
    for f in SPACES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            configs.append(DataSpaceConfig(**data))
        except Exception as e:
            log.warning(f"Failed to load space config {f.name}: {e}")
    return configs


# ---------------------------------------------------------------------------
# ClickHouse VIEW management
# ---------------------------------------------------------------------------

def _create_view(config: DataSpaceConfig):
    """Create or replace the ClickHouse VIEW."""
    sql = generate_view_sql(config)
    log.info(f"Creating VIEW {config.view_name}")
    get_client().command(sql, settings={"allow_suspicious_low_cardinality_types": 1})


def _drop_view(config: DataSpaceConfig):
    """Drop the ClickHouse VIEW if it exists."""
    sql = f"DROP VIEW IF EXISTS {config.view_name}"
    log.info(f"Dropping VIEW {config.view_name}")
    query_value(sql)


# ---------------------------------------------------------------------------
# Dynamic registration in system registries
# ---------------------------------------------------------------------------

def _register_in_systems(config: DataSpaceConfig):
    """Register data space VIEW in FILTER_COLUMNS, ALLOWED_TABLES, and TABLES."""
    from app.config import TABLES
    from app.engine.sql_filter import FILTER_COLUMNS
    from app.llm.sql_validator import ALLOWED_TABLES

    view_name = config.view_name  # e.g. "gold.ds_lead_pipeline"

    # Register in ALLOWED_TABLES for SQL validator
    ALLOWED_TABLES.add(view_name)

    # Build FILTER_COLUMNS entry — inherit from grain entity
    grain_entity = config.grain.entity
    grain_filter = FILTER_COLUMNS.get(f"silver.{grain_entity}")
    if grain_filter:
        FILTER_COLUMNS[view_name] = dict(grain_filter)

    # Register in TABLES for schema prompt
    grain_meta = TABLES.get(grain_entity, {})
    fields = {}
    # Add grain columns
    grain_fields = grain_meta.get("fields", {})
    for col in config.grain.columns:
        if col in grain_fields:
            fields[col] = grain_fields[col]

    # Add dimension columns with prefixes
    for dim in config.dimensions:
        dim_meta = TABLES.get(dim.entity, {})
        dim_fields = dim_meta.get("fields", {})
        for col in dim.columns:
            if col in dim_fields:
                fields[f"{dim.prefix}{col}"] = {
                    "type": dim_fields[col]["type"],
                    "display": f"{dim_fields[col]['display']} ({dim.prefix.rstrip('_')})",
                }

    # Add computed columns
    for comp in config.computed:
        fields[comp.alias] = {"type": "computed", "display": comp.alias}

    TABLES[f"ds_{config.id}"] = {
        "primary_key": config.grain.key,
        "display_name": f"Data Space: {config.name}",
        "database": "gold",
        "fields": fields,
    }


def _unregister_from_systems(config: DataSpaceConfig):
    """Remove data space from all system registries."""
    from app.config import TABLES
    from app.engine.sql_filter import FILTER_COLUMNS
    from app.llm.sql_validator import ALLOWED_TABLES

    view_name = config.view_name
    ALLOWED_TABLES.discard(view_name)
    FILTER_COLUMNS.pop(view_name, None)
    TABLES.pop(f"ds_{config.id}", None)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_spaces() -> list[DataSpaceConfig]:
    return list(_spaces.values())


def get_space(space_id: str) -> DataSpaceConfig | None:
    return _spaces.get(space_id)


def create_space(config: DataSpaceConfig) -> DataSpaceConfig:
    """Create a new data space: persist config, create VIEW, register."""
    if config.id in _spaces:
        raise ValueError(f"Data space '{config.id}' already exists")

    _create_view(config)
    _save_config(config)
    _spaces[config.id] = config
    _register_in_systems(config)
    log.info(f"Created data space '{config.id}' ({config.name})")
    return config


def update_space(space_id: str, config: DataSpaceConfig) -> DataSpaceConfig:
    """Update a data space: drop old VIEW, create new, re-register."""
    old = _spaces.get(space_id)
    if old:
        _drop_view(old)
        _unregister_from_systems(old)

    config.id = space_id  # Ensure ID consistency
    _create_view(config)
    _save_config(config)
    _spaces[space_id] = config
    _register_in_systems(config)
    log.info(f"Updated data space '{space_id}' ({config.name})")
    return config


def delete_space(space_id: str):
    """Delete a data space: drop VIEW, remove config, unregister."""
    config = _spaces.get(space_id)
    if not config:
        raise ValueError(f"Data space '{space_id}' not found")

    _drop_view(config)
    _unregister_from_systems(config)
    _delete_config(space_id)
    del _spaces[space_id]
    log.info(f"Deleted data space '{space_id}'")


def preview_space(config: DataSpaceConfig) -> dict:
    """Generate SQL and execute preview without saving."""
    select_sql = generate_select_sql(config)
    preview_sql = select_sql.rstrip().rstrip(";") + " LIMIT 50"
    try:
        rows = query_rows(preview_sql)
        columns = list(rows[0].keys()) if rows else []
        return {
            "sql": generate_view_sql(config),
            "select_sql": select_sql,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
        }
    except Exception as e:
        return {
            "sql": generate_view_sql(config),
            "select_sql": select_sql,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# Startup — load all saved spaces
# ---------------------------------------------------------------------------

def load_saved_spaces():
    """Load all saved data space configs and register them.

    Called on app startup. Creates VIEWs if they don't exist.
    """
    configs = _load_all_configs()
    for config in configs:
        try:
            _create_view(config)
            _spaces[config.id] = config
            _register_in_systems(config)
            log.info(f"Loaded data space '{config.id}' ({config.name})")
        except Exception as e:
            log.warning(f"Failed to load data space '{config.id}': {e}")
    log.info(f"Loaded {len(_spaces)} data spaces from disk")
