"""Silver fact assets: fact_activities, fact_form_submissions, fact_stage_history.

fact_activities and fact_stage_history compute their deps lists dynamically
against app.customer.extraction so disabled object types don't leak into the
Dagster graph as phantom external assets.
"""

from dagster import asset, AssetExecutionContext, AssetKey, MaterializeResult, MetadataValue

from resources.clickhouse import ClickHouseResource
from silver_config import FACT_ACTIVITIES, FACT_FORM_SUBMISSIONS
from app.customer import extraction as _ext
from .sql import _swap_table


# Bronze table name -> activity_type literal
_ACTIVITY_BRONZE = {
    "calls":    ("hs_calls",             "call"),
    "meetings": ("hs_meetings",          "meeting"),
    "emails":   ("hs_engagement_emails", "email"),
    "notes":    ("hs_notes",             "note"),
    "tasks":    ("hs_tasks",             "task"),
}




def _fact_activities_deps():
    enabled_bronze = _ext.get_enabled_bronze_tables()
    return [AssetKey(t) for _, (t, _lit) in _ACTIVITY_BRONZE.items() if t in enabled_bronze]


def _enabled_activity_bronze_map():
    enabled_bronze = _ext.get_enabled_bronze_tables()
    return {k: v for k, v in _ACTIVITY_BRONZE.items() if v[0] in enabled_bronze}


@asset(
    name="fact_activities",
    group_name="silver",
    deps=_fact_activities_deps(),
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
PARTITION BY toYear(toDate(hs_timestamp))
ORDER BY (activity_type, toDate(hs_timestamp), activity_id)
""".strip()
    ch_silver.execute_sql(ddl)

    # Build UNION ALL — only across activity types whose bronze is enabled
    enabled_activity_map = _enabled_activity_bronze_map()
    union_parts = []
    for act_key, mapping in FACT_ACTIVITIES.items():
        if act_key not in enabled_activity_map:
            continue
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
# Fact: fact_stage_history — unpivots HubSpot stage enter/exit timestamps
# Covers leads, deals, and contacts in a single table.
# Property names embed stage IDs (e.g. hs_date_entered_4967489725) which are
# discovered dynamically from the bronze properties map at build time.
# ---------------------------------------------------------------------------

# (bronze_table, entity_type, id_column, stage_lookup_table, required_object_key)
_STAGE_HISTORY_SOURCES_FULL = [
    ("hs_leads",    "lead",    "_record_id", "dim_lead_pipeline_stages", "leads"),
    ("hs_deals",    "deal",    "_record_id", "dim_pipeline_stages",      "deals"),
    ("hs_contacts", "contact", "_record_id", None,                       "contacts"),
]


def _enabled_stage_history_sources():
    enabled = _ext.get_enabled_objects()
    enabled_silver = _ext.get_enabled_silver_tables()
    out = []
    for bronze_table, entity_type, id_col, stage_table, required in _STAGE_HISTORY_SOURCES_FULL:
        if required not in enabled:
            continue
        # If a stage_table is referenced but the dim isn't built, drop the lookup
        if stage_table and stage_table not in enabled_silver:
            stage_table = None
        out.append((bronze_table, entity_type, id_col, stage_table))
    return out


_STAGE_HISTORY_SOURCES = _enabled_stage_history_sources()


def _fact_stage_history_deps():
    deps = []
    enabled_bronze = _ext.get_enabled_bronze_tables()
    enabled_silver = _ext.get_enabled_silver_tables()
    for bronze, _et, _id, stage, _req in _STAGE_HISTORY_SOURCES_FULL:
        if bronze in enabled_bronze:
            deps.append(AssetKey(bronze))
        if stage and stage in enabled_silver:
            deps.append(AssetKey(stage))
    return deps


@asset(
    name="fact_stage_history",
    group_name="silver",
    deps=_fact_stage_history_deps(),
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
PARTITION BY toYear(toDate(entered_at))
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

