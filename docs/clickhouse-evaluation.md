# ClickHouse Architecture Evaluation

**Context:** HubSpot CRM ELT pipeline (bronze/silver/gold medallion) with ~200K contacts, ~10K deals, ~1.5K leads, hourly full loads. Evaluated against ClickHouse best practices with an eye toward 100x-1000x scale.

---

## Current State Summary

| Area | Verdict | Notes |
|------|---------|-------|
| Engine choice | Good | ReplacingMergeTree everywhere is correct for CDC/full-load patterns |
| ORDER BY keys | Weak | Single-column PKs miss the main query patterns entirely |
| Data types | Weak | String overuse, Nullable overuse, no LowCardinality on obvious candidates |
| Partitioning | Missing | None on any table — fine at current scale, fatal at 100x |
| Skip indexes | Missing | Zero secondary indexes anywhere |
| Projections | Missing | No projections — gold layer is doing what projections should do |
| Refresh strategy | Risky | DROP+CREATE+INSERT causes downtime windows; doesn't scale |
| Bronze schema | Suboptimal | `Map(String, String)` + `_raw String` stores everything twice |
| Container config | Minimal | No memory limits, no ClickHouse server tuning |
| Connection mgmt | Weak | New client per operation, no connection reuse |

---

## 1. ORDER BY Key Design

**Problem:** Every table uses `ORDER BY (primary_key)` — a single unique ID column. This is the worst possible ordering for an analytical database. ClickHouse's sparse index works by skipping granules (8192 rows by default). When data is ordered by a unique ID, every query scans every granule because the ID provides zero locality.

**What queries actually do:**
- `dim_deals`: Almost always filtered by `archived`, `pipeline_label`, `hs_is_closed`, then ranged on `closedate` or `createdate`
- `dim_contacts`: Filtered by `archived`, `lifecyclestage`, `hs_analytics_source`, ranged on `createdate`
- `fact_activities`: Filtered by `archived`, `activity_type`, ranged on `hs_timestamp`
- `bridge_*`: Always looked up by one of the two FK columns

**Recommendations:**

```
dim_deals:       ORDER BY (pipeline, archived, toDate(closedate), deal_id)
dim_contacts:    ORDER BY (archived, lifecyclestage, toDate(createdate), contact_id)
dim_companies:   ORDER BY (archived, toDate(createdate), company_id)
dim_leads:       ORDER BY (archived, hs_pipeline, toDate(createdate), lead_id)
fact_activities:  ORDER BY (activity_type, toDate(hs_timestamp), activity_id)
fact_form_submissions: ORDER BY (form_id, toDate(submitted_at), submission_id)
```

**Why this order:** Low cardinality columns first (archived has 2 values, pipeline ~5, activity_type ~5), then the most common range filter (date), then the unique ID last. This follows ClickHouse's cardinal rule: ascending cardinality in the key.

**Impact at 100x:** On dim_deals with 1M rows, a query filtering `pipeline_label = 'Main Sales Pipeline' AND closedate >= '2026-01-01'` would scan ~200K rows instead of 1M. At 1000x (10M rows) the difference is 10M vs ~2M granules scanned.

**Bridge tables** should reverse the key for the less-queried direction using a projection (see section 6).

---

## 2. Data Types

### 2a. String overuse

Many columns are `String` when they have <100 distinct values. ClickHouse's `LowCardinality(String)` dictionary-encodes these, reducing storage 5-20x and speeding up GROUP BY.

**Should be LowCardinality(String):**
- `pipeline`, `pipeline_label`, `dealstage`, `stage_label` (~10-20 values)
- `hs_is_closed`, `hs_is_closed_won` (2 values — `'true'`/`'false'`)
- `hs_manual_forecast_category` (5 values)
- `lifecyclestage` (~8 values)
- `hs_analytics_source` (~15 values)
- `hs_lead_status`, `hs_lead_type` (~5 values each)
- `closedlost_reason`, `won_reason` (~10-20 values)
- `deal_currency_code` (1-3 values)
- `new_logo`, `renewal`, `partner` (mostly blank or a few values)

**Actual booleans stored as String `'true'`/`'false'`:**
- `hs_is_closed`, `hs_is_closed_won`, `is_closed` (on stages)
- These could be `UInt8` (0/1), which is 1 byte vs 4-5 bytes, and enables arithmetic (`SUM(is_closed_won)` instead of `countIf(hs_is_closed_won = 'true')`)
- **Caveat:** This is a bigger refactor since the LLM prompt and all SQL patterns reference string comparisons. Worth doing at scale, but not the highest priority.

### 2b. Nullable overuse

`Nullable(Float64)` adds a separate null bitmap column per nullable field, doubling the number of columns ClickHouse must read. From the docs: "Always prefer default values over Nullable... Nullable almost always negatively impacts performance."

