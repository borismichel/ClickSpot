# Data Pipeline

hs2ch runs an hourly ELT pipeline orchestrated by **Dagster**, extracting data from HubSpot's CRM APIs and loading it through a three-layer medallion architecture in ClickHouse.

---

## Medallion Architecture

```
HubSpot CRM API
      |
      v
  +---------+     +---------+     +---------+
  | BRONZE  | --> | SILVER  | --> |  GOLD   |
  |  (raw)  |    | (typed) |    |  (agg)  |
  +---------+     +---------+     +---------+
   13 tables       20 tables       4 tables
```

| Layer | Purpose | Engine | Refresh Strategy |
|-------|---------|--------|------------------|
| **Bronze** | Raw extraction from HubSpot. Safety net — nothing is lost. | `ReplacingMergeTree(_extracted_at)` | Incremental (high-water mark on `lastmodifieddate`) |
| **Silver** | Clean, typed dimensions, facts, and bridges. No business logic. | `ReplacingMergeTree(_silver_loaded_at)` | Full rebuild (DROP + CREATE + INSERT) |
| **Gold** | Pre-computed aggregates for analytics. | `ReplacingMergeTree(_gold_loaded_at)` | Full rebuild |

---

## Bronze Layer

Bronze assets extract raw HubSpot data and store it as-is. Every record preserves the full JSON response in `_raw` and a flattened `properties Map(String, String)` for quick access.

### Schema

Every bronze table shares the same shape:

```sql
CREATE TABLE bronze.<table_name> (
    _record_id    String,          -- HubSpot object ID
    _extracted_at DateTime,        -- When we pulled this record
    properties    Map(String, String),  -- Flattened property map
    _raw          String           -- Full JSON response
) ENGINE = ReplacingMergeTree(_extracted_at)
  ORDER BY (_record_id)
```

`ReplacingMergeTree` deduplicates by `_record_id`, keeping the row with the latest `_extracted_at`.

### Assets

#### CRM Objects (5 assets)

| Asset | HubSpot API | Notes |
|-------|-------------|-------|
| `hs_contacts` | `/crm/v3/objects/contacts` | Incremental via `lastmodifieddate` |
| `hs_companies` | `/crm/v3/objects/companies` | Incremental via `lastmodifieddate` |
| `hs_deals` | `/crm/v3/objects/deals` | Incremental via `lastmodifieddate` |
| `hs_leads` | `/crm/v3/objects/leads` | Incremental via `lastmodifieddate` |
| `hs_owners` | `/crm/v3/owners` | Full load (no search API for owners) |

Built with `_make_crm_asset()` factory in `assets/crm.py`.

#### Activities (5 assets)

| Asset | HubSpot API | Type Discriminator |
|-------|-------------|-------------------|
| `hs_calls` | `/crm/v3/objects/calls` | `call` |
| `hs_meetings` | `/crm/v3/objects/meetings` | `meeting` |
| `hs_engagement_emails` | `/crm/v3/objects/emails` | `email` |
| `hs_notes` | `/crm/v3/objects/notes` | `note` |
| `hs_tasks` | `/crm/v3/objects/tasks` | `task` |

Built with the same `_make_crm_asset()` factory in `assets/activities.py`.

#### Marketing (3 assets)

| Asset | HubSpot API | Notes |
|-------|-------------|-------|
| `hs_pipelines` | `/crm/v3/pipelines/deals` | Contains nested `stages` array |
| `hs_lead_pipelines` | `/crm/v3/pipelines/leads` | Contains nested `stages` array |
| `hs_campaigns` | `/marketing/v3/campaigns` | Full load |
| `hs_forms` | `/marketing/v3/forms` | Full load |

Built with `_make_marketing_asset()` factory in `assets/marketing.py`.

#### Associations (15 bridge assets)

HubSpot associations are **N:M:N** — a contact can be associated with many deals, and a deal with many contacts, each with a typed association label.

