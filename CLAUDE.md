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

Visual QA / screenshots: this is a shared host — **always launch headless Chrome through `qa-render`** (`qa-render node my-qa.cjs`). It forces scratch onto `/dev/shm` (never the often-full `/`) and caps concurrent renders. See `docs/qa-render-runbook.md`; (re)install with `./scripts/qa-render/install.sh`.

Docker-free local setup (Linux): `./bootstrap.sh` (Python + frontend deps + a pinned single-binary ClickHouse under `.clickhouse/`), then `./start.sh`. When `CLICKSPOT_CLICKHOUSE_MODE` is unset, `start.sh` auto-picks `local` on Linux (managed via `scripts/clickhouse-local.sh`) and `docker` on macOS/Windows, where the binary can't be auto-downloaded.

Native Windows: `.\start.ps1` — PowerShell sibling of `start.sh` (same services/ports, Windows venv layout `.venv\Scripts`, process-tree cleanup via `taskkill /T`). Supports `docker` (default) and `external` modes only; `local` is Linux-only, use WSL + `./start.sh` for that.

ClickHouse init (run once): `python scripts/init_clickhouse.py` (both `bootstrap.sh --seed` and `start.sh` run this for you).

ClickHouse, three modes via `CLICKSPOT_CLICKHOUSE_MODE` (set in `.env`; unset = auto `local` on Linux / `docker` elsewhere): `local` (Docker-free single binary on port 8124), `docker` (`docker compose up -d clickhouse`, image pinned to `clickhouse/clickhouse-server:26.2.5.45`), or `external` (you manage it). Server config + user profile come from `clickhouse/config.xml` (`index_granularity=4096`) and `clickhouse/users.xml` (per-query memory cap 2 GB, spill thresholds 500 MB, `max_result_rows=100k`, `max_partitions_per_insert_block=500`) — mounted into the container in `docker` mode, applied to the local runtime otherwise.

## Env Vars

