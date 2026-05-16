"""Silver layer assets — config-driven dim/fact/bridge tables with full refresh."""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource
from silver_config import (
    DIM_CONTACTS, DIM_COMPANIES, DIM_DEALS, DIM_LEADS,
    DIM_OWNERS, DIM_PIPELINES, DIM_PIPELINE_STAGES,
    DIM_LEAD_PIPELINES, DIM_LEAD_PIPELINE_STAGES,
    FACT_ACTIVITIES, FACT_FORM_SUBMISSIONS, BRIDGE_TABLES,
    BRIDGE_ACTIVITY_CONTACT, BRIDGE_ACTIVITY_COMPANY, BRIDGE_ACTIVITY_DEAL,
    DICTIONARIES,
)


# ---------------------------------------------------------------------------
# Helpers: dictionary lifecycle + atomic table swap
# ---------------------------------------------------------------------------

def _drop_dependent_dicts(table_name: str, ch: ClickHouseResource, log) -> list[str]:
    """Drop dictionaries that depend on this table. Returns list of dict names dropped."""
    if table_name not in DICTIONARIES:
        return []
    dict_name = "dict_" + table_name.removeprefix("dim_")
    log.info(f"Dropping dependent dictionary silver.{dict_name}")
    ch.execute_sql(f"DROP DICTIONARY IF EXISTS silver.{dict_name}")
    return [table_name]


def _recreate_dicts(table_names: list[str], ch: ClickHouseResource, log):
    """Recreate dictionaries for the given table names."""
    for table_name in table_names:
        ddl = DICTIONARIES.get(table_name)
        if ddl:
            dict_name = "dict_" + table_name.removeprefix("dim_")
            log.info(f"Recreating dictionary silver.{dict_name}")
            ch.execute_sql(ddl.strip())


def _swap_table(ch: ClickHouseResource, table: str, log):
    """Atomic swap: silver.{table}_tmp -> silver.{table}. Handles dict lifecycle."""
    tmp = f"{table}_tmp"
    # Ensure target exists (first run) — same schema as tmp
    ch.execute_sql(f"CREATE TABLE IF NOT EXISTS silver.{table} AS silver.{tmp}")
    # Drop dependent dicts before swap
    dropped = _drop_dependent_dicts(table, ch, log)
    # Atomic swap — zero downtime
    log.info(f"EXCHANGE TABLES silver.{table} AND silver.{tmp}")
    ch.execute_sql(f"EXCHANGE TABLES silver.{table} AND silver.{tmp}")
    ch.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")
    # Recreate dicts pointing at new data
    _recreate_dicts(dropped, ch, log)


# ---------------------------------------------------------------------------
# Helpers: SQL generation from config
# ---------------------------------------------------------------------------

def _cast_expr(prop_key: str, ch_type: str, source: str = "properties") -> str:
    """Generate a ClickHouse SELECT expression with type casting."""
    if source == "json":
        raw_expr = f"JSONExtractString(_raw, '{prop_key}')"
    else:
        raw_expr = f"properties['{prop_key}']"

    # Strip LowCardinality wrapper — casting is the same, encoding handled by DDL
    inner_type = ch_type
    if ch_type.startswith("LowCardinality("):
        inner_type = ch_type[len("LowCardinality("):-1]

    if inner_type == "String":
        return raw_expr
    elif inner_type == "DateTime":
        return f"parseDateTimeBestEffortOrZero({raw_expr})"
    elif inner_type == "Nullable(Float64)":
        return f"toFloat64OrNull({raw_expr})"
    elif inner_type == "UInt32":
        return f"toUInt32OrZero({raw_expr})"
    elif inner_type == "Nullable(Int64)":
        return f"toInt64OrNull({raw_expr})"
    else:
        return raw_expr