**CRM-to-CRM (6):**
- `hs_assoc_contact_company`, `hs_assoc_contact_deal`, `hs_assoc_deal_company`
- `hs_assoc_lead_contact`, `hs_assoc_deal_lead`, `hs_assoc_lead_company`

**Activity-to-CRM (9):**
- 5 activity types x 3 CRM objects (contacts, companies, deals):
  `hs_assoc_call_contact`, `hs_assoc_meeting_contact`, `hs_assoc_email_contact`, etc.

Each association record contains `(_from_id, _to_id, _association_type)`.

Built with `_make_association_asset()` factory in `assets/associations.py`.

### Incremental Ingestion

Bronze assets use a high-water mark strategy:

1. **First run:** Full load via HubSpot's List API (no 10k limit).
2. **Subsequent runs:** Search API with `lastmodifieddate > (last_run - 5min)`. The 5-minute overlap buffer handles clock drift and in-flight writes.
3. **Deduplication:** ClickHouse's `ReplacingMergeTree` keeps only the latest version per `_record_id`.

### Rate Limiting

HubSpot enforces 150 requests per 10 seconds. `HubSpotResource` handles this with:
- Automatic 429 retry with exponential backoff (up to 5 retries)
- Batch pagination (100 records per page)

---

## Silver Layer

Silver transforms bronze data into typed, query-ready dimensional tables. Configuration-driven — adding a property is a one-line change in `silver_config.py`.

### Configuration

`silver_config.py` is the single source of truth. Each dimension is a dict with a column list of `(silver_column_name, bronze_property_key, clickhouse_type)` tuples.

```python
# Example: adding a new property
DIM_DEALS = {
    "bronze_table": "hs_deals",
    "primary_key": "deal_id",
    "columns": [
        ("dealname",    "dealname",    "String"),
        ("amount",      "amount",      "Nullable(Float64)"),
        ("closedate",   "closedate",   "DateTime"),
        # Add new property here:
        ("new_field",   "hs_new_field", "String"),
    ],
}
```

### Dimension Tables (10)

| Table | Source | Primary Key | Key Columns |
|-------|--------|-------------|-------------|
| `dim_contacts` | `hs_contacts` | `contact_id` | `full_name`, `email`, `lifecyclestage`, `hs_analytics_source` |
| `dim_companies` | `hs_companies` | `company_id` | `name`, `domain`, `industry`, `country` |
| `dim_deals` | `hs_deals` | `deal_id` | `dealname`, `amount`, `dealstage`, `pipeline`, `closedate`, `owner_name` (denormalized) |
| `dim_leads` | `hs_leads` | `lead_id` | `hs_pipeline`, `hs_lead_status`, `hs_lead_type` |
| `dim_owners` | `hs_owners` | `owner_id` | `first_name`, `last_name`, `email` |
| `dim_pipelines` | `hs_pipelines` | `pipeline_id` | `label` |
| `dim_pipeline_stages` | `hs_pipelines` (ARRAY JOIN) | `stage_id` | `label`, `pipeline_id`, `is_closed`, `display_order` |
| `dim_lead_pipelines` | `hs_lead_pipelines` | `pipeline_id` | `label` |
| `dim_lead_pipeline_stages` | `hs_lead_pipelines` (ARRAY JOIN) | `stage_id` | `label`, `pipeline_id`, `is_closed` |

**Special cases:**
- **`dim_deals`** denormalizes `pipeline_label`, `stage_label`, and `owner_name` via LEFT JOINs to pipelines, stages, and owners at load time.
- **`dim_pipeline_stages`** and **`dim_lead_pipeline_stages`** use `ARRAY JOIN` to flatten nested stage arrays from pipeline records.

### Fact Table (1)

| Table | Source | Primary Key | Discriminator |
|-------|--------|-------------|---------------|
| `fact_activities` | 5 bronze activity tables | `activity_id` | `activity_type` ('call', 'meeting', 'email', 'note', 'task') |

