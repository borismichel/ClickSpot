"""Silver layer assets — config-driven dim/fact/bridge tables with full refresh."""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource
from silver_config import (
    DIM_CONTACTS, DIM_COMPANIES, DIM_DEALS, DIM_LEADS,
    DIM_OWNERS, DIM_PIPELINES, DIM_PIPELINE_STAGES,
    FACT_ACTIVITIES, BRIDGE_TABLES,
    BRIDGE_ACTIVITY_CONTACT, BRIDGE_ACTIVITY_COMPANY, BRIDGE_ACTIVITY_DEAL,
)


# ---------------------------------------------------------------------------
# Helpers: SQL generation from config
# ---------------------------------------------------------------------------

def _cast_expr(prop_key: str, ch_type: str, source: str = "properties") -> str:
    """Generate a ClickHouse SELECT expression with type casting."""
    if source == "json":
        raw_expr = f"JSONExtractString(_raw, '{prop_key}')"
    else:
        raw_expr = f"properties['{prop_key}']"

    if ch_type == "String":
        return raw_expr
    elif ch_type == "DateTime":
        return f"parseDateTimeBestEffortOrZero({raw_expr})"
    elif ch_type == "Nullable(Float64)":
        return f"toFloat64OrNull({raw_expr})"
    elif ch_type == "UInt32":
        return f"toUInt32OrZero({raw_expr})"
    elif ch_type == "Nullable(Int64)":
        return f"toInt64OrNull({raw_expr})"
    else:
        return raw_expr


def _build_ddl(table_name: str, primary_key: str, columns: list, source: str = "properties") -> str:
    """Build CREATE TABLE DDL from config."""
    col_defs = [f"    {primary_key} String"]

    if source == "nested_stages":
        # columns are (name, type) tuples for nested_stages
        for col_name, col_type in columns:
            col_defs.append(f"    {col_name} {col_type}")
    else:
        # columns are (name, prop_key, type) tuples
        for col_name, _prop_key, col_type in columns:
            col_defs.append(f"    {col_name} {col_type}")

    col_defs.append("    archived UInt8")
    col_defs.append("    _silver_loaded_at DateTime DEFAULT now()")

    cols_sql = ",\n".join(col_defs)
    return (
        f"CREATE TABLE silver.{table_name} (\n"
        f"{cols_sql}\n"
        f") ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY ({primary_key})"
    )


def _build_insert(table_name: str, primary_key: str, config: dict) -> str:
    """Build INSERT INTO ... SELECT from bronze."""
    bronze_table = config["bronze_table"]
    source = config.get("source", "properties")
    columns = config["columns"]

    select_exprs = [f"    _record_id AS {primary_key}"]

    if source == "properties":
        for col_name, prop_key, col_type in columns:
            expr = _cast_expr(prop_key, col_type, "properties")
            select_exprs.append(f"    {expr} AS {col_name}")
    elif source == "json":
        for col_name, json_key, col_type in columns:
            expr = _cast_expr(json_key, col_type, "json")
            select_exprs.append(f"    {expr} AS {col_name}")

    select_exprs.append("    JSONExtractBool(_raw, 'archived') AS archived")
    select_exprs.append("    now() AS _silver_loaded_at")

    select_sql = ",\n".join(select_exprs)
    return (
        f"INSERT INTO silver.{table_name}\n"
        f"SELECT\n{select_sql}\n"
        f"FROM bronze.{bronze_table} FINAL"
    )


# ---------------------------------------------------------------------------
# Factory: dimension assets
# ---------------------------------------------------------------------------

def _make_dim_asset(name: str, config: dict):
    bronze_table = config["bronze_table"]
    primary_key = config["primary_key"]
    source = config.get("source", "properties")

    @asset(
        name=f"dim_{name}",
        group_name="silver",
        deps=[AssetKey(bronze_table)],
    )
    def _asset(context: AssetExecutionContext, ch_silver: ClickHouseResource):
        # DROP + CREATE + INSERT
        context.log.info(f"Rebuilding silver.dim_{name}")
        ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.dim_{name}")

        ddl = _build_ddl(f"dim_{name}", primary_key, config["columns"], source)
        context.log.info(f"DDL: {ddl}")
        ch_silver.execute_sql(ddl)

        insert_sql = _build_insert(f"dim_{name}", primary_key, config)
        context.log.info(f"INSERT: {insert_sql}")
        ch_silver.execute_sql(insert_sql)

        row_count = ch_silver.execute_sql(f"SELECT count() FROM silver.dim_{name}")
        context.log.info(f"silver.dim_{name}: {row_count} rows")

        yield MaterializeResult(
            metadata={
                "row_count": MetadataValue.int(int(row_count)),
                "table": MetadataValue.text(f"silver.dim_{name}"),
            }
        )

    return _asset