def _build_ddl(
    table_name: str,
    primary_key: str,
    columns: list,
    source: str = "properties",
    *,
    order_by: str | None = None,
    partition_by: str | None = None,
) -> str:
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
    order_clause = order_by or f"({primary_key})"
    partition_clause = f"PARTITION BY {partition_by} " if partition_by else ""
    return (
        f"CREATE TABLE silver.{table_name} (\n"
        f"{cols_sql}\n"
        f") ENGINE = ReplacingMergeTree(_silver_loaded_at) "
        f"{partition_clause}ORDER BY {order_clause}"
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

CHUNK_SIZE = 50_000


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
        target = f"dim_{name}"
        tmp = f"{target}_tmp"

        context.log.info(f"Rebuilding silver.{target}")
        ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

        ddl = _build_ddl(tmp, primary_key, config["columns"], source,
                         order_by=config.get("order_by"),
                         partition_by=config.get("partition_by"))
        context.log.info(f"DDL: {ddl}")
        ch_silver.execute_sql(ddl)

        # Count unique bronze records to decide chunking (not total rows which includes dupes)
        bronze_count = int(ch_silver.execute_sql(
            f"SELECT uniq(_record_id) FROM bronze.{bronze_table}"
        ))
        context.log.info(f"Bronze {bronze_table}: {bronze_count} unique records")

        insert_sql = _build_insert(tmp, primary_key, config)

        context.log.info(f"INSERT: {insert_sql}")
        ch_silver.execute_sql(insert_sql)

        # Atomic swap
        _swap_table(ch_silver, target, context.log)

        row_count = ch_silver.execute_sql(f"SELECT count() FROM silver.{target}")
        context.log.info(f"silver.{target}: {row_count} rows")

        yield MaterializeResult(
            metadata={
                "row_count": MetadataValue.int(int(row_count)),
                "table": MetadataValue.text(f"silver.{target}"),
            }
        )

    return _asset


# Create standard dim assets
dim_contacts = _make_dim_asset("contacts", DIM_CONTACTS)
dim_companies = _make_dim_asset("companies", DIM_COMPANIES)
dim_leads = _make_dim_asset("leads", DIM_LEADS)
dim_owners = _make_dim_asset("owners", DIM_OWNERS)
dim_pipelines = _make_dim_asset("pipelines", DIM_PIPELINES)
dim_lead_pipelines = _make_dim_asset("lead_pipelines", DIM_LEAD_PIPELINES)


# ---------------------------------------------------------------------------
# Custom dim_deals: standard columns + denormalized labels from lookups
# ---------------------------------------------------------------------------

@asset(
    name="dim_deals",
    group_name="silver",
    deps=[
        AssetKey("hs_deals"),
        AssetKey("dim_pipelines"),
        AssetKey("dim_pipeline_stages"),
        AssetKey("dim_owners"),
    ],
)
def dim_deals(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    """dim_deals with denormalized pipeline_label, stage_label, owner_name."""
    target = "dim_deals"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.dim_deals (with denormalized labels)")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    config = DIM_DEALS
    primary_key = config["primary_key"]
    columns = config["columns"]
    order_by = config.get("order_by", "(deal_id)")
    partition_by = config.get("partition_by")

    # Build DDL with extra label columns
    col_defs = [f"    {primary_key} String"]
    for col_name, _prop_key, col_type in columns:
        col_defs.append(f"    {col_name} {col_type}")
    col_defs.append("    pipeline_label String")
    col_defs.append("    stage_label String")
    col_defs.append("    owner_name String")
    col_defs.append("    archived UInt8")
    col_defs.append("    _silver_loaded_at DateTime DEFAULT now()")

    partition_clause = f"PARTITION BY {partition_by} " if partition_by else ""
    ddl = (
        f"CREATE TABLE silver.{tmp} (\n"
        + ",\n".join(col_defs)
        + f"\n) ENGINE = ReplacingMergeTree(_silver_loaded_at) "
        + partition_clause
        + f"ORDER BY {order_by}"
    )
    ch_silver.execute_sql(ddl)

    # Build INSERT with dictGet() for denormalized labels (no JOINs)
    select_exprs = [f"    _record_id AS {primary_key}"]
    for col_name, prop_key, col_type in columns:
        expr = _cast_expr(prop_key, col_type, "properties")
        select_exprs.append(f"    {expr} AS {col_name}")
    select_exprs.append("    dictGet('silver.dict_pipelines', 'label', tuple(properties['pipeline'])) AS pipeline_label")
    select_exprs.append("    dictGet('silver.dict_pipeline_stages', 'label', tuple(properties['dealstage'])) AS stage_label")
    select_exprs.append(
        "    concat("
        "dictGet('silver.dict_owners', 'first_name', tuple(properties['hubspot_owner_id'])), "
        "' ', "
        "dictGet('silver.dict_owners', 'last_name', tuple(properties['hubspot_owner_id']))"
        ") AS owner_name"
    )
    select_exprs.append("    JSONExtractBool(_raw, 'archived') AS archived")
    select_exprs.append("    now() AS _silver_loaded_at")

    select_sql = ",\n".join(select_exprs)
    insert_sql = (
        f"INSERT INTO silver.{tmp}\n"
        f"SELECT\n{select_sql}\n"
        f"FROM bronze.hs_deals FINAL"
    )
    context.log.info(f"INSERT: {insert_sql}")
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.dim_deals")
    context.log.info(f"silver.dim_deals: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.dim_deals"),
        }
    )


