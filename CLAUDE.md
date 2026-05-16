# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

HubSpot → ClickHouse ELT pipeline with bronze/silver/gold/anon medallion architecture, running hourly via Dagster OSS (bronze on a cron schedule; silver → gold → anon chained by sensors). Includes a chat interface where natural language questions are converted to ClickHouse SQL by an LLM, persistent server-backed dashboards with global filters, a data explorer, scoped Data Spaces (per-space chat/dashboards/filters over a configured slice of the warehouse), and an MCP server that exposes the anonymized warehouse to Claude Desktop / other MCP clients with the same schema prompt and SQL guardrails as in-app chat.

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

Copy `.env.example` → `.env`. Required: `HUBSPOT_TOKEN`, `HUBSPOT_HUB_ID` (used to build canonical HubSpot record URLs in result tables and MCP responses), `CLICKHOUSE_HOST`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`. Optional: `CLICKHOUSE_PORT` (project default 8124; `app/db.py` falls back to 8123 if unset).

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
- **Assets** (`assets/`): 15 object tables + 21 association tables = 36 bronze tables
  - `crm.py`: contacts, companies, deals, leads (via `_make_crm_asset` factory) + `hs_owners`
  - `activities.py`: calls, meetings, engagement_emails, notes, tasks (reuses `_make_crm_asset`)
  - `marketing.py`: campaigns, forms, pipelines, lead_pipelines (via `_make_marketing_asset` factory) + `hs_form_submissions` (legacy `/form-integrations/v1` endpoint, bespoke asset)
  - `associations.py`: 21 N:M:N association bridges (6 CRM-to-CRM + 15 activity-to-CRM)
- **Schema**: `ReplacingMergeTree(_extracted_at) ORDER BY (_record_id)` — `properties Map(String, String)` + raw JSON in `_raw`
- **Extraction**: Dynamic property discovery per object (calls `/crm/objects/{API_VERSION}/{type}/properties` first, then lists with explicit `properties=` query param). Cursor pagination via `paging.next.after`. Note: incremental HWM filtering via `/search` is NOT currently wired up — bronze does full list-endpoint loads, deduped by `ReplacingMergeTree` on `_record_id`

### Silver Layer

- **Config** (`silver_config.py`): Single source of truth for field selection — adding/removing a property is a 1-line change. ~197 columns across all dimensions.
- **Assets** (`assets/silver.py`): Config-driven factories generate DDL + transform SQL
  - 10 dimension tables: `dim_contacts`, `dim_companies`, `dim_deals`, `dim_leads`, `dim_owners`, `dim_pipelines`, `dim_pipeline_stages`, `dim_lead_pipelines`, `dim_lead_pipeline_stages`
  - 3 fact tables: `fact_activities` (UNION ALL across 5 activity types), `fact_stage_history` (stage enter/exit tracking), `fact_form_submissions`
  - 9 bridge tables: `bridge_contact_company`, `bridge_contact_deal`, `bridge_deal_company`, `bridge_lead_contact`, `bridge_deal_lead`, `bridge_lead_company`, `bridge_activity_contact`, `bridge_activity_company`, `bridge_activity_deal`
  - 8 dictionaries: in-memory lookups from silver dims (`DICT_CONFIGS` in `silver_config.py` → auto DDL via `_build_dict_ddl()`). Single-key dicts use `HASHED()`; composite (`dim_lead_pipeline_stages`) uses `COMPLEX_KEY_HASHED()`
  - `dq_metrics`: append-only quality metrics (row counts, null rates, orphan counts, archived rates) with 90-day TTL
- **Refresh**: Atomic swap via `EXCHANGE TABLES` — build into a staging table, swap in place, drop the old one. No downtime window
- **Three source modes**: `properties` (Map column), `json` (JSONExtract from _raw), `nested_stages` (ARRAY JOIN)

### Gold Layer

- 7 aggregate tables: `agg_rep_performance`, `agg_deal_health`, `agg_deal_stage_funnel`, `agg_source_attribution`, `agg_lead_health`, `agg_deal_cohorts`, `fact_pipeline_snapshots`
- Uses `dictGet()` for ID-to-label resolution (no JOINs)
- Rebuilt from silver on each pipeline run

### Anon Layer

- **Assets** (`assets/silver_anon.py`, `assets/gold_anon.py`): mirror of silver + gold into the `silver_anon` and `gold_anon` databases with PII masked via `app/engine/anon_masking.py` (email/name/domain replaced; IDs preserved for joins).
- **Job**: `anon_job` runs after `gold_job` via the `trigger_anon_after_gold` sensor.
- **Used by**: the MCP server (`app/mcp/`) so external Claude clients only ever see anonymized data; can also be exposed for demos.

### Chat Interface

- **LLM providers** (`app/llm/`): Anthropic API, OpenAI API, Claude OAuth, Claude CLI (auto-detection)
- **Schema prompt** (`app/llm/schema_prompt.py`): Generated from `app/config.py` + `silver_config.py` DICT_CONFIGS + semantic layer. Enforces relative date expressions (`today()`, `toStartOfMonth()`) so saved queries stay current.
- **SQL validator** (`app/llm/sql_validator.py`): Whitelist tables, block mutations, inject LIMIT
- **Semantic layer** (`app/semantic/layer.py`): HubSpot property labels/descriptions cached to `~/.hs2ch/schema_cache.json`
- **Frontend**: React chat UI with inline visualizations (number, table, bar, line, funnel, comparison)
- **Period-over-period**: Context KPIs support `previous_sql` for delta computation. `comparison` viz type shows KPIs with colored trend badges.
- **HubSpot linking**: Result tables auto-link entity names/IDs to HubSpot records. ID columns are auto-hidden when a paired name column exists.

### Dashboards

- **Object library** (`frontend/src/hooks/useObjectRepo.ts` + server-side `app/api/object_routes.py` backed by `app/store.py` SQLite): Chat results saved as objects (SQL + viz + KPIs). Persistence is now server-side; the hook syncs to/from the API.
- **Dashboard grid** (`frontend/src/pages/DashboardPage.tsx` + server-side `app/api/dashboard_routes.py`): Draggable/resizable cards via `react-grid-layout`. Dashboards, items, and layouts persist via the API.
- **Conversations** (`app/api/conversation_routes.py`): chat history also persists server-side.
- **Global filters** (`app/engine/sql_filter.py`): Rule-based SQL rewriting using sqlglot AST manipulation. Date, owner, pipeline filters injected into all card queries. Silver tables use IDs, gold tables use names. No AI involved.
- **Filter registry** (`FILTER_COLUMNS` in `sql_filter.py`): Static mapping from `database.table` to filterable column names per dimension

### Data Spaces

- **Module** (`app/spaces/`): `config.py` (DataSpaceConfig schema), `discovery.py` (entity/dimension introspection), `registry.py` (CRUD + preview), `space_filter.py` (per-space SQL rewriting), `space_prompt.py` (scoped schema prompt), `generator.py`, `routes.py` (`/api/v1/spaces/*` — 26 endpoints).
- **Frontend** (`frontend/src/pages/DataSpace*.tsx`, `Space*.tsx`; `frontend/src/components/spaces/`; hooks `useDataSpaces`, `useSpaceChat`, `useSpaceDashboards`): a Data Space is a user-defined slice of the warehouse (grain entity + dimensions + filters) with its own chat conversation and its own dashboards. Spaces are loaded at FastAPI startup via `load_saved_spaces()`.

### MCP Server

- **Module** (`app/mcp/`): `server.py` (FastMCP entrypoint — `python -m app.mcp.server`), `guardrails.py` (table allowlist + activity-strip regex), `pii.py`.
- Reuses `app/llm/schema_prompt.build_schema_prompt` and `app/llm/sql_validator.ensure_limit` so external clients see the same dict hints, ILIKE guidance, and table whitelist as in-app chat.
- Exposes the `silver_anon` / `gold_anon` databases (NEVER raw silver/gold). No LLM lives in the server; the MCP client drives SQL generation.

### Wiring

- `definitions.py` composes: all bronze + silver + gold + silver_anon + gold_anon assets; jobs `bronze_job`, `silver_job`, `gold_job`, `anon_job`; the `hourly_schedule` (runs `bronze_job`, default status STOPPED); sensors `trigger_silver_after_bronze` → `trigger_gold_after_silver` → `trigger_anon_after_gold`.
- Resources: `hubspot`, `ch` (bronze), `ch_silver`, `ch_gold`, `ch_silver_anon`, `ch_gold_anon`.

## Key Patterns

- Adding a new CRM object: one line in `assets/crm.py` using `_make_crm_asset("object_type", "hs_table_name")`
- Adding a new marketing object: one line in `assets/marketing.py` using `_make_marketing_asset`
- Adding a silver property: add one tuple `(silver_name, bronze_key, type)` to the config dict in `silver_config.py`
- Adding a new silver dimension: add config block in `silver_config.py` + call `_make_dim_asset` in `assets/silver.py`
- Adding a new dictionary: add entry to `DICT_CONFIGS` in `silver_config.py` (DDL + prompt auto-generated)
- Resources are shared via Dagster injection: `"hubspot"`, `"ch"` (bronze), `"ch_silver"` (silver), `"ch_gold"` (gold)

## Blocked / TODO

- `hs_ads`, `hs_marketing_emails`: bronze assets deactivated (API endpoint issues)