# Create standard dim assets
dim_contacts = _make_dim_asset("contacts", DIM_CONTACTS)
dim_companies = _make_dim_asset("companies", DIM_COMPANIES)
dim_deals = _make_dim_asset("deals", DIM_DEALS)
dim_leads = _make_dim_asset("leads", DIM_LEADS)
dim_owners = _make_dim_asset("owners", DIM_OWNERS)
dim_pipelines = _make_dim_asset("pipelines", DIM_PIPELINES)


# ---------------------------------------------------------------------------
# Special asset: dim_pipeline_stages (ARRAY JOIN)
# ---------------------------------------------------------------------------

@asset(
    name="dim_pipeline_stages",
    group_name="silver",
    deps=[AssetKey("hs_pipelines")],
)
def dim_pipeline_stages(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    context.log.info("Rebuilding silver.dim_pipeline_stages")
    ch_silver.execute_sql("DROP TABLE IF EXISTS silver.dim_pipeline_stages")

    ddl = _build_ddl("dim_pipeline_stages", "stage_id", DIM_PIPELINE_STAGES["columns"], "nested_stages")
    context.log.info(f"DDL: {ddl}")
    ch_silver.execute_sql(ddl)

    insert_sql = """
INSERT INTO silver.dim_pipeline_stages
SELECT
    JSONExtractString(stage, 'id') AS stage_id,
    _record_id AS pipeline_id,
    JSONExtractString(stage, 'label') AS label,
    toUInt32OrZero(JSONExtractString(stage, 'displayOrder')) AS display_order,
    JSONExtractString(stage, 'metadata', 'isClosed') AS is_closed,
    toFloat64OrNull(JSONExtractString(stage, 'metadata', 'probability')) AS probability,
    parseDateTimeBestEffortOrZero(JSONExtractString(stage, 'createdAt')) AS created_at,
    parseDateTimeBestEffortOrZero(JSONExtractString(stage, 'updatedAt')) AS updated_at,
    JSONExtractBool(_raw, 'archived') AS archived,
    now() AS _silver_loaded_at
FROM bronze.hs_pipelines FINAL
ARRAY JOIN JSONExtractArrayRaw(_raw, 'stages') AS stage
""".strip()
    context.log.info(f"INSERT: {insert_sql}")
    ch_silver.execute_sql(insert_sql)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.dim_pipeline_stages")
    context.log.info(f"silver.dim_pipeline_stages: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.dim_pipeline_stages"),
        }
    )


# ---------------------------------------------------------------------------
# Fact: fact_activities (UNION ALL across 5 activity types)
# ---------------------------------------------------------------------------

# Bronze table name -> activity_type literal
_ACTIVITY_BRONZE = {
    "calls":    ("hs_calls",             "call"),
    "meetings": ("hs_meetings",          "meeting"),
    "emails":   ("hs_engagement_emails", "email"),
    "notes":    ("hs_notes",             "note"),
    "tasks":    ("hs_tasks",             "task"),
}


