# HubSpot Analytics

HubSpot to ClickHouse analytics platform. Extracts CRM data hourly via Dagster, transforms it through a bronze/silver/gold medallion architecture, and serves it through a chat interface where natural language questions are converted to ClickHouse SQL by an LLM.

---

## What It Does

1. **Extracts** contacts, companies, deals, leads, activities, pipelines, and associations from HubSpot's CRM API
2. **Loads** raw data into ClickHouse bronze tables (incremental, deduplicated)
3. **Transforms** into typed silver dimensions, facts, and bridge tables (config-driven)
4. **Aggregates** into gold tables for rep performance, deal health, source attribution, and pipeline snapshots
5. **Anonymizes** silver/gold into `silver_anon`/`gold_anon` databases for safe external sharing (MCP, demos)
6. **Serves** five interfaces:
   - **Chat** — Ask questions in natural language, get SQL + visualizations
   - **Dashboards** — Pin chat results to persistent dashboards with global filters (date, owner, pipeline)
   - **Data Spaces** — Scoped, configured views over the warehouse with per-space chat, dashboards, and filters
   - **Analytics API** — Associative graph engine (Qlik-like selection propagation)
   - **MCP server** — Exposes the anonymized warehouse to Claude Desktop / other MCP clients with the same schema prompt and SQL guardrails as in-app chat

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (for ClickHouse)
- A HubSpot private app token with CRM read scopes

### Setup

```bash
# Clone and enter
cd hs2ch

# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Environment
cp .env.example .env
# Edit .env: set HUBSPOT_TOKEN, optionally ANTHROPIC_API_KEY or OPENAI_API_KEY

# Frontend
cd frontend && npm install && cd ..

# Start everything
./start.sh
```

This starts:

| Service | URL | Purpose |
|---------|-----|---------|
| ClickHouse | http://localhost:8124 | Data warehouse |
| FastAPI | http://localhost:8192 | Backend API |
| Dagster | http://localhost:8194 | Pipeline orchestration |
| Frontend | http://localhost:8193 | Chat, dashboards, data explorer |

### First Run

1. Open Dagster at http://localhost:8194
2. Materialize all assets (or wait for the hourly schedule)
3. Open the frontend at http://localhost:8193
4. Configure an LLM provider in Settings (top-right)
5. Ask a question: *"What's our pipeline coverage for this quarter?"*

---

## Stack

| Component | Technology |
|-----------|-----------|
| Data warehouse | ClickHouse (columnar OLAP) |
| ETL orchestration | Dagster OSS |
| Backend API | FastAPI (Python) |
| Frontend | React 19 + TypeScript + Ant Design + Recharts + React Grid Layout |
| SQL filter engine | sqlglot (AST-based SQL rewriting for dashboard filters) |
| LLM providers | Claude (Anthropic API / OAuth / CLI), GPT-4o (OpenAI API) |

## Architecture

```
HubSpot CRM --> Dagster --> ClickHouse (bronze -> silver -> gold)
                                  |
                              FastAPI
                            /         \
                    Analytics API    Chat API
                    (graph engine)   (LLM -> SQL)
                           \         /
                          React Frontend
```

### Data Pipeline

Three-layer medallion architecture:

| Layer | Tables | Engine | Strategy |
|-------|--------|--------|----------|
| **Bronze** | 15 objects + 21 associations | `ReplacingMergeTree` | Incremental (HWM) |
| **Silver** | 10 dimensions + 3 facts + 9 bridges + 8 dicts | `ReplacingMergeTree` | Full rebuild via `EXCHANGE TABLES` (atomic swap) |
| **Gold** | 7 aggregates | `ReplacingMergeTree` | Full rebuild |
| **Anon** | Masked silver + gold mirrors in `silver_anon` / `gold_anon` | `ReplacingMergeTree` | Rebuilt after gold via sensor |

### Chat Interface

```
User question
    -> Schema prompt (tables + semantics + business context)
    -> LLM (Claude / GPT-4o)
    -> Structured response {sql, viz, title, explanation, context}
    -> SQL validation (whitelist tables, block mutations)
    -> ClickHouse execution
    -> Chart / table / number rendered inline
```

The LLM never sees actual data — only schema metadata and property descriptions from HubSpot. Queries use relative date expressions (`today()`, `toStartOfMonth()`) so saved results stay current. Period-over-period comparisons show colored delta badges.

### Dashboards

Chat results can be saved to an object library and pinned to persistent dashboards. Each dashboard supports global filters (date range, owner, pipeline) that apply to all cards simultaneously via rule-based SQL rewriting — no AI involved.

```
Dashboard filter state
    -> sqlglot AST parse (ClickHouse dialect)
    -> Identify table references from a static registry
    -> Inject WHERE conditions (silver uses IDs, gold uses names)
    -> Re-execute all card queries
```

### Associative Engine

