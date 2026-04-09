"""Pydantic models for data space configuration.

A data space defines a star schema: one grain (fact) entity at the center,
with dimension entities joined via bridges or foreign keys. The config is
used to generate a ClickHouse VIEW in the gold database.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BridgeStrategy(str, Enum):
    """How to handle N:M bridge joins while preserving grain."""

    one_to_one = "one_to_one"  # FULL OUTER JOIN (1:1 in practice)
    any = "any"                # any() — pick one record per grain key
    latest = "latest"          # argMax(pk, timestamp) — most recent
    aggregate = "aggregate"    # count()/sum() — aggregate metrics
    fan_out = "fan_out"        # plain LEFT JOIN — rows multiply


class GrainConfig(BaseModel):
    """Center entity of the star schema."""

    entity: str = Field(description="Silver table name, e.g. 'dim_leads'")
    key: str = Field(description="Primary key column, e.g. 'lead_id'")
    columns: list[str] = Field(description="Columns to include from the grain entity")


class BridgeDimension(BaseModel):
    """Dimension joined via an N:M bridge table."""

    join_type: Literal["bridge"] = "bridge"
    entity: str = Field(description="Dimension table name, e.g. 'dim_deals'")
    bridge: str = Field(description="Bridge table name, e.g. 'bridge_deal_lead'")
    bridge_grain_key: str = Field(description="Bridge column that references the grain PK")
    bridge_dim_key: str = Field(description="Bridge column that references the dimension PK")
    dim_key: str = Field(description="Dimension table PK column")
    strategy: BridgeStrategy = Field(description="How to handle N:M cardinality")
    columns: list[str] = Field(description="Columns to include from the dimension")
    prefix: str = Field(description="Column alias prefix, e.g. 'deal_'")
    timestamp_col: str | None = Field(
        default=None,
        description="Timestamp column for 'latest' strategy (e.g. 'createdate')",
    )
    agg_expressions: list[dict[str, str]] | None = Field(
        default=None,
        description="For 'aggregate' strategy: list of {alias, expr} dicts",
    )

    @model_validator(mode="after")
    def check_strategy_fields(self) -> BridgeDimension:
        if self.strategy == BridgeStrategy.latest and not self.timestamp_col:
            raise ValueError("'latest' strategy requires timestamp_col")
        if self.strategy == BridgeStrategy.aggregate and not self.agg_expressions:
            raise ValueError("'aggregate' strategy requires agg_expressions")
        return self


class FKDimension(BaseModel):
    """Dimension joined via a direct foreign key (always 1:1)."""

    join_type: Literal["fk"] = "fk"
    entity: str = Field(description="Dimension table name, e.g. 'dim_owners'")
    dim_key: str = Field(description="Dimension table PK column")
    fk_from: str = Field(description="Grain column containing the FK")
    fk_to: str = Field(description="Dimension column the FK points to")
    columns: list[str] = Field(description="Columns to include from the dimension")
    prefix: str = Field(description="Column alias prefix, e.g. 'owner_'")


class DictDimension(BaseModel):
    """Dimension resolved via dictGet() — O(1) in-memory hash lookup, no JOIN.

    Uses ClickHouse dictionaries (DICT_CONFIGS in silver_config.py).
    Only works for columns registered in the dictionary's values.
    Cannot filter on looked-up columns — use FKDimension if you need that.
    At scale (50M+ rows), this is orders of magnitude faster than LEFT JOIN.
    """

    join_type: Literal["dict"] = "dict"
    entity: str = Field(description="Source dim table, e.g. 'dim_owners' → dict_owners")
    dict_name: str = Field(description="Dictionary name, e.g. 'dict_owners'")
    key_expr: str = Field(description="Grain expression for the dict key, e.g. 'grain.hubspot_owner_id'")
    columns: list[str] = Field(description="Dictionary value columns to include")
    prefix: str = Field(description="Column alias prefix, e.g. 'owner_'")


DimensionJoin = BridgeDimension | FKDimension | DictDimension


class ComputedColumn(BaseModel):
    """A derived column defined as a SQL expression."""

    alias: str = Field(description="Output column name")
    expr: str = Field(description="ClickHouse SQL expression")


class DataSpaceConfig(BaseModel):
    """Full data space configuration — grain + dimensions + computed."""

    id: str = Field(description="Unique identifier, used in VIEW name: gold.ds_{id}")
    name: str = Field(description="Human-readable name")
    grain: GrainConfig
    dimensions: list[DimensionJoin] = Field(default_factory=list)
    computed: list[ComputedColumn] = Field(default_factory=list)
    default_filter: str | None = Field(
        default=None,
        description="Default WHERE clause applied to the grain, e.g. 'grain.archived = 0'",
    )

    @property
    def view_name(self) -> str:
        return f"gold.ds_{self.id}"
