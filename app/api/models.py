"""Pydantic request/response models for the analytics API."""

from pydantic import BaseModel, Field


class MeasureRequest(BaseModel):
    table: str
    column: str
    agg: str = "sum"
    condition: str | None = None


class GroupedMeasureRequest(BaseModel):
    table: str
    column: str
    agg: str = "sum"
    group_by: list[str]
    limit: int = 50


class TimeSeriesRequest(BaseModel):
    table: str
    measure_column: str
    agg: str = "sum"
    date_column: str
    granularity: str = "month"  # day, week, month, quarter, year
    date_from: str | None = None
    date_to: str | None = None


class ListRequest(BaseModel):
    columns: list[str]
    limit: int = 50
    offset: int = 0


class QueryRequest(BaseModel):
    selections: dict[str, list[str]] = Field(default_factory=dict)
    counts: bool = True
    field_values: list[str] = Field(default_factory=list)
    measures: list[MeasureRequest] = Field(default_factory=list)
    grouped_measures: list[GroupedMeasureRequest] = Field(default_factory=list)
    time_series: list[TimeSeriesRequest] = Field(default_factory=list)
    computed_metrics: list[str] = Field(default_factory=list)
    lists: dict[str, ListRequest] = Field(default_factory=dict)


class FieldValueItem(BaseModel):
    value: str
    count: int


class FieldValuesResponse(BaseModel):
    possible: list[FieldValueItem]
    excluded: list[FieldValueItem]


class GroupedMeasureItem(BaseModel):
    groups: dict[str, str]
    value: float | int | None


class TimeSeriesItem(BaseModel):
    period: str
    value: float | int | None


class ListResponse(BaseModel):
    rows: list[dict]
    total: int


class QueryResponse(BaseModel):
    reachable_counts: dict[str, int] = Field(default_factory=dict)
    field_values: dict[str, FieldValuesResponse] = Field(default_factory=dict)
    measures: dict[str, float | int | None] = Field(default_factory=dict)
    grouped_measures: dict[str, list[GroupedMeasureItem]] = Field(default_factory=dict)
    time_series: dict[str, list[TimeSeriesItem]] = Field(default_factory=dict)
    computed_metrics: dict[str, float | int | None] = Field(default_factory=dict)
    lists: dict[str, ListResponse] = Field(default_factory=dict)


class TableSchema(BaseModel):
    primary_key: str
    display_name: str
    fields: dict[str, dict]


class SchemaResponse(BaseModel):
    tables: dict[str, TableSchema]
    edges: list[dict]
    reference_joins: list[dict]


class MetadataResponse(BaseModel):
    row_counts: dict[str, int]
    silver_loaded_at: dict[str, str]
