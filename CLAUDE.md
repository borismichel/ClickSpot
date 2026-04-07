# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

HubSpot → ClickHouse ELT pipeline with bronze/silver/gold medallion architecture, running hourly via Dagster OSS. Includes a chat interface where natural language questions are converted to ClickHouse SQL by an LLM.

## Development

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests: `pytest -v`

Start Dagster UI: `dagster dev -p 8194` → http://localhost:8194

Start backend: `uvicorn app.main:app --port 8192 --reload` → http://localhost:8192

Start frontend: `cd frontend && npm run dev` → http://localhost:8193

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
| **Gold** | Business entities, computed cols, KPIs | Business requirements change |

Silver is intentionally dumb — 1:1 mapping from bronze properties to typed columns. No computed columns, no business logic. Those belong in gold.

### Bronze Layer

- **Resources** (`resources/`): `HubSpotResource` (API pagination + 429 retry), `ClickHouseResource` (bulk insert + `execute_sql`)
- **Assets** (`assets/`): 17 object tables + 21 association tables = 38 bronze tables
  - `crm.py`: contacts, companies, deals, leads (via `_make_crm_asset` factory)
  - `activities.py`: calls, meetings, engagement_emails, notes, tasks (reuses `_make_crm_asset`)
  - `marketing.py`: campaigns, forms, pipelines, lead_pipelines (via `_make_marketing_asset` factory)
  - `associations.py`: 21 N:M:N association bridges (6 CRM-to-CRM + 15 activity-to-CRM)
- **Schema**: `ReplacingMergeTree(_extracted_at) ORDER BY (_record_id)` — `properties Map(String, String)` + raw JSON in `_raw`
- **Extraction**: Incremental via `lastmodifieddate` high-water mark, 5-minute overlap buffer

### Silver Layer

- **Config** (`silver_config.py`): Single source of truth for field selection — adding/removing a property is a 1-line change. ~197 columns across all dimensions.
- **Assets** (`assets/silver.py`): Config-driven factories generate DDL + transform SQL
  - 10 dimension tables: `dim_contacts`, `dim_companies`, `dim_deals`, `dim_leads`, `dim_owners`, `dim_pipelines`, `dim_pipeline_stages`, `dim_lead_pipelines`, `dim_lead_pipeline_stages`
  - 2 fact tables: `fact_activities` (UNION ALL across 5 activity types), `fact_stage_history` (stage enter/exit tracking)
  - 9 bridge tables: `bridge_contact_company`, `bridge_contact_deal`, `bridge_deal_company`, `bridge_lead_contact`, `bridge_deal_lead`, `bridge_lead_company`, `bridge_activity_contact`, `bridge_activity_company`, `bridge_activity_deal`
  - 8 dictionaries: in-memory lookups from silver dims (`DICT_CONFIGS` in `silver_config.py` → auto DDL via `_build_dict_ddl()`)
  - `dq_metrics`: append-only quality metrics (row counts, null rates, orphan counts, archived rates) with 90-day TTL
- **Refresh**: Full DROP + CREATE + INSERT each run via `EXCHANGE TABLES` (atomic swap)
- **Three source modes**: `properties` (Map column), `json` (JSONExtract from _raw), `nested_stages` (ARRAY JOIN)

### Gold Layer

- 7 aggregate tables: `agg_rep_performance`, `agg_deal_health`, `agg_deal_stage_funnel`, `agg_source_attribution`, `agg_lead_health`, `agg_deal_cohorts`, `fact_pipeline_snapshots`
- Uses `dictGet()` for ID-to-label resolution (no JOINs)
- Rebuilt from silver on each pipeline run

### Chat Interface

- **LLM providers** (`app/llm/`): Anthropic API, OpenAI API, Claude OAuth, Claude CLI (auto-detection)
- **Schema prompt** (`app/llm/schema_prompt.py`): Generated from `app/config.py` + `silver_config.py` DICT_CONFIGS + semantic layer
- **SQL validator** (`app/llm/sql_validator.py`): Whitelist tables, block mutations, inject LIMIT
- **Semantic layer** (`app/semantic/layer.py`): HubSpot property labels/descriptions cached to `~/.hs2ch/schema_cache.json`
- **Frontend**: React chat UI with inline visualizations (number, table, bar, line, funnel)

### Wiring

- `definitions.py` → `jobs.py` → `schedules.py` (hourly cron)
- Resources: `hubspot`, `ch` (bronze database), `ch_silver` (silver database), `ch_gold` (gold database)
- Jobs: `bronze_job`, `silver_job`, `gold_job`, `full_pipeline_job` (all assets, dependency-ordered)

## Key Patterns

- Adding a new CRM object: one line in `assets/crm.py` using `_make_crm_asset("object_type", "hs_table_name")`
- Adding a new marketing object: one line in `assets/marketing.py` using `_make_marketing_asset`
- Adding a silver property: add one tuple `(silver_name, bronze_key, type)` to the config dict in `silver_config.py`
- Adding a new silver dimension: add config block in `silver_config.py` + call `_make_dim_asset` in `assets/silver.py`
- Adding a new dictionary: add entry to `DICT_CONFIGS` in `silver_config.py` (DDL + prompt auto-generated)
- Resources are shared via Dagster injection: `"hubspot"`, `"ch"` (bronze), `"ch_silver"` (silver), `"ch_gold"` (gold)

## Blocked / TODO

- `hs_ads`, `hs_marketing_emails`: bronze assets deactivated (API endpoint issues)