**Current:** 20+ Nullable(Float64) columns in dim_deals alone.

**Fix:** Use `Float64 DEFAULT 0` for amounts, counts, rates. Only use Nullable when the distinction between 0 and "not set" is business-critical (rare — most are just "missing means zero").

### 2c. DateTime precision

All date columns use `DateTime` (second precision, 4 bytes). Many are just dates (closedate, createdate) that don't need time. `Date` is 2 bytes — half the storage, better compression, faster comparison.

**Recommendation:** Use `Date` for `closedate`, `createdate`, `period_start`, `cohort_month`, `snapshot_date`, stage-entry dates. Keep `DateTime` only where time matters (`hs_timestamp`, `_extracted_at`, `submitted_at`).

---

## 3. Partitioning

**Current:** Zero partitioning anywhere.

**Problem at scale:** Without partitioning, every `DROP TABLE` + `CREATE TABLE` is atomic — the table is unavailable during rebuild. At 100x scale, the contacts INSERT takes minutes. At 1000x, it takes 10+ minutes. Every query during that window fails.

**Recommendation for silver/gold tables:**

```sql
-- dim_deals: partition by month of creation
PARTITION BY toYYYYMM(createdate)

-- fact_activities: partition by month of activity timestamp
PARTITION BY toYYYYMM(hs_timestamp)

-- fact_form_submissions: partition by month
PARTITION BY toYYYYMM(submitted_at)

-- agg_rep_performance: already has period_start, natural partition
PARTITION BY toYYYYMM(period_start)

-- fact_pipeline_snapshots: partition by month of snapshot
PARTITION BY toYYYYMM(snapshot_date)
```

**Why:** Partitioning enables `ALTER TABLE ... REPLACE PARTITION` — swap new data in atomically with zero downtime. It also enables partition pruning: a query for "deals closed this quarter" only touches 3 partitions instead of the full table.

**Bronze tables** could partition by `toYYYYMM(_extracted_at)` to enable efficient TTL cleanup of old extractions.

**Don't over-partition:** ClickHouse docs warn against >1000 partitions. Monthly granularity is ideal for this data volume. Never partition by day at current scale.

---

## 4. Refresh Strategy — DROP+CREATE vs. Atomic Swap

**Current:** Every silver/gold table does `DROP TABLE IF EXISTS` → `CREATE TABLE` → `INSERT INTO ... SELECT`. During the window between DROP and INSERT completion, queries return "table not found" errors.

**Problem at scale:** A 20M-row contacts table takes several minutes to rebuild. The dashboard and LLM chat are broken during that window.

**Better pattern — atomic swap with EXCHANGE:**

```sql
-- 1. Build into a staging table
CREATE TABLE silver.dim_deals_new (...)
INSERT INTO silver.dim_deals_new SELECT ...

-- 2. Atomic swap (ClickHouse native, zero downtime)
EXCHANGE TABLES silver.dim_deals AND silver.dim_deals_new

-- 3. Clean up
DROP TABLE silver.dim_deals_new
```

`EXCHANGE TABLES` is atomic — queries never see an empty or missing table. This is critical at any scale where queries run concurrently with refreshes.

**Alternative with partitions:** If partitioned, use `ALTER TABLE REPLACE PARTITION` to swap individual months without touching the rest of the table.

---

## 5. Bronze Layer — Map + Raw JSON Duplication

**Current:** Every bronze row stores the same data twice:
- `properties Map(String, String)` — all properties flattened into a map
- `_raw String` — the full JSON response

At 200K contacts with ~100 properties each, this roughly doubles storage. At 100x scale (20M contacts), the `_raw` column alone is hundreds of GB.

**Options:**

1. **Drop `_raw`, keep `Map`:** If all silver transforms can work from the Map column (most already do), `_raw` is pure waste. Only `dim_owners` and `dim_pipeline_stages` use `_raw` (JSON extraction) — these could be switched to Map with renamed keys at bronze insert time.

2. **Drop `Map`, keep `_raw` as JSON type:** ClickHouse's native `JSON` type (v24.8+) supports typed sub-columns and compression. Queries like `_raw.properties.email` compile to direct column reads. This eliminates the Map overhead entirely. **This is the forward-looking choice** but requires ClickHouse 24.8+.

3. **Keep both, compress `_raw`:** If you need raw audit trail, store `_raw` with `CODEC(ZSTD(3))` to cut its size ~5x.

**Immediate win:** Add codec to `_raw`:
```sql
_raw String CODEC(ZSTD(3))
```

---

## 6. Projections — Replacing Gold Aggregates

