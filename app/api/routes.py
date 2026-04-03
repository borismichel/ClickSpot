"""FastAPI routes for the associative analytics engine."""

import logging
import time

from fastapi import APIRouter

from app import db
from app.config import GRAPH_EDGES, REFERENCE_JOINS, TABLES
from app.engine.graph import AssociativeGraph
from app.engine.propagator import Propagator
from app.engine.state import SelectionState
from app.engine import sql_builder
from app.engine.metrics import COMPUTED_METRICS
from app.api.models import (
    QueryRequest, QueryResponse,
    FieldValueItem, FieldValuesResponse,
    GroupedMeasureItem, TimeSeriesItem,
    ListResponse,
    SchemaResponse, TableSchema,
    MetadataResponse,
)

log = logging.getLogger("app")
router = APIRouter(prefix="/api/v1")

graph = AssociativeGraph()
propagator = Propagator(graph)


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    t0 = time.time()
    state = SelectionState(selections=req.selections)

    # Propagate selections through the graph
    reachable = propagator.propagate(state)

    response = QueryResponse()

    # Counts
    if req.counts:
        for table in graph.all_tables():
            pk = graph.primary_key(table)
            sql = sql_builder.build_count_query(table, pk, reachable.get(table))
            try:
                response.reachable_counts[table] = int(db.query_value(sql))
            except Exception as e:
                log.warning(f"Count query failed for {table}: {e}")
                response.reachable_counts[table] = 0

    # Field values (three-state)
    for field_spec in req.field_values:
        table, column = field_spec.split(".", 1)
        if table not in TABLES:
            continue
        pk = graph.primary_key(table)
        id_filter = reachable.get(table)

        possible_sql = sql_builder.build_field_values_query(
            table, column, pk, id_filter
        )
        possible_rows = db.query_rows(possible_sql)
        possible_values = {str(r["value"]) for r in possible_rows}
        possible = [
            FieldValueItem(value=str(r["value"]), count=int(r["cnt"]))
            for r in possible_rows
            if str(r["value"])
        ]

        excluded = []
        if id_filter:
            all_sql = sql_builder.build_field_values_query(table, column, pk, None)
            all_rows = db.query_rows(all_sql)
            excluded = [
                FieldValueItem(value=str(r["value"]), count=int(r["cnt"]))
                for r in all_rows
                if str(r["value"]) and str(r["value"]) not in possible_values
            ]

        response.field_values[field_spec] = FieldValuesResponse(
            possible=possible, excluded=excluded
        )

    # Measures (with optional conditions)
    for m in req.measures:
        if m.table not in TABLES:
            continue
        pk = graph.primary_key(m.table)
        id_filter = reachable.get(m.table)

        if m.condition:
            sql = sql_builder.build_conditional_measure_query(
                m.table, m.column, m.agg, m.condition, pk, id_filter
            )
        else:
            sql = sql_builder.build_measure_query(
                m.table, m.column, m.agg, pk, id_filter
            )
        try:
            val = db.query_value(sql)
            key = f"{m.table}.{m.column}.{m.agg}"
            response.measures[key] = float(val) if val is not None else None
        except Exception as e:
            log.warning(f"Measure query failed: {e}")

    # Grouped measures
    for gm in req.grouped_measures:
        if gm.table not in TABLES:
            continue
        pk = graph.primary_key(gm.table)
        id_filter = reachable.get(gm.table)

        sql = sql_builder.build_grouped_measure_query(
            gm.table, gm.column, gm.agg, gm.group_by,
            pk, id_filter, gm.limit,
        )
        try:
            rows = db.query_rows(sql)
            key = f"{gm.table}.{gm.column}.{gm.agg}.by.{','.join(gm.group_by)}"
            response.grouped_measures[key] = [
                GroupedMeasureItem(
                    groups={col: str(row[col]) for col in gm.group_by},
                    value=float(row["value"]) if row["value"] is not None else None,
                )
                for row in rows
            ]
        except Exception as e:
            log.warning(f"Grouped measure query failed: {e}")

    # Time series
    for ts in req.time_series:
        if ts.table not in TABLES:
            continue
        pk = graph.primary_key(ts.table)
        id_filter = reachable.get(ts.table)

        sql = sql_builder.build_time_series_query(
            ts.table, ts.measure_column, ts.agg,
            ts.date_column, ts.granularity,
            pk, id_filter, ts.date_from, ts.date_to,
        )
        try:
            rows = db.query_rows(sql)
            key = f"{ts.table}.{ts.measure_column}.{ts.agg}.by.{ts.date_column}.{ts.granularity}"
            response.time_series[key] = [
                TimeSeriesItem(
                    period=str(row["period"]),
                    value=float(row["value"]) if row["value"] is not None else None,
                )
                for row in rows
            ]
        except Exception as e:
            log.warning(f"Time series query failed: {e}")

    # Computed metrics
    for metric_name in req.computed_metrics:
        metric = COMPUTED_METRICS.get(metric_name)
        if not metric:
            continue
        table = metric["table"]
        pk = graph.primary_key(table)
        id_filter = reachable.get(table)
        ref = sql_builder._table_ref(table)

        where = f"{pk} IN ({id_filter}) AND archived = 0" if id_filter else "archived = 0"
        sql = f"SELECT {metric['sql']} FROM {ref} FINAL WHERE {where}"
        try:
            val = db.query_value(sql)
            response.computed_metrics[metric_name] = float(val) if val is not None else None
        except Exception as e:
            log.warning(f"Computed metric {metric_name} failed: {e}")

    # Lists
    for table, list_req in req.lists.items():
        if table not in TABLES:
            continue
        pk = graph.primary_key(table)
        id_filter = reachable.get(table)

        rows_sql = sql_builder.build_list_query(
            table, list_req.columns, pk, id_filter,
            list_req.limit, list_req.offset,
        )
        count_sql = sql_builder.build_list_count_query(table, pk, id_filter)

        rows = db.query_rows(rows_sql)
        total = int(db.query_value(count_sql))

        response.lists[table] = ListResponse(rows=rows, total=total)

    elapsed = (time.time() - t0) * 1000
    log.info(f"Query completed in {elapsed:.0f}ms | selections={len(state.selections)} tables")

    return response


@router.get("/schema", response_model=SchemaResponse)
def schema() -> SchemaResponse:
    tables = {}
    for name, meta in TABLES.items():
        tables[name] = TableSchema(
            primary_key=meta["primary_key"],
            display_name=meta["display_name"],
            fields=meta["fields"],
        )
    return SchemaResponse(
        tables=tables,
        edges=GRAPH_EDGES,
        reference_joins=REFERENCE_JOINS,
    )


@router.get("/metrics-catalog")
def metrics_catalog() -> dict:
    """Return all available computed metrics."""
    return {
        name: {"label": m["label"], "format": m["format"], "table": m["table"]}
        for name, m in COMPUTED_METRICS.items()
    }


@router.get("/metadata", response_model=MetadataResponse)
def metadata() -> MetadataResponse:
    row_counts = {}
    loaded_at = {}

    for table in TABLES:
        try:
            row_counts[table] = int(db.query_value(
                f"SELECT count() FROM silver.{table} FINAL WHERE archived = 0"
            ))
        except Exception:
            row_counts[table] = 0

        try:
            ts = db.query_value(
                f"SELECT max(_silver_loaded_at) FROM silver.{table}"
            )
            loaded_at[table] = str(ts) if ts else ""
        except Exception:
            loaded_at[table] = ""

    return MetadataResponse(row_counts=row_counts, silver_loaded_at=loaded_at)