Qlik-inspired selection propagation. Select a value in any table and all connected tables filter automatically through bridge table traversal.

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HUBSPOT_TOKEN` | Yes | HubSpot private app token |
| `HUBSPOT_HUB_ID` | Yes | HubSpot portal/hub ID — used to build canonical record URLs for the frontend and MCP responses |
| `CLICKHOUSE_HOST` | Yes | ClickHouse hostname (default: `localhost`) |
| `CLICKHOUSE_PORT` | Yes | ClickHouse HTTP port (default: `8124`) |
| `CLICKHOUSE_USER` | Yes | ClickHouse username (default: `hs2ch`) |
| `CLICKHOUSE_PASSWORD` | Yes | ClickHouse password (default: `hs2ch`) |
| `DAGSTER_HOME` | Recommended | Persistent Dagster storage directory |
| `ANTHROPIC_API_KEY` | Optional | Anthropic API key for Claude |
| `OPENAI_API_KEY` | Optional | OpenAI API key for GPT-4o |

### LLM Providers

Configure in the Settings drawer or `~/.hs2ch/config.json`:

| Provider | Setup | Notes |
|----------|-------|-------|
| Anthropic API | Set `ANTHROPIC_API_KEY` | Best quality. Prompt caching for fast responses. |
| OpenAI API | Set `OPENAI_API_KEY` | Good fallback. |
| Claude OAuth | Paste token in Settings | For Claude Pro/Max subscribers. Auto-refreshes. |
| Claude CLI | Install `claude` CLI | Zero-config for developers. |

### Adding Data

**New HubSpot property:**
```python
# silver_config.py — add one tuple
DIM_DEALS["columns"].append(("new_field", "hs_property_name", "String"))
```

**New computed metric:**
```python
# app/engine/metrics.py
COMPUTED_METRICS["new_metric"] = {
    "label": "New Metric", "format": "percent", "table": "dim_deals",
    "sql": "countIf(condition) / nullIf(count(), 0)",
}
```

---

## Development

```bash
source .venv/bin/activate

# Run tests
pytest -v

# Start individual services
uvicorn app.main:app --port 8192 --reload          # Backend
dagster dev -p 8194                                  # Dagster
cd frontend && npm run dev                           # Frontend
```

### Project Structure

```
hs2ch/
|-- app/                  # FastAPI backend (API + engine + LLM + spaces + MCP + SQL filter)
|   |-- mcp/              # MCP server (Claude Desktop integration, anon warehouse)
|   |-- spaces/           # Data Spaces feature (scoped warehouse views)
|   |-- store.py          # SQLite-backed persistence for objects/dashboards/conversations
|-- assets/               # Dagster assets (bronze + silver + gold + anon ELT)
|-- resources/            # Dagster resources (HubSpot + ClickHouse clients)
|-- frontend/             # React application (chat, dashboards, data spaces, data explorer)
|-- scripts/              # Initialization scripts
|-- tests/                # Unit tests (SQL filter, etc.)
|-- docs/                 # Detailed documentation
|   |-- architecture.md   # System architecture and design decisions
|   |-- data-pipeline.md  # ETL pipeline: bronze, silver, gold, anon layers
|   |-- backend.md        # Backend API: analytics engine + chat + LLM + spaces + MCP
|   |-- frontend.md       # Frontend: components, hooks, visualization
|-- silver_config.py      # Silver layer column definitions (single source of truth)
|-- definitions.py        # Dagster wiring (assets + jobs + schedules + sensors)
|-- sensors.py            # bronze → silver → gold → anon trigger chain
|-- docker-compose.yml    # ClickHouse container
|-- start.sh              # Start all services
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | System overview, data flow, design decisions, relationship graph |
| [Data Pipeline](docs/data-pipeline.md) | Bronze/silver/gold/anon layers, Dagster jobs, sensor chain |
| [Backend](docs/backend.md) | Analytics engine, chat API, LLM providers, spaces, MCP, SQL validation |
| [Frontend](docs/frontend.md) | Chat UI, visualization components, hooks, types |
| [ClickHouse Evaluation](docs/clickhouse-evaluation.md) | ClickHouse design notes — what shipped, what's still open |
| [Security Audit](SECURITY_AUDIT.md) | Findings + priority fixes (last run 2026-04-06; stale — see backend.md additions) |
| [CLAUDE.md](CLAUDE.md) | Development commands and codebase conventions |

---

## Stats

| | Count |
|---|---|
| Bronze tables | 36 (15 objects + 21 associations) |
| Silver assets | 23 (10 dims + 3 facts + 9 bridges + DQ) |
| Gold tables | 7 |
| Anon mirrors | silver_anon + gold_anon (masked copies for external sharing) |
| Dictionaries | 8 (in-memory lookups from silver dims) |
| Silver columns | ~197 (across all dimensions) |
| Graph relationships | 9 bridge edges |
| API endpoints | ~64 (analytics + chat + data + objects + dashboards + conversations + spaces) |
| Computed metrics | 22 |
| LLM providers | 4 |
| Viz types | 6 (number, table, bar, line, funnel, comparison) |
| Frontend pages | 9 (chat, dashboard, library, data explorer, architecture, spaces list/new/edit/overview/dashboard) |