**Insight:** The gold layer (agg_rep_performance, agg_deal_stage_funnel, agg_source_attribution, agg_deal_cohorts) is manually doing what ClickHouse projections do natively.

**What projections do:** A projection is a hidden materialized view stored inside the table. ClickHouse automatically routes queries to the projection when it matches the query's GROUP BY + WHERE pattern. No separate table, no refresh job, no staleness.

**Example — replace agg_deal_stage_funnel:**

```sql
ALTER TABLE silver.dim_deals
ADD PROJECTION agg_by_pipeline_stage (
    SELECT
        pipeline,
        dealstage,
        count() AS deal_count,
        sum(amount) AS total_value,
        sum(amount * hs_deal_stage_probability / 100) AS weighted_value
    GROUP BY pipeline, dealstage
);
ALTER TABLE silver.dim_deals MATERIALIZE PROJECTION agg_by_pipeline_stage;
```

Now `SELECT pipeline, dealstage, count(), sum(amount) FROM dim_deals GROUP BY pipeline, dealstage` automatically uses the projection — pre-aggregated, instant.

**Example — bidirectional bridge lookups:**

```sql
-- bridge_contact_deal is ordered by (contact_id, deal_id)
-- Add reverse lookup:
ALTER TABLE silver.bridge_contact_deal
ADD PROJECTION by_deal (
    SELECT * ORDER BY deal_id, contact_id
);
```

**Trade-off:** Projections double storage for the projected columns and slow down inserts slightly. At current scale this is negligible. At 1000x scale, choose projections for the 3-5 most common query patterns.

**What to keep as gold:** `agg_deal_health` and `fact_pipeline_snapshots` should stay as separate tables. Deal health computes cross-table metrics (activity staleness from bridge+activities JOIN). Pipeline snapshots are append-only historical records — they can't be projections.

---

## 7. Skip Indexes

**Current:** Zero secondary indexes.

**What they do:** Skip indexes let ClickHouse skip granules that definitely don't match a filter, even if the column isn't in the ORDER BY key. They add minimal storage overhead.

**Recommendations:**

```sql
-- dim_deals: bloom filter on owner_name (free-text lookup)
ALTER TABLE silver.dim_deals
ADD INDEX idx_owner bloom_filter(0.01) GRANULARITY 4;

-- dim_deals: set index on pipeline_label (low cardinality, not in ORDER BY)
ALTER TABLE silver.dim_deals
ADD INDEX idx_pipeline_label SET(100) GRANULARITY 4;

-- dim_contacts: bloom filter on email (exact match lookups)
ALTER TABLE silver.dim_contacts
ADD INDEX idx_email bloom_filter(0.01) GRANULARITY 4;

-- fact_activities: set index on hubspot_owner_id
ALTER TABLE silver.fact_activities
ADD INDEX idx_owner SET(100) GRANULARITY 4;
```

**Why bloom_filter for names/emails:** Bloom filters excel at "does this value exist in this granule?" checks. False positive rate of 1% means ClickHouse reads ~1% extra granules at worst.

**Why SET for pipeline/stage:** Set indexes store the distinct values per granule. If a granule has 3 pipeline values and you filter for one, ClickHouse can skip it if the value isn't in the set.

---

## 8. Compression

**Current:** Default LZ4 compression everywhere.

**Recommendation:** ZSTD(3) for cold/large columns, LZ4 (default) for hot/small columns.

```sql
-- Bronze: compress the huge _raw column
_raw String CODEC(ZSTD(3))

-- Silver: compress long string fields that are rarely filtered
closedlost_reason_description String CODEC(ZSTD(1))
page_url String CODEC(ZSTD(1))
body_preview String CODEC(ZSTD(1))

-- Numeric columns: Delta + ZSTD for time-series-like data
amount Nullable(Float64) CODEC(Delta, ZSTD(1))
closedate DateTime CODEC(Delta(4), ZSTD(1))
```

**Impact:** ZSTD(3) compresses ~2-3x better than LZ4 at a small CPU cost. For `_raw` columns that are rarely read, this is pure win. Delta encoding on sorted numeric/date columns exploits the ordering for another 2-5x compression.

---

## 9. Dictionary Layout

**Current:** All dictionaries use `COMPLEX_KEY_HASHED()` with `String` primary keys.

**Problem:** `COMPLEX_KEY_HASHED` is the slowest dictionary layout. Since all primary keys are single-column String IDs, use `HASHED()` instead — simpler hash function, fewer indirections.

**Better:**
```sql
-- BEFORE
LAYOUT(COMPLEX_KEY_HASHED())

-- AFTER (single string key = HASHED is faster)
LAYOUT(HASHED())
```

`COMPLEX_KEY_HASHED` is for composite keys (multiple columns). For single-column keys, `HASHED()` is ~30% faster lookups.

