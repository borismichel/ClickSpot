# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

HubSpot → ClickHouse bronze layer pipeline. Extracts 13 HubSpot object types (CRM + Marketing) into raw JSON tables in ClickHouse, running hourly via Dagster OSS.

## Development

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests: `pytest -v`

Start Dagster UI: `dagster dev -p 3333` → http://localhost:3333

ClickHouse init (run once): `python scripts/init_clickhouse.py`

## Env Vars

Copy `.env.example` → `.env`. Required: `HUBSPOT_TOKEN`, `CLICKHOUSE_HOST`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`.

## Architecture

- **Resources** (`resources/`): `HubSpotResource` (API pagination), `ClickHouseResource` (bulk insert)
- **Assets** (`assets/`): 13 Dagster assets — each fetches one HubSpot object type and writes raw JSON to a bronze table
  - `crm.py`: contacts, companies, deals, leads (via `_make_crm_asset` factory)
  - `activities.py`: calls, meetings, engagement_emails, notes, tasks (reuses `_make_crm_asset`)
  - `marketing.py`: campaigns, forms, ads, marketing_emails (via `_make_marketing_asset` factory)
- **Wiring**: `definitions.py` → `jobs.py` → `schedules.py` (hourly cron)
- **Extraction**: Incremental via `lastmodifieddate` high-water mark stored in Dagster asset metadata, with 5-minute overlap buffer
- **Bronze schema**: `ReplacingMergeTree(_extracted_at) ORDER BY (_record_id)` — raw JSON in `_raw` column

## Key Patterns

- Adding a new CRM object: one line in `assets/crm.py` using `_make_crm_asset("object_type", "hs_table_name")`
- Adding a new marketing object: one line in `assets/marketing.py` using `_make_marketing_asset`
- Both resources are shared via Dagster's resource injection (`"hubspot"` and `"ch"` keys)
- ClickHouse user `clickhouse` is shared with Langfuse (no separate `hs2ch` user — access_management is disabled)