Built as a UNION ALL across all 5 activity bronze tables, with a `activity_type` discriminator column.

### Bridge Tables (9)

| Table | From Key | To Key | Source |
|-------|----------|--------|--------|
| `bridge_contact_company` | `contact_id` | `company_id` | `hs_assoc_contact_company` |
| `bridge_contact_deal` | `contact_id` | `deal_id` | `hs_assoc_contact_deal` |
| `bridge_deal_company` | `deal_id` | `company_id` | `hs_assoc_deal_company` |
| `bridge_lead_contact` | `lead_id` | `contact_id` | `hs_assoc_lead_contact` |
| `bridge_deal_lead` | `deal_id` | `lead_id` | `hs_assoc_deal_lead` |
| `bridge_lead_company` | `lead_id` | `company_id` | `hs_assoc_lead_company` |
| `bridge_activity_contact` | `activity_id` | `contact_id` | 5 activity-contact assoc tables |
| `bridge_activity_company` | `activity_id` | `company_id` | 5 activity-company assoc tables |
| `bridge_activity_deal` | `activity_id` | `deal_id` | 5 activity-deal assoc tables |

### ClickHouse Dictionaries (6)

Silver tables that serve as lookup references have in-memory dictionaries for fast joins:

| Dictionary | Source Table | Key | Values |
|-----------|-------------|-----|--------|
| `dict_owners` | `dim_owners` | `owner_id` | `first_name`, `last_name`, `email` |
| `dict_pipelines` | `dim_pipelines` | `pipeline_id` | `label` |
| `dict_pipeline_stages` | `dim_pipeline_stages` | `stage_id` | `label`, `pipeline_id`, `is_closed`, `display_order` |
| `dict_contacts` | `dim_contacts` | `contact_id` | `full_name`, `email` |
| `dict_companies` | `dim_companies` | `company_id` | `name`, `domain`, `industry` |
| `dict_deals` | `dim_deals` | `deal_id` | `dealname`, `amount`, `owner_name` |

Dictionaries use `COMPLEX_KEY_HASHED` layout and auto-refresh every 5-10 minutes. During silver refresh, dependent dictionaries are dropped before the table and recreated after.

### Data Quality

The `dq_metrics` asset runs after all silver tables and records:
- **Row counts** per table
- **Null rates** for critical fields (`email`, `name`, `dealname`)
- **Archived rates** per dimension
- **Orphan counts** for bridge table foreign keys

Metrics are stored in `silver.dq_metrics` (append-only, 90-day TTL).

### Refresh Strategy

Silver uses a full-rebuild approach:

```
1. DROP DICTIONARY (if dependent)
2. DROP TABLE IF EXISTS
3. CREATE TABLE
4. INSERT INTO ... SELECT FROM bronze.* FINAL
5. CREATE DICTIONARY (if applicable)
```

This avoids migration complexity. ClickHouse's columnar storage makes full rebuilds fast (typically under 10 seconds for datasets up to 100K records per table).

---

## Gold Layer

Gold tables contain pre-computed aggregates optimized for analytics dashboards. They join multiple silver tables and compute business metrics.

### Aggregate Tables (4)

#### `agg_rep_performance`

Monthly sales rep performance metrics.

| Column | Type | Description |
|--------|------|-------------|
| `hubspot_owner_id` | String | Rep identifier |
| `owner_name` | String | Denormalized rep name |
| `period_start` | Date | First day of month |
| `deals_won` / `deals_lost` / `deals_created` | UInt32 | Deal counts |
| `win_rate` | Float64 | Won / (Won + Lost) |
| `total_arr_closed` | Float64 | Sum of ARR on closed-won deals |
| `avg_deal_size` | Float64 | Average deal amount |
| `avg_days_to_close` | Float64 | Average close cycle |
| `pipeline_value` | Float64 | Sum of open deal amounts |
| `calls_count` / `meetings_count` / `emails_count` / `tasks_count` | UInt32 | Activity counts via bridges |
| `total_activities` | UInt32 | Sum of all activities |