**At 1000x scale:** Consider `SPARSE_HASHED()` for large dictionaries (contacts at 200M rows). It uses ~40% less memory than `HASHED()` at the cost of slightly slower lookups.

---

## 10. Container & Server Configuration

**Current:** Bare `clickhouse/clickhouse-server:latest` with zero config.

**Recommendations:**

```yaml
# docker-compose.yml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:24.8  # Pin version, don't use :latest
    deploy:
      resources:
        limits:
          memory: 4G      # Prevent OOM killing host
        reservations:
          memory: 2G
    volumes:
      - ./clickhouse/config.xml:/etc/clickhouse-server/config.d/custom.xml
```

```xml
<!-- clickhouse/config.xml -->
<clickhouse>
    <profiles>
        <default>
            <!-- Limit per-query memory to prevent single query OOM -->
            <max_memory_usage>2000000000</max_memory_usage>  <!-- 2GB -->
            <!-- Spill to disk instead of failing -->
            <max_bytes_before_external_group_by>500000000</max_bytes_before_external_group_by>
            <max_bytes_before_external_sort>500000000</max_bytes_before_external_sort>
            <!-- Limit result size for safety -->
            <max_result_rows>100000</max_result_rows>
            <result_overflow_mode>throw</result_overflow_mode>
        </default>
    </profiles>
    <merge_tree>
        <!-- Optimize for small tables: smaller granules = better pruning -->
        <index_granularity>4096</index_granularity>
    </merge_tree>
</clickhouse>
```

**Pin the image version.** `:latest` means a `docker pull` can break your schema. Pin to a specific release (e.g., `24.8`).

---

## 11. Connection Management

**Current:** `get_client()` creates a new `clickhouse_connect` client on every `insert_records()` and `execute_sql()` call. Each call opens a new HTTP connection, does TLS/auth handshake (if applicable), and tears it down.

**Fix:**
```python
class ClickHouseResource(ConfigurableResource):
    _client = None
    
    def get_client(self):
        if self._client is None:
            self._client = clickhouse_connect.get_client(...)
        return self._client
```

`clickhouse_connect` clients are thread-safe and use connection pooling internally. Reusing the client avoids per-call connection overhead. At 100x insertion volume (thousands of batches), this matters.

---

## 12. Materialized Views for Real-Time Gold

**Current:** Gold tables are rebuilt hourly from scratch. Between refreshes, they're stale.

**Alternative for aggregates:** Materialized views that update incrementally on every silver INSERT.

```sql
CREATE MATERIALIZED VIEW gold.mv_deal_stage_funnel
ENGINE = SummingMergeTree()
ORDER BY (pipeline, dealstage)
AS SELECT
    pipeline,
    dealstage,
    count() AS deal_count,
    sum(amount) AS total_value
FROM silver.dim_deals
GROUP BY pipeline, dealstage;
```

Every INSERT into dim_deals automatically updates the materialized view. No refresh job needed. Queries are always up-to-date.

**Caveat:** This works well for SUM/COUNT aggregates. For complex metrics (win rates, days_since_last_activity), the current gold table approach is cleaner. Consider materialized views for the simple aggregates (funnel counts, cohort counts) and keep gold tables for complex computed metrics.

---

## Priority Ranking

| # | Change | Effort | Impact at current scale | Impact at 100x+ | Do when? |
|---|--------|--------|------------------------|-----------------|----------|
| 1 | Fix ORDER BY keys | Medium | Moderate | Critical | Now |
| 2 | LowCardinality on enum-like columns | Low | Low | High | Now |
| 3 | Atomic swap (EXCHANGE TABLES) | Low | High (eliminates downtime) | Critical | Now |
| 4 | Reuse ClickHouse client | Trivial | Low | Moderate | Now |
| 5 | Dictionary layout HASHED() | Trivial | Low | Moderate | Now |
| 6 | ZSTD on _raw column | Trivial | Moderate (storage) | High | Now |
| 7 | Add partitioning (monthly) | Medium | Low | Critical | Before 10x |
| 8 | Drop Nullable, use defaults | Medium | Low | Moderate | Before 10x |
| 9 | Skip indexes (bloom, set) | Low | Low | High | Before 100x |
| 10 | Projections on dim_deals | Medium | Moderate | High | Before 100x |
| 11 | Server config tuning | Low | Low (safety) | Critical (OOM prevention) | Before 100x |
| 12 | Drop _raw or use JSON type | High | Moderate (storage) | Critical (storage) | Before 1000x |
| 13 | Materialized views for gold | High | Low (hourly is fine) | High (real-time) | At 1000x |
| 14 | Pin Docker image version | Trivial | Safety | Safety | Now |
