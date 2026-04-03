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
from app.api.models import (
    QueryRequest, QueryResponse,
    FieldValueItem, FieldValuesResponse,
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

        # Get "possible" values (in the reachable set)
        possible_sql = sql_builder.build_field_values_query(
            table, column, pk, id_filter
        )
        possible_rows = db.query_rows(possible_sql)
        possible_values = {str(r["value"]) for r in possible_rows}
        possible = [
            FieldValueItem(value=str(r["value"]), count=int(r["cnt"]))
            for r in possible_rows
            if str(r["value"])  # skip empty strings
        ]

        # Get "excluded" values (NOT in reachable set, but exist in table)
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

    # Measures
    for m in req.measures:
        if m.table not in TABLES:
            continue
        pk = graph.primary_key(m.table)
        id_filter = reachable.get(m.table)
        sql = sql_builder.build_measure_query(
            m.table, m.column, m.agg, pk, id_filter
        )
        try:
            val = db.query_value(sql)
            key = f"{m.table}.{m.column}.{m.agg}"
            response.measures[key] = float(val) if val is not None else None
        except Exception as e:
            log.warning(f"Measure query failed: {e}")

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