#### `agg_deal_health`

Per-deal health indicators for pipeline management.

| Column | Type | Description |
|--------|------|-------------|
| `deal_id` | String | Deal identifier |
| `days_in_current_stage` | Int32 | Days since last stage change |
| `days_since_last_activity` | Int32 | Days since any associated activity |
| `last_activity_date` / `last_activity_type` | DateTime / String | Most recent activity |
| `has_future_activity` | UInt8 | Boolean: scheduled future activity exists |
| `is_stale` | UInt8 | >14 days with no activity |
| `missing_amount` / `missing_closedate` / `missing_owner` | UInt8 | Data quality flags |

#### `agg_source_attribution`

Lead source attribution funnel.

| Column | Type | Description |
|--------|------|-------------|
| `hs_analytics_source` | String | Top-level source (ORGANIC, PAID, REFERRAL, etc.) |
| `hs_analytics_source_data_1` | String | Source detail |
| `contacts_count` / `mql_count` / `sql_count` | UInt32 | Funnel stage counts |
| `deals_associated` / `deals_won` | UInt32 | Deal conversion counts |
| `closed_won_value` | Float64 | Total closed-won deal value |

#### `fact_pipeline_snapshots`

Daily pipeline state snapshots for trend analysis.

| Column | Type | Description |
|--------|------|-------------|
| `snapshot_date` | Date | Snapshot date |
| `pipeline` | String | Pipeline ID |
| `total_open_deals` / `total_pipeline_value` | UInt32 / Float64 | Open pipeline state |
| `weighted_pipeline_value` | Float64 | Probability-weighted value |
| `closed_won_value` | Float64 | Already-closed value |

---

## Orchestration

### Dagster Jobs

| Job | Assets | Purpose |
|-----|--------|---------|
| `bronze_job` | All bronze + association assets | Extract from HubSpot |
| `silver_job` | All silver dim/fact/bridge + DQ | Transform to typed tables |
| `gold_job` | All gold aggregates | Compute analytics |
| `full_pipeline_job` | All of the above, dependency-ordered | End-to-end refresh |

### Schedule

```python
@schedule(cron_schedule="0 * * * *", job=full_pipeline_job)
```

Runs the full pipeline every hour on the hour.

### Resources

| Resource | Class | Target |
|----------|-------|--------|
| `hubspot` | `HubSpotResource` | HubSpot CRM API |
| `ch` | `ClickHouseResource` | `bronze` database |
| `ch_silver` | `ClickHouseResource` | `silver` database |
| `ch_gold` | `ClickHouseResource` | `gold` database |

### Dagster Home

Set `DAGSTER_HOME` in `.env` to persist run history, schedules, and asset materialization state across restarts. Without it, Dagster uses a temporary directory that is lost on exit.

---

## Adding New Data

### New HubSpot CRM Object

```python
# assets/crm.py — one line
hs_tickets = _make_crm_asset("tickets", "hs_tickets")
```

### New Silver Property

```python
# silver_config.py — one tuple
DIM_DEALS["columns"].append(
    ("new_field", "hs_new_field_name", "String"),
)
```

### New Silver Dimension

1. Add config block to `silver_config.py`
2. Call `_make_dim_asset("new_table", NEW_CONFIG)` in `assets/silver.py`
3. Add to `all_silver_assets` list

### New Association Bridge

```python
# assets/associations.py — one line
hs_assoc_ticket_contact = _make_association_asset("ticket", "contact")
```

Then add the silver bridge in `silver_config.py` BRIDGE_TABLES and `assets/silver.py`.

### New Computed Metric

```python
# app/engine/metrics.py
COMPUTED_METRICS["new_metric"] = {
    "label": "New Metric",
    "format": "percent",  # or "currency", "number"
    "table": "dim_deals",
    "sql": "countIf(condition) / nullIf(count(), 0)",
}
```
