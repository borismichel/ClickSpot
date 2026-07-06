"""Pydantic models for data space configuration.

A data space defines a star schema: one grain (fact) entity at the center,
with dimension entities joined via bridges or foreign keys. The config is
used to generate a ClickHouse VIEW in the gold database.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, model_validator


class FilterCondition(BaseModel):
    """One structured filter condition emitted by the no-SQL filter builder.

    Mirrors the frontend `SpaceFilter` shape and the `SpaceFilter` dataclass in
    `space_filter.py`. Persisted as the source-of-truth sidecar so a
    builder-made filter round-trips on edit (see `no_sql.derive_sql`).
    """

    column: str
    operator: Literal[
        "eq", "neq", "in", "gt", "gte", "lt", "lte", "between", "like"
    ]
    values: list[str] = Field(default_factory=list)


class ComputedPreset(BaseModel):
    """A no-SQL computed-column preset: a curated `{kind, params}` recipe that
    expands to a ClickHouse expression (see `no_sql.expand_preset`)."""

    kind: Literal["days_since", "age_bucket", "flag_equals", "quarter", "month"]
    params: dict[str, Any] = Field(default_factory=dict)


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
    filter: str | None = Field(
        default=None,
        description="Optional WHERE expression applied to the grain table, e.g. 'archived = 0'",
    )
    filter_builder: list[FilterCondition] | None = Field(
        default=None,
        description=(
            "Structured no-SQL grain filter (source of truth). When present, "
            "`filter` is derived from it on save (bare grain columns). When None, "
            "`filter` holds raw/Advanced SQL and the field opens in Advanced on edit."
        ),
    )


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
    filter: str | None = Field(
        default=None,
        description="Optional WHERE expression applied to the dimension before joining",
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
    filter: str | None = Field(
        default=None,
        description="Optional WHERE expression applied to the dimension before joining",
    )


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


# Discriminated on `join_type` so a bad dimension reports only *its own*
# validation errors (e.g. "'aggregate' strategy requires agg_expressions"),
# instead of the union trying all three members and returning a 3x-larger
# error array that the frontend rendered as an opaque "[object Object]".
DimensionJoin = Annotated[
    BridgeDimension | FKDimension | DictDimension,
    Field(discriminator="join_type"),
]


class ComputedColumn(BaseModel):
    """A derived column defined as a SQL expression.

    Either authored as a raw `expr` (Advanced) or via a no-SQL `preset`. When
    `preset` is set, `expr` is (re)derived from it on save by `no_sql.derive_sql`,
    so a preset-built column round-trips on edit without exposing SQL.
    """

    alias: str = Field(description="Output column name")
    expr: str = Field(default="", description="ClickHouse SQL expression (derived from preset when set)")
    preset: ComputedPreset | None = Field(
        default=None,
        description="Structured no-SQL preset (source of truth); expands to `expr` on save.",
    )


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
    default_filter_builder: list[FilterCondition] | None = Field(
        default=None,
        description=(
            "Structured no-SQL default filter (source of truth). When present, "
            "`default_filter` is derived from it on save (grain.<col> conditions). "
            "When None, `default_filter` holds raw/Advanced SQL."
        ),
    )

    @property
    def view_name(self) -> str:
        return f"gold.ds_{self.id}"