@asset(
    name="fact_activities",
    group_name="silver",
    deps=[
        AssetKey("hs_calls"),
        AssetKey("hs_meetings"),
        AssetKey("hs_engagement_emails"),
        AssetKey("hs_notes"),
        AssetKey("hs_tasks"),
    ],
)
def fact_activities(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    context.log.info("Rebuilding silver.fact_activities")
    ch_silver.execute_sql("DROP TABLE IF EXISTS silver.fact_activities")

    ddl = """
CREATE TABLE silver.fact_activities (
    activity_id String,
    activity_type LowCardinality(String),
    hs_timestamp DateTime,
    subject String,
    body_preview String,
    disposition String,
    duration_ms Nullable(Int64),
    hubspot_owner_id String,
    createdate DateTime,
    lastmodifieddate DateTime,
    archived UInt8,
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY (activity_id)
""".strip()
    ch_silver.execute_sql(ddl)

    # Build UNION ALL
    union_parts = []
    for act_key, mapping in FACT_ACTIVITIES.items():
        bronze_table, type_literal = _ACTIVITY_BRONZE[act_key]

        subject_prop = mapping["subject"]
        disposition_prop = mapping["disposition"]
        duration_prop = mapping["duration"]

        subject_expr = f"properties['{subject_prop}']" if subject_prop else "''"
        disposition_expr = f"properties['{disposition_prop}']" if disposition_prop else "''"
        duration_expr = f"toInt64OrNull(properties['{duration_prop}'])" if duration_prop else "NULL"

        part = f"""SELECT
    _record_id AS activity_id,
    '{type_literal}' AS activity_type,
    parseDateTimeBestEffortOrZero(properties['hs_timestamp']) AS hs_timestamp,
    {subject_expr} AS subject,
    properties['hs_body_preview'] AS body_preview,
    {disposition_expr} AS disposition,
    {duration_expr} AS duration_ms,
    properties['hubspot_owner_id'] AS hubspot_owner_id,
    parseDateTimeBestEffortOrZero(properties['hs_createdate']) AS createdate,
    parseDateTimeBestEffortOrZero(properties['hs_lastmodifieddate']) AS lastmodifieddate,
    JSONExtractBool(_raw, 'archived') AS archived,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = "INSERT INTO silver.fact_activities\n" + "\nUNION ALL\n".join(union_parts)
    context.log.info(f"INSERT: {insert_sql}")
    ch_silver.execute_sql(insert_sql)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.fact_activities")
    context.log.info(f"silver.fact_activities: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.fact_activities"),
        }
    )


# ---------------------------------------------------------------------------
# Bridge factories
# ---------------------------------------------------------------------------

def _make_bridge_asset(silver_table: str, bronze_table: str, from_key: str, to_key: str):
    @asset(
        name=silver_table,
        group_name="silver",
        deps=[AssetKey(bronze_table)],
    )
    def _asset(context: AssetExecutionContext, ch_silver: ClickHouseResource):
        context.log.info(f"Rebuilding silver.{silver_table}")
        ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{silver_table}")

        ddl = f"""
CREATE TABLE silver.{silver_table} (
    {from_key} String,
    {to_key} String,
    association_type LowCardinality(String),
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY ({from_key}, {to_key})
""".strip()
        ch_silver.execute_sql(ddl)

        insert_sql = f"""
INSERT INTO silver.{silver_table}
SELECT
    _from_id AS {from_key},
    _to_id AS {to_key},
    _association_type AS association_type,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL
""".strip()
        ch_silver.execute_sql(insert_sql)

        row_count = ch_silver.execute_sql(f"SELECT count() FROM silver.{silver_table}")
        context.log.info(f"silver.{silver_table}: {row_count} rows")

        yield MaterializeResult(
            metadata={
                "row_count": MetadataValue.int(int(row_count)),
                "table": MetadataValue.text(f"silver.{silver_table}"),
            }
        )

    return _asset


# Create bridge assets from config
_bridge_assets = {
    silver_table: _make_bridge_asset(silver_table, bronze_table, from_key, to_key)
    for silver_table, bronze_table, from_key, to_key in BRIDGE_TABLES
}
bridge_contact_company = _bridge_assets["bridge_contact_company"]
bridge_contact_deal = _bridge_assets["bridge_contact_deal"]
bridge_deal_company = _bridge_assets["bridge_deal_company"]
bridge_lead_contact = _bridge_assets["bridge_lead_contact"]
bridge_deal_lead = _bridge_assets["bridge_deal_lead"]
bridge_lead_company = _bridge_assets["bridge_lead_company"]


# ---------------------------------------------------------------------------
# Special bridge: bridge_activity_contact (UNION ALL across 5 assoc tables)
# ---------------------------------------------------------------------------

@asset(
    name="bridge_activity_contact",
    group_name="silver",
    deps=[
        AssetKey("hs_assoc_call_contact"),
        AssetKey("hs_assoc_meeting_contact"),
        AssetKey("hs_assoc_email_contact"),
        AssetKey("hs_assoc_note_contact"),
        AssetKey("hs_assoc_task_contact"),
    ],
)
def bridge_activity_contact(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    context.log.info("Rebuilding silver.bridge_activity_contact")
    ch_silver.execute_sql("DROP TABLE IF EXISTS silver.bridge_activity_contact")

    ddl = """
CREATE TABLE silver.bridge_activity_contact (
    activity_id String,
    activity_type LowCardinality(String),
    contact_id String,
    association_type LowCardinality(String),
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY (activity_id, contact_id)
""".strip()
    ch_silver.execute_sql(ddl)

    union_parts = []
    for activity_type, bronze_table in BRIDGE_ACTIVITY_CONTACT:
        part = f"""SELECT
    _from_id AS activity_id,
    '{activity_type}' AS activity_type,
    _to_id AS contact_id,
    _association_type AS association_type,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = "INSERT INTO silver.bridge_activity_contact\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.bridge_activity_contact")
    context.log.info(f"silver.bridge_activity_contact: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.bridge_activity_contact"),
        }
    )