# ---------------------------------------------------------------------------
# Special asset: dim_pipeline_stages (ARRAY JOIN)
# ---------------------------------------------------------------------------

@asset(
    name="dim_pipeline_stages",
    group_name="silver",
    deps=[AssetKey("hs_pipelines")],
)
def dim_pipeline_stages(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "dim_pipeline_stages"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.dim_pipeline_stages")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = _build_ddl(tmp, "stage_id", DIM_PIPELINE_STAGES["columns"], "nested_stages")
    context.log.info(f"DDL: {ddl}")
    ch_silver.execute_sql(ddl)

    insert_sql = f"""
INSERT INTO silver.{tmp}
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

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.dim_pipeline_stages")
    context.log.info(f"silver.dim_pipeline_stages: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.dim_pipeline_stages"),
        }
    )


# ---------------------------------------------------------------------------
# Special asset: dim_lead_pipeline_stages (ARRAY JOIN from lead pipelines)
# ---------------------------------------------------------------------------

@asset(
    name="dim_lead_pipeline_stages",
    group_name="silver",
    deps=[AssetKey("hs_lead_pipelines")],
)
def dim_lead_pipeline_stages(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "dim_lead_pipeline_stages"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.dim_lead_pipeline_stages")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = _build_ddl(tmp, "stage_id", DIM_LEAD_PIPELINE_STAGES["columns"], "nested_stages")
    ch_silver.execute_sql(ddl)

    insert_sql = f"""
INSERT INTO silver.{tmp}
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
FROM bronze.hs_lead_pipelines FINAL
ARRAY JOIN JSONExtractArrayRaw(_raw, 'stages') AS stage
""".strip()
    ch_silver.execute_sql(insert_sql)

    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.dim_lead_pipeline_stages")
    context.log.info(f"silver.dim_lead_pipeline_stages: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.dim_lead_pipeline_stages"),
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
    target = "fact_activities"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.fact_activities")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = f"""
CREATE TABLE silver.{tmp} (
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
) ENGINE = ReplacingMergeTree(_silver_loaded_at)
PARTITION BY toYYYYMM(toDate(hs_timestamp))
ORDER BY (activity_type, toDate(hs_timestamp), activity_id)
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

    insert_sql = f"INSERT INTO silver.{tmp}\n" + "\nUNION ALL\n".join(union_parts)
    context.log.info(f"INSERT: {insert_sql}")
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.fact_activities")
    context.log.info(f"silver.fact_activities: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.fact_activities"),
        }
    )


# ---------------------------------------------------------------------------
# Fact: fact_form_submissions (from hs_form_submissions bronze)
# ---------------------------------------------------------------------------

