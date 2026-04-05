# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

HubSpot → ClickHouse ELT pipeline with bronze/silver/gold medallion architecture, running hourly via Dagster OSS.

## Development

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests: `pytest -v`

Start Dagster UI: `dagster dev -p 3333` → http://localhost:3333

ClickHouse init (run once): `python scripts/init_clickhouse.py`

ClickHouse local dev: `docker compose up -d` (port 8124)

## Env Vars

Copy `.env.example` → `.env`. Required: `HUBSPOT_TOKEN`, `CLICKHOUSE_HOST`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`. Optional: `CLICKHOUSE_PORT` (default 8123).

## Architecture

### Three-Layer Philosophy

| Layer | Purpose | Changes when... |
|---|---|---|
| **Bronze** | Raw extraction, safety net | New HubSpot object type or API change |
| **Silver** | Clean typed properties, no business logic | User adds/removes a property in `silver_config.py` |
| **Gold** (future) | Business entities, computed cols, KPIs | Business requirements change |

Silver is intentionally dumb — 1:1 mapping from bronze properties to typed columns. No computed columns, no business logic. Those belong in gold.

### Bronze Layer

- **Resources** (`resources/`): `HubSpotResource` (API pagination + 429 retry), `ClickHouseResource` (bulk insert + `execute_sql`)
- **Assets** (`assets/`): 18 bronze assets + 8 association assets
  - `crm.py`: contacts, companies, deals, leads (via `_make_crm_asset` factory)
  - `activities.py`: calls, meetings, engagement_emails, notes, tasks (reuses `_make_crm_asset`)
  - `marketing.py`: campaigns, forms, pipelines (via `_make_marketing_asset` factory)
  - `associations.py`: 8 N:M:N association bridges (via `_make_association_asset` factory)
- **Schema**: `ReplacingMergeTree(_extracted_at) ORDER BY (_record_id)` — `properties Map(String, String)` + raw JSON in `_raw`
- **Extraction**: Incremental via `lastmodifieddate` high-water mark, 5-minute overlap buffer

### Silver Layer

- **Config** (`silver_config.py`): Single source of truth for field selection — adding/removing a property is a 1-line change
- **Assets** (`assets/silver.py`): Config-driven factories generate DDL + transform SQL
  - 6 dimension tables: `dim_contacts`, `dim_companies`, `dim_deals`, `dim_leads`, `dim_pipelines`, `dim_pipeline_stages`
  - 1 fact table: `fact_activities` (UNION ALL across 5 activity types with type discriminator)
  - 4 bridge tables: `bridge_contact_company`, `bridge_contact_deal`, `bridge_deal_company`, `bridge_activity_contact`
  - `dq_metrics`: append-only quality metrics (row counts, null rates, orphan counts, archived rates) with 90-day TTL
- **Refresh**: Full DROP + CREATE + INSERT each run (no migrations)
- **Three source modes**: `properties` (Map column), `json` (JSONExtract from _raw), `nested_stages` (ARRAY JOIN)

### Wiring

- `definitions.py` → `jobs.py` → `schedules.py` (hourly cron)
- Resources: `hubspot`, `ch` (bronze database), `ch_silver` (silver database)
- Jobs: `bronze_job` (group "bronze"), `silver_job` (group "silver"), `full_pipeline_job` (all assets, dependency-ordered)

## Key Patterns

- Adding a new CRM object: one line in `assets/crm.py` using `_make_crm_asset("object_type", "hs_table_name")`
- Adding a new marketing object: one line in `assets/marketing.py` using `_make_marketing_asset`
- Adding a silver property: add one tuple `(silver_name, bronze_key, type)` to the config dict in `silver_config.py`
- Adding a new silver dimension: add config block in `silver_config.py` + call `_make_dim_asset` in `assets/silver.py`
- Resources are shared via Dagster injection: `"hubspot"`, `"ch"` (bronze), `"ch_silver"` (silver)

## Blocked / TODO

- `hs_ads`, `hs_marketing_emails`: bronze assets deactivated (API endpoint issues)