# ---------------------------------------------------------------------------
# Special bridge: bridge_activity_company (UNION ALL across 5 assoc tables)
# ---------------------------------------------------------------------------

@asset(
    name="bridge_activity_company",
    group_name="silver",
    deps=[
        AssetKey("hs_assoc_call_company"),
        AssetKey("hs_assoc_meeting_company"),
        AssetKey("hs_assoc_email_company"),
        AssetKey("hs_assoc_note_company"),
        AssetKey("hs_assoc_task_company"),
    ],
)
def bridge_activity_company(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    context.log.info("Rebuilding silver.bridge_activity_company")
    ch_silver.execute_sql("DROP TABLE IF EXISTS silver.bridge_activity_company")

    ddl = """
CREATE TABLE silver.bridge_activity_company (
    activity_id String,
    activity_type LowCardinality(String),
    company_id String,
    association_type LowCardinality(String),
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY (activity_id, company_id)
""".strip()
    ch_silver.execute_sql(ddl)

    union_parts = []
    for activity_type, bronze_table in BRIDGE_ACTIVITY_COMPANY:
        part = f"""SELECT
    _from_id AS activity_id,
    '{activity_type}' AS activity_type,
    _to_id AS company_id,
    _association_type AS association_type,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = "INSERT INTO silver.bridge_activity_company\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.bridge_activity_company")
    context.log.info(f"silver.bridge_activity_company: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.bridge_activity_company"),
        }
    )


# ---------------------------------------------------------------------------
# Special bridge: bridge_activity_deal (UNION ALL across 5 assoc tables)
# ---------------------------------------------------------------------------

@asset(
    name="bridge_activity_deal",
    group_name="silver",
    deps=[
        AssetKey("hs_assoc_call_deal"),
        AssetKey("hs_assoc_meeting_deal"),
        AssetKey("hs_assoc_email_deal"),
        AssetKey("hs_assoc_note_deal"),
        AssetKey("hs_assoc_task_deal"),
    ],
)
def bridge_activity_deal(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    context.log.info("Rebuilding silver.bridge_activity_deal")
    ch_silver.execute_sql("DROP TABLE IF EXISTS silver.bridge_activity_deal")

    ddl = """
CREATE TABLE silver.bridge_activity_deal (
    activity_id String,
    activity_type LowCardinality(String),
    deal_id String,
    association_type LowCardinality(String),
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY (activity_id, deal_id)
""".strip()
    ch_silver.execute_sql(ddl)

    union_parts = []
    for activity_type, bronze_table in BRIDGE_ACTIVITY_DEAL:
        part = f"""SELECT
    _from_id AS activity_id,
    '{activity_type}' AS activity_type,
    _to_id AS deal_id,
    _association_type AS association_type,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = "INSERT INTO silver.bridge_activity_deal\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.bridge_activity_deal")
    context.log.info(f"silver.bridge_activity_deal: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.bridge_activity_deal"),
        }
    )


# ---------------------------------------------------------------------------
# DQ metrics (append-only)
# ---------------------------------------------------------------------------

_ALL_SILVER_DIM_ASSETS = [
    "dim_contacts", "dim_companies", "dim_deals", "dim_leads",
    # "dim_owners",  # blocked: needs crm.objects.owners.read scope
    "dim_pipelines", "dim_pipeline_stages",
]
_ALL_SILVER_FACT_ASSETS = ["fact_activities"]
_ALL_SILVER_BRIDGE_ASSETS = [
    "bridge_contact_company", "bridge_contact_deal", "bridge_deal_company",
    "bridge_lead_contact", "bridge_deal_lead", "bridge_lead_company",
    "bridge_activity_contact", "bridge_activity_company", "bridge_activity_deal",
]
_ALL_SILVER_TABLES = _ALL_SILVER_DIM_ASSETS + _ALL_SILVER_FACT_ASSETS + _ALL_SILVER_BRIDGE_ASSETS