@asset(
    name="fact_form_submissions",
    group_name="silver",
    deps=[AssetKey("hs_form_submissions")],
)
def fact_form_submissions(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "fact_form_submissions"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.fact_form_submissions")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    config = FACT_FORM_SUBMISSIONS
    primary_key = config["primary_key"]
    columns = config["columns"]
    order_by = config.get("order_by", "(submission_id)")
    partition_by = config.get("partition_by")

    # Build DDL
    col_defs = [f"    {primary_key} String"]
    for col_name, _prop_key, col_type in columns:
        col_defs.append(f"    {col_name} {col_type}")
    col_defs.append("    archived UInt8")
    col_defs.append("    _silver_loaded_at DateTime DEFAULT now()")

    partition_clause = f"PARTITION BY {partition_by} " if partition_by else ""
    ddl = (
        f"CREATE TABLE silver.{tmp} (\n"
        + ",\n".join(col_defs)
        + f"\n) ENGINE = ReplacingMergeTree(_silver_loaded_at) "
        + partition_clause
        + f"ORDER BY {order_by}"
    )
    ch_silver.execute_sql(ddl)

    # Build INSERT — submitted_at is epoch ms, needs fromUnixTimestamp64Milli
    insert_sql = f"""
INSERT INTO silver.{tmp}
SELECT
    _record_id AS submission_id,
    properties['form_id'] AS form_id,
    properties['form_name'] AS form_name,
    toDateTime(toUInt64OrZero(properties['submitted_at']) / 1000) AS submitted_at,
    properties['page_url'] AS page_url,
    properties['email'] AS email,
    properties['firstname'] AS firstname,
    properties['lastname'] AS lastname,
    properties['company'] AS company,
    properties['jobtitle'] AS jobtitle,
    properties['phone'] AS phone,
    0 AS archived,
    now() AS _silver_loaded_at
FROM bronze.hs_form_submissions FINAL
""".strip()
    context.log.info(f"INSERT: {insert_sql}")
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql("SELECT count() FROM silver.fact_form_submissions")
    context.log.info(f"silver.fact_form_submissions: {row_count} rows")

    yield MaterializeResult(
        metadata={
            "row_count": MetadataValue.int(int(row_count)),
            "table": MetadataValue.text("silver.fact_form_submissions"),
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
        target = silver_table
        tmp = f"{target}_tmp"

        context.log.info(f"Rebuilding silver.{target}")
        ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

        ddl = f"""
CREATE TABLE silver.{tmp} (
    {from_key} String,
    {to_key} String,
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at) ORDER BY ({from_key}, {to_key})
""".strip()
        ch_silver.execute_sql(ddl)

        insert_sql = f"""
INSERT INTO silver.{tmp}
SELECT DISTINCT
    _from_id AS {from_key},
    _to_id AS {to_key},
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL
""".strip()
        ch_silver.execute_sql(insert_sql)

        # Atomic swap
        _swap_table(ch_silver, target, context.log)

        row_count = ch_silver.execute_sql(f"SELECT count() FROM silver.{target}")
        context.log.info(f"silver.{target}: {row_count} rows")

        yield MaterializeResult(
            metadata={
                "row_count": MetadataValue.int(int(row_count)),
                "table": MetadataValue.text(f"silver.{target}"),
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
    target = "bridge_activity_contact"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.bridge_activity_contact")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = f"""
CREATE TABLE silver.{tmp} (
    activity_id String,
    activity_type LowCardinality(String),
    contact_id String,
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
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = f"INSERT INTO silver.{tmp}\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

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
    target = "bridge_activity_company"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.bridge_activity_company")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = f"""
CREATE TABLE silver.{tmp} (
    activity_id String,
    activity_type LowCardinality(String),
    company_id String,
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
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = f"INSERT INTO silver.{tmp}\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

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
    target = "bridge_activity_deal"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.bridge_activity_deal")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ddl = f"""
CREATE TABLE silver.{tmp} (
    activity_id String,
    activity_type LowCardinality(String),
    deal_id String,
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
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL"""
        union_parts.append(part)

    insert_sql = f"INSERT INTO silver.{tmp}\n" + "\nUNION ALL\n".join(union_parts)
    ch_silver.execute_sql(insert_sql)

    # Atomic swap
    _swap_table(ch_silver, target, context.log)

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
    "dim_owners",
    "dim_pipelines", "dim_pipeline_stages",
    "dim_lead_pipelines", "dim_lead_pipeline_stages",
]
_ALL_SILVER_FACT_ASSETS = ["fact_activities", "fact_form_submissions"]
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
# Fact: fact_stage_history — unpivots HubSpot stage enter/exit timestamps
# Covers leads, deals, and contacts in a single table.
# Property names embed stage IDs (e.g. hs_date_entered_4967489725) which are
# discovered dynamically from the bronze properties map at build time.
# ---------------------------------------------------------------------------

# (bronze_table, entity_type, id_column, stage_lookup_table)
_STAGE_HISTORY_SOURCES = [
    ("hs_leads",    "lead",    "_record_id", "dim_lead_pipeline_stages"),
    ("hs_deals",    "deal",    "_record_id", "dim_pipeline_stages"),
    ("hs_contacts", "contact", "_record_id", None),  # lifecycle stages, no lookup table
]


@asset(
    name="fact_stage_history",
    group_name="silver",
    deps=[
        AssetKey("hs_leads"),
        AssetKey("hs_deals"),
        AssetKey("hs_contacts"),
        AssetKey("dim_lead_pipeline_stages"),
        AssetKey("dim_pipeline_stages"),
    ],
)
def fact_stage_history(context: AssetExecutionContext, ch_silver: ClickHouseResource):
    target = "fact_stage_history"
    tmp = f"{target}_tmp"

    context.log.info("Rebuilding silver.fact_stage_history")
    ch_silver.execute_sql(f"DROP TABLE IF EXISTS silver.{tmp}")

    ch_silver.execute_sql(f"""
CREATE TABLE silver.{tmp} (
    entity_type LowCardinality(String),
    entity_id String,
    stage_id String,
    stage_label String,
    entered_at DateTime,
    exited_at Nullable(DateTime),
    duration_ms Nullable(Int64),
    _silver_loaded_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(_silver_loaded_at)
PARTITION BY toYYYYMM(toDate(entered_at))
ORDER BY (entity_type, stage_id, entity_id)
""".strip())

    total_rows = 0
    for bronze_table, entity_type, id_col, stage_table in _STAGE_HISTORY_SOURCES:
        # Discover all stage IDs from hs_date_entered_* or hs_v2_date_entered_* properties.
        # Subquery materializes a single record first, then arrayJoin expands its keys.
        stage_ids_rows = ch_silver.execute_sql(f"""
SELECT DISTINCT
    replaceRegexpOne(k, '^hs_(v2_)?date_entered_', '') AS stage_id
FROM (
    SELECT arrayJoin(mapKeys(props)) AS k
    FROM (SELECT properties AS props FROM bronze.{bronze_table} LIMIT 1)
)
WHERE match(k, '^hs_(v2_)?date_entered_')
  AND k NOT IN ('hs_v2_date_entered_current_stage', 'hs_date_entered_current_stage')
""")
        if not stage_ids_rows:
            context.log.info(f"No stage enter properties found for {bronze_table}")
            continue

        # Parse comma/newline separated result
        if isinstance(stage_ids_rows, str):
            stage_ids = [s.strip() for s in stage_ids_rows.replace("\n", ",").split(",") if s.strip()]
        else:
            stage_ids = [str(stage_ids_rows)]

        context.log.info(f"{bronze_table}: found {len(stage_ids)} stage IDs")

        # Insert one stage at a time to avoid a massive UNION ALL that
        # triggers N concurrent FINAL scans of the same bronze table.
        # HubSpot uses both hs_date_entered_* and hs_v2_date_entered_* patterns.
        import re as _re
        for stage_id in stage_ids:
            entered_v1 = f"hs_date_entered_{stage_id}"
            entered_v2 = f"hs_v2_date_entered_{stage_id}"
            exited_v1 = f"hs_date_exited_{stage_id}"
            exited_v2 = f"hs_v2_date_exited_{stage_id}"
            time_v1 = f"hs_time_in_{stage_id}"
            time_v2 = f"hs_v2_latest_time_in_{stage_id}"

            entered_expr = f"if(properties['{entered_v2}'] != '', properties['{entered_v2}'], properties['{entered_v1}'])"
            exited_expr = f"if(properties['{exited_v2}'] != '', properties['{exited_v2}'], properties['{exited_v1}'])"
            time_expr = f"if(properties['{time_v2}'] != '', properties['{time_v2}'], properties['{time_v1}'])"

            normalized = _re.sub(r'_\d+$', '', stage_id).replace('_', '-')

            if stage_table:
                label_expr = (
                    f"ifNull((SELECT label FROM silver.{stage_table} "
                    f"WHERE stage_id IN ('{stage_id}', '{normalized}') AND archived = 0 LIMIT 1), '{stage_id}')"
                )
            else:
                label_expr = f"'{stage_id}'"

            insert_sql = f"""
INSERT INTO silver.{tmp}
SELECT
    '{entity_type}' AS entity_type,
    {id_col} AS entity_id,
    '{stage_id}' AS stage_id,
    {label_expr} AS stage_label,
    parseDateTimeBestEffortOrZero({entered_expr}) AS entered_at,
    if({exited_expr} != '',
       parseDateTimeBestEffortOrZero({exited_expr}),
       NULL) AS exited_at,
    toInt64OrNull({time_expr}) AS duration_ms,
    now() AS _silver_loaded_at
FROM bronze.{bronze_table} FINAL
WHERE properties['{entered_v1}'] != '' OR properties['{entered_v2}'] != ''
""".strip()
            ch_silver.execute_sql(insert_sql)

        count = ch_silver.execute_sql(
            f"SELECT count() FROM silver.{tmp} WHERE entity_type = '{entity_type}'"
        )
        context.log.info(f"{entity_type}: {count} stage history rows")
        total_rows += int(count) if count else 0

    _swap_table(ch_silver, target, context.log)

    row_count = ch_silver.execute_sql(f"SELECT count() FROM silver.{target}")
    context.log.info(f"silver.{target}: {row_count} rows total")

    yield MaterializeResult(metadata={
        "row_count": MetadataValue.int(int(row_count)),
        "table": MetadataValue.text(f"silver.{target}"),
    })


# ---------------------------------------------------------------------------
# Export all assets for definitions.py
# ---------------------------------------------------------------------------

all_silver_assets = [
    dim_contacts, dim_companies, dim_deals, dim_leads,
    dim_owners,
    dim_pipelines, dim_pipeline_stages,
    dim_lead_pipelines, dim_lead_pipeline_stages,
    fact_activities, fact_form_submissions, fact_stage_history,
    bridge_contact_company, bridge_contact_deal, bridge_deal_company,
    bridge_lead_contact, bridge_deal_lead, bridge_lead_company,
    bridge_activity_contact, bridge_activity_company, bridge_activity_deal,
    dq_metrics,
]