Copy `.env.example` → `.env`; every value ships with a working default. **`HUBSPOT_TOKEN` and `HUBSPOT_HUB_ID` are optional** — needed only for live HubSpot extraction (and the canonical HubSpot record URLs in result tables and MCP responses). Omit them and load the bundled synthetic warehouse with the offline seed loader: `make seed` (or `python scripts/seed.py`), which populates bronze→silver→gold→anon from `demo-data/clickspot-demo-data.csv` with no portal and no token. The ClickHouse connection vars (`CLICKHOUSE_HOST`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`) come pre-filled in `.env.example`; `CLICKHOUSE_PORT` defaults to 8124 (`app/db.py` falls back to 8123 if unset). `HUBSPOT_REGION` (region code like `eu1`, `na2`) auto-detects from `HUBSPOT_TOKEN` on the first bronze API call and caches in `~/.clickspot/customer.json::hubspot_region`; only set it explicitly when running MCP without the token.

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
- **Assets** (`assets/`): 16 object tables + 25 association tables = 41 bronze tables
  - `crm.py`: contacts, companies, deals, leads (via `_make_crm_asset` factory) + `hs_owners`
  - `activities.py`: calls, meetings, engagement_emails, notes, tasks (reuses `_make_crm_asset`)
  - `marketing.py`: campaigns, forms, pipelines, lead_pipelines (via `_make_marketing_asset` factory) + `hs_form_submissions` (legacy `/form-integrations/v1` endpoint, bespoke asset) + `hs_lists` (v3 lists catalog via `POST /crm/v3/lists/search`) + per-objectType list membership assoc assets
  - `associations.py`: 21 N:M:N association bridges (6 CRM-to-CRM + 15 activity-to-CRM). Lists add 4 more (`hs_assoc_list_{contact,company,deal,lead}`), built in `marketing.py` from `/crm/v3/lists/{id}/memberships`.
- **Schema**: `ReplacingMergeTree(_extracted_at) ORDER BY (_record_id)` — `properties Map(String, String)` + raw JSON in `_raw`
- **Extraction**: Dynamic property discovery per object (calls `/crm/objects/{API_VERSION}/{type}/properties` first, then lists with explicit `properties=` query param). Cursor pagination via `paging.next.after`. Note: incremental HWM filtering via `/search` is NOT currently wired up — bronze does full list-endpoint loads, deduped by `ReplacingMergeTree` on `_record_id`

### Silver Layer

- **Config** (`silver_config.py`): Single source of truth for field selection — adding/removing a property is a 1-line change. ~197 columns across all dimensions.
- **Assets** (`assets/silver.py`): Config-driven factories generate DDL + transform SQL
  - 11 dimension tables: `dim_contacts`, `dim_companies`, `dim_deals`, `dim_leads`, `dim_owners`, `dim_pipelines`, `dim_pipeline_stages`, `dim_lead_pipelines`, `dim_lead_pipeline_stages`, `dim_lists`
  - 3 fact tables: `fact_activities` (UNION ALL across 5 activity types), `fact_stage_history` (stage enter/exit tracking), `fact_form_submissions`
  - 13 bridge tables: `bridge_contact_company`, `bridge_contact_deal`, `bridge_deal_company`, `bridge_lead_contact`, `bridge_deal_lead`, `bridge_lead_company`, `bridge_list_contact`, `bridge_list_company`, `bridge_list_deal`, `bridge_list_lead`, `bridge_activity_contact`, `bridge_activity_company`, `bridge_activity_deal`
  - 9 dictionaries: in-memory lookups from silver dims (`DICT_CONFIGS` in `silver_config.py` → auto DDL via `_build_dict_ddl()`). Single-key dicts use `HASHED()`; composite (`dim_lead_pipeline_stages`) uses `COMPLEX_KEY_HASHED()`
  - `dq_metrics`: append-only quality metrics (row counts, null rates, orphan counts, archived rates) with 90-day TTL
- **Refresh**: Atomic swap via `EXCHANGE TABLES` — build into a staging table, swap in place, drop the old one. No downtime window
- **Three source modes**: `properties` (Map column), `json` (JSONExtract from _raw), `nested_stages` (ARRAY JOIN)
- **Partitioning**: optional `partition_by` field on dim/fact configs (consumed by `_build_ddl`). Silver dims partition by `toYYYYMM(toDate(createdate))`; `fact_form_submissions` by month of `submitted_at`; `fact_activities` + `fact_stage_history` by year (multi-year spans would otherwise exceed `max_partitions_per_insert_block`). Small lookup dims (`dim_owners`, `dim_pipelines`, `*_stages`) are intentionally unpartitioned. Verified with `EXPLAIN indexes=1` that partition pruning fires on date-ranged queries against partitioned columns.
- **Skip indexes**: optional `indexes` field on dim configs. Bloom filters on `dim_deals.hubspot_owner_id`, `dim_contacts.email`, `dim_leads.hubspot_owner_id` for exact-match lookups not in any ORDER BY.

### Gold Layer

- 7 aggregate tables: `agg_rep_performance`, `agg_deal_health`, `agg_deal_stage_funnel`, `agg_source_attribution`, `agg_lead_health`, `agg_deal_cohorts`, `fact_pipeline_snapshots`
- Uses `dictGet()` for ID-to-label resolution (no JOINs)
- Rebuilt from silver on each pipeline run
- Partitioned where there's a natural date axis: `agg_rep_performance` (`period_start`), `agg_deal_cohorts` (`cohort_month`), `fact_pipeline_snapshots` (`snapshot_date`). The lookup-style aggregates (`agg_deal_health`, `agg_lead_health`, `agg_source_attribution`, `agg_deal_stage_funnel`) stay unpartitioned — they're keyed on entity IDs/sources.

### Anon Layer

- **Assets** (`assets/silver_anon.py`, `assets/gold_anon.py`): mirror of silver + gold into the `silver_anon` and `gold_anon` databases with PII masked via `app/engine/anon_masking.py` (email/name/domain replaced; IDs preserved for joins).
- **Job**: `anon_job` runs after `gold_job` via the `trigger_anon_after_gold` sensor.
- **Used by**: the MCP server (`app/mcp/`) so external Claude clients only ever see anonymized data; can also be exposed for demos.

### Chat Interface

- **LLM providers** (`app/llm/`): Anthropic API, OpenAI API, Claude OAuth, Claude CLI (auto-detection). Claude CLI is source/native-only — the Docker images don't bundle the `claude` binary, so containers use an API key or Claude OAuth.
- **Schema prompt** (`app/llm/schema_prompt.py`): Generated from `app/config.py` + `silver_config.py` DICT_CONFIGS + semantic layer. Enforces relative date expressions (`today()`, `toStartOfMonth()`) so saved queries stay current.
- **SQL validator** (`app/llm/sql_validator.py`): Whitelist tables, block mutations, inject LIMIT
- **Semantic layer** (`app/semantic/layer.py`): HubSpot property labels/descriptions cached to `~/.clickspot/schema_cache.json`
- **Frontend**: React chat UI with inline visualizations (number, table, bar, line, funnel, comparison)
- **Period-over-period**: Context KPIs support `previous_sql` for delta computation. `comparison` viz type shows KPIs with colored trend badges.
- **HubSpot linking**: Result tables auto-link entity names/IDs to HubSpot records. ID columns are auto-hidden when a paired name column exists.

### Dashboards

- **Object library** (`frontend/src/hooks/useObjectRepo.ts` + server-side `app/api/object_routes.py` backed by `app/store.py` SQLite): Chat results saved as objects (SQL + viz + KPIs). Persistence is now server-side; the hook syncs to/from the API.
- **Dashboard grid** (`frontend/src/pages/DashboardPage.tsx` + server-side `app/api/dashboard_routes.py`): Draggable/resizable cards via `react-grid-layout`. Dashboards, items, and layouts persist via the API.
- **Conversations** (`app/api/conversation_routes.py`): chat history also persists server-side.
- **Global filters** (`app/engine/sql_filter.py`): Rule-based SQL rewriting using sqlglot AST manipulation. Date, owner, pipeline filters injected into all card queries. Silver tables use IDs, gold tables use names. No AI involved.
- **Filter registry** (`FILTER_COLUMNS` in `sql_filter.py`): Static mapping from `database.table` to filterable column names per dimension

### Customer config (per-portal)

- **Module** (`app/customer/config.py`): single source of truth for portal-specific runtime values (company name, currency, main pipeline, stage names, canonical revenue field). Lives in `~/.clickspot/customer.json` (0600). Defaults shipped in `DEFAULTS` make a fresh clone usable.
- **Consumed by** `app/llm/schema_prompt.py::_block_business_context` + `_block_examples` — no portal-specific strings exist in the repo; the prompt templates against `customer.config.load()`.
- **Auto-discovered on FastAPI startup**: `app/main.py` lifespan calls `customer_config.auto_discover(ch)` after silver loads and merges into `customer.json` *only for keys still at their default* — operator choices via `python -m app.customer.onboarding` are never overwritten.
- **Per-portal silver extensions**: `silver_config_custom.py` (gitignored) appends extra deal/contact column tuples to the core lists. Worked example at `silver_config_custom.py.example`. A fresh clone has none.

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