@asset(
    name="dq_metrics",
    group_name="silver",
    deps=[AssetKey(t) for t in _ALL_SILVER_TABLES],
)
def dq_metrics(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    context.log.info("Running data quality checks")

    # Create table if not exists (never drop)
    ch_silver.execute_sql("""
CREATE TABLE IF NOT EXISTS silver.dq_metrics (
    measured_at DateTime,
    table_name LowCardinality(String),
    metric_name LowCardinality(String),
    metric_value Float64,
    detail String
) ENGINE = MergeTree() ORDER BY (table_name, metric_name, measured_at) TTL measured_at + INTERVAL 90 DAY
""".strip())

    metrics = []

    # Row counts for all silver tables
    for table in _ALL_SILVER_TABLES:
        try:
            count = int(ch_silver.execute_sql(f"SELECT count() FROM silver.{table}"))
        except Exception:
            count = 0
        metrics.append(f"(now(), '{table}', 'row_count', {count}, '')")

    # Null rate checks for dims
    null_checks = [
        ("dim_contacts", "email", "null_rate_email"),
        ("dim_companies", "name", "null_rate_name"),
        ("dim_deals", "dealname", "null_rate_dealname"),
    ]
    for table, col, metric_name in null_checks:
        try:
            rate = float(ch_silver.execute_sql(
                f"SELECT countIf({col} = '') / count() FROM silver.{table}"
            ))
        except Exception:
            rate = 0.0
        metrics.append(f"(now(), '{table}', '{metric_name}', {rate}, '')")

    # Archived rate for dim tables
    for table in _ALL_SILVER_DIM_ASSETS:
        try:
            rate = float(ch_silver.execute_sql(
                f"SELECT countIf(archived = 1) / count() FROM silver.{table}"
            ))
        except Exception:
            rate = 0.0
        metrics.append(f"(now(), '{table}', 'archived_rate', {rate}, '')")

    # Orphan checks for bridges
    orphan_checks = [
        ("bridge_contact_company", "contact_id", "dim_contacts", "contact_id"),
        ("bridge_contact_company", "company_id", "dim_companies", "company_id"),
        ("bridge_contact_deal", "contact_id", "dim_contacts", "contact_id"),
        ("bridge_contact_deal", "deal_id", "dim_deals", "deal_id"),
        ("bridge_deal_company", "deal_id", "dim_deals", "deal_id"),
        ("bridge_deal_company", "company_id", "dim_companies", "company_id"),
        ("bridge_lead_contact", "lead_id", "dim_leads", "lead_id"),
        ("bridge_lead_contact", "contact_id", "dim_contacts", "contact_id"),
        ("bridge_deal_lead", "deal_id", "dim_deals", "deal_id"),
        ("bridge_deal_lead", "lead_id", "dim_leads", "lead_id"),
        ("bridge_lead_company", "lead_id", "dim_leads", "lead_id"),
        ("bridge_lead_company", "company_id", "dim_companies", "company_id"),
        ("bridge_activity_contact", "activity_id", "fact_activities", "activity_id"),
        ("bridge_activity_company", "activity_id", "fact_activities", "activity_id"),
        ("bridge_activity_company", "company_id", "dim_companies", "company_id"),
        ("bridge_activity_deal", "activity_id", "fact_activities", "activity_id"),
        ("bridge_activity_deal", "deal_id", "dim_deals", "deal_id"),
    ]
    for bridge_table, bridge_col, dim_table, dim_col in orphan_checks:
        try:
            count = int(ch_silver.execute_sql(
                f"SELECT count() FROM silver.{bridge_table} "
                f"WHERE {bridge_col} NOT IN (SELECT {dim_col} FROM silver.{dim_table})"
            ))
        except Exception:
            count = 0
        metrics.append(
            f"(now(), '{bridge_table}', 'orphan_count_{bridge_col}', {count}, "
            f"'{bridge_col} NOT IN {dim_table}.{dim_col}')"
        )

    # Insert all metrics
    if metrics:
        values = ",\n".join(metrics)
        ch_silver.execute_sql(
            f"INSERT INTO silver.dq_metrics VALUES {values}"
        )

    total_metrics = len(metrics)
    context.log.info(f"Inserted {total_metrics} DQ metrics")

    yield MaterializeResult(
        metadata={
            "metrics_count": MetadataValue.int(total_metrics),
        }
    )


# ---------------------------------------------------------------------------
# Export all assets for definitions.py
# ---------------------------------------------------------------------------

all_silver_assets = [
    dim_contacts, dim_companies, dim_deals, dim_leads,
    # dim_owners,  # blocked: needs crm.objects.owners.read scope
    dim_pipelines, dim_pipeline_stages,
    fact_activities,
    bridge_contact_company, bridge_contact_deal, bridge_deal_company,
    bridge_lead_contact, bridge_deal_lead, bridge_lead_company,
    bridge_activity_contact, bridge_activity_company, bridge_activity_deal,
    dq_metrics,
]
