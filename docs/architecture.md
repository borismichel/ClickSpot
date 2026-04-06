# Architecture

This document describes the overall system architecture, how components connect, and the design decisions behind them.

---

## System Overview

```
+----------------+          +----------------+          +-------------------+
|   HubSpot CRM  |  API     |    Dagster     |  SQL     |    ClickHouse     |
|   (source)     | -------> |  (orchestrator)| -------> |   (warehouse)     |
+----------------+          +----------------+          +-------------------+
                                                          |  bronze.*  (raw) |
                                                          |  silver.*  (dim) |
                                                          |  gold.*    (agg) |
                                                          +--------+--------+
                                                                   |
                            +-------------------+                  |
                            |    FastAPI         | <---------------+
                            |   (backend API)   |    SQL queries
                            +--------+----------+
                                     |
                    +----------------+----------------+
                    |                                 |
            +-------+-------+              +---------+---------+
            | Analytics API |              |    Chat API       |
            | (associative  |              |  (LLM -> SQL)     |
            |  graph engine)|              +---+-------+-------+
            +---------------+                  |       |
                                               v       v
                                         +-----+--+ +-+--------+
                                         |  LLM   | | Semantic  |
                                         |Provider | |  Layer    |
                                         +--------+ +----------+
                                                         |
                            +-------------------+        |
                            |  React Frontend   | <------+
                            |  (chat + viz)     |    via /api
                            +-------------------+
```

---

## Data Flow

### 1. Ingestion (Hourly)

```
HubSpot CRM API
    |
    |  HubSpotResource: paginated fetch, 429 retry, HWM tracking
    v
bronze.hs_contacts, bronze.hs_deals, bronze.hs_companies, ...
    |
    |  Config-driven transform: silver_config.py -> DDL + INSERT
    v
silver.dim_contacts, silver.dim_deals, silver.bridge_contact_deal, ...
    |
    |  Multi-table JOINs + aggregations
    v
gold.agg_rep_performance, gold.agg_deal_health, ...
```

Each layer is a separate ClickHouse database (`bronze`, `silver`, `gold`). Tables use `ReplacingMergeTree` for deduplication.

### 2. Chat Query (Interactive)

```
User: "What's our win rate by rep?"
    |
    v
Frontend: POST /api/v1/chat {message, history}
    |
    v
Backend: Build schema prompt (tables + semantics + examples)
    |
    v
LLM: Generate {sql, viz, title, explanation, context}
    |
    v
Validator: Whitelist tables, reject mutations, inject LIMIT
    |
    v
ClickHouse: Execute SQL + context KPI queries
    |
    v
Frontend: Render explanation + SQL preview + chart/table + context bar
```

**Latency budget:**

| Step | Typical Time |
|------|-------------|
| LLM call (cached prompt) | 800-1500ms |
| SQL validation | <1ms |
| ClickHouse execution | 10-100ms |
| Frontend render | <50ms |
| **Total** | **~1-2 seconds** |

### 3. Associative Query (Programmatic)

```
Selection: dim_deals.stage_label = ['Proposal']
    |
    v
SelectionState.parse() -> {dim_deals: {stage_label: ['Proposal']}}
    |
    v
AssociativeGraph.bfs_paths() -> shortest paths to all tables
    |
    v
Propagator.propagate() -> {table: SQL_subquery} for reachable IDs
    |
    v
SQL Builder -> COUNT, FIELD_VALUES, MEASURE, TIME_SERIES queries
    |
    v
ClickHouse -> results for each requested computation
```

---

## Design Decisions

### Why ClickHouse?

ClickHouse is a columnar OLAP database optimized for analytical queries. For this use case:

- **Fast aggregations** — Sum, count, avg over millions of rows in milliseconds
- **ReplacingMergeTree** — Built-in deduplication for incremental ingestion
- **FINAL modifier** — Query-time deduplication without explicit merge operations
- **Dictionaries** — In-memory lookup tables for fast dimension joins
- **Low overhead** — Single Docker container, no cluster needed for this scale

### Why a Three-Layer Architecture?

| Decision | Rationale |
|----------|-----------|
| Bronze stores raw JSON | If HubSpot changes a property name or adds a field, nothing breaks. We re-extract from bronze. |
| Silver is config-driven | Adding a property is a one-line change. No migration files, no schema diffs. |
| Silver rebuilds fully | ClickHouse makes this fast. Avoids migration complexity and schema drift. |
| Gold pre-aggregates | Complex multi-table JOINs are expensive. Gold computes them once per hour. |
| Separate databases | Clear namespace separation. Different retention policies per layer. |

### Why LLM for SQL Instead of a Query Builder?

Revenue leaders don't think in filters and aggregations — they think in questions: "Will we hit target?", "Which deals are slipping?", "What's different about Alex's win rate?"

A traditional dashboard with fixed views can't anticipate these questions. An LLM that sees the schema and business context can generate the exact SQL needed for any ad-hoc question, while the structured output format ensures deterministic rendering.

**Safety model:**
- The LLM never sees actual data — only schema metadata and column descriptions
- SQL is validated before execution (whitelist tables, reject mutations)
- Auto-injected LIMIT prevents accidental full-table scans
- Prompt caching keeps latency under 2 seconds

### Why Associative Model?

The associative model (inspired by Qlik Sense) provides a fundamentally different UX than traditional filtering:

- **One selection, all tables filter** — Select "Proposal" stage and instantly see which contacts, companies, and activities are connected to those deals
- **Three-state field values** — Values are "possible" (reachable given current selections), "excluded" (not reachable), or "selected" (active filter)
- **No explicit JOINs** — The graph engine handles bridge traversal automatically

This is more intuitive for non-technical users exploring data relationships.

### Why Multi-Provider LLM?

Different users have different access:

| Provider | Use Case |
|----------|----------|
| Anthropic API | Team has API key, best quality + prompt caching |
| OpenAI API | Already has OpenAI key, good fallback |
| Claude OAuth | Individual Claude Pro/Max subscriber, no API key needed |
| Claude CLI | Developer with Claude Code installed, zero config |

Auto-detection means the system works out of the box for developers (CLI) and is easily configured for production (API key).

---

## Relationship Graph

The core data model is a graph of 14 queryable tables connected by 9 bridge tables and 8+ reference joins.

### Entities

```
                        dim_owners
                       /    |     \
                      /     |      \
              dim_leads  dim_deals  dim_companies
                |    \   / |    \   /    |
                |     \ /  |     \ /     |
                |    bridge|    bridge    |
                |      s   |      s      |
                |          |             |
              dim_contacts----bridge----dim_companies
                      |
                      |
                fact_activities
```

### Bridge Tables (N:M Relationships)

| Bridge | Connects | Via |
|--------|----------|-----|
| `bridge_contact_company` | Contacts <-> Companies | `contact_id`, `company_id` |
| `bridge_contact_deal` | Contacts <-> Deals | `contact_id`, `deal_id` |
| `bridge_deal_company` | Deals <-> Companies | `deal_id`, `company_id` |
| `bridge_lead_contact` | Leads <-> Contacts | `lead_id`, `contact_id` |
| `bridge_deal_lead` | Deals <-> Leads | `deal_id`, `lead_id` |
| `bridge_lead_company` | Leads <-> Companies | `lead_id`, `company_id` |
| `bridge_activity_contact` | Activities <-> Contacts | `activity_id`, `contact_id` |
| `bridge_activity_company` | Activities <-> Companies | `activity_id`, `company_id` |
| `bridge_activity_deal` | Activities <-> Deals | `activity_id`, `deal_id` |

### Reference Joins (FK Relationships)

| From | To | Join |
|------|----|------|
| `dim_deals.pipeline` | `dim_pipelines.pipeline_id` | Pipeline name lookup |
| `dim_deals.dealstage` | `dim_pipeline_stages.stage_id` | Stage name lookup |
| `dim_deals.hubspot_owner_id` | `dim_owners.owner_id` | Deal owner lookup |
| `dim_leads.hubspot_owner_id` | `dim_owners.owner_id` | Lead owner lookup |
| `dim_companies.hubspot_owner_id` | `dim_owners.owner_id` | Company owner lookup |
| `fact_activities.hubspot_owner_id` | `dim_owners.owner_id` | Activity owner lookup |
| `dim_leads.hs_pipeline` | `dim_lead_pipelines.pipeline_id` | Lead pipeline lookup |
| `dim_leads.hs_lead_status` | `dim_lead_pipeline_stages.stage_id` | Lead stage lookup |

---

## File Structure

```
hs2ch/
|-- app/                          # FastAPI backend
|   |-- main.py                   # App entry, CORS, router mounting
|   |-- db.py                     # ClickHouse client singleton
|   |-- config.py                 # Table/graph/join configuration
|   |-- api/
|   |   |-- routes.py             # Analytics engine endpoints
|   |   |-- chat_routes.py        # Chat + settings + OAuth endpoints
|   |   |-- models.py             # Analytics request/response models
|   |   |-- chat_models.py        # Chat request/response models
|   |-- engine/
|   |   |-- graph.py              # AssociativeGraph (BFS, adjacency)
|   |   |-- propagator.py         # Selection propagation
|   |   |-- state.py              # SelectionState dataclass
|   |   |-- sql_builder.py        # SQL generation functions
|   |   |-- metrics.py            # 24 computed metrics registry
|   |-- llm/
|   |   |-- config.py             # Multi-provider config (~/.hs2ch/config.json)
|   |   |-- providers.py          # Anthropic, OpenAI, OAuth, CLI providers
|   |   |-- schema_prompt.py      # LLM system prompt builder
|   |   |-- response_schema.py    # Structured output models
|   |   |-- sql_validator.py      # SQL safety (whitelist + mutation blocking)
|   |   |-- oauth.py              # Claude OAuth token management
|   |   |-- warmup.py             # Prompt cache warmup (startup)
|   |-- semantic/
|       |-- layer.py              # HubSpot property metadata enrichment
|
|-- assets/                       # Dagster assets (ETL)
|   |-- crm.py                    # CRM object extraction (5 assets)
|   |-- activities.py             # Activity extraction (5 assets)
|   |-- marketing.py              # Marketing extraction (3 assets)
|   |-- associations.py           # Association bridges (15 assets)
|   |-- silver.py                 # Silver transform (10 dim + 1 fact + 9 bridge + DQ)
|   |-- gold.py                   # Gold aggregates (4 assets)
|
|-- resources/                    # Dagster resources
|   |-- hubspot.py                # HubSpot API client
|   |-- clickhouse.py             # ClickHouse bulk insert client
|
|-- frontend/                     # React application
|   |-- src/
|   |   |-- main.tsx              # Entry + router setup
|   |   |-- App.tsx               # Main layout
|   |   |-- components/
|   |   |   |-- chat/             # Chat UI (container, message, input, SQL, suggestions)
|   |   |   |-- viz/              # Visualizations (number, table, bar, line, funnel)
|   |   |   |-- settings/         # Settings drawer
|   |   |   |-- diagrams/         # Architecture SVG diagrams
|   |   |-- hooks/                # useChat, useConversations, useAnalyticsQuery
|   |   |-- types/                # TypeScript interfaces
|   |   |-- pages/                # ArchitecturePage
|   |-- vite.config.ts            # Dev server + proxy config
|   |-- package.json
|
|-- scripts/
|   |-- init_clickhouse.py        # Schema initialization
|   |-- init_clickhouse.sql       # DDL for bronze/silver/gold databases
|
|-- definitions.py                # Dagster: assets + jobs + schedules + resources
|-- jobs.py                       # Dagster: job definitions
|-- schedules.py                  # Dagster: hourly cron schedule
|-- silver_config.py              # Silver layer column definitions + dictionaries
|-- docker-compose.yml            # ClickHouse service
|-- start.sh                      # Multi-service startup script
|-- pyproject.toml                # Python project metadata + dependencies
|-- .env                          # Environment variables (gitignored)
|-- .env.example                  # Template for .env
```

---

## Deployment Topology

### Local Development

All services run locally via `start.sh`:

| Service | Port | Process |
|---------|------|---------|
| ClickHouse | 8124 (HTTP), 9001 (native) | Docker container |
| FastAPI | 8192 | Uvicorn (Python) |
| Dagster | 8194 | Dagster webserver + daemon |
| Frontend | 8193 | Vite dev server (Node.js) |

### Production (Single Server)

```bash
# ClickHouse: Docker or native install
# Backend: gunicorn + uvicorn workers
# Frontend: vite build -> serve static from FastAPI
# Dagster: dagster-daemon + dagster-webserver (systemd)
```

Environment variables via `.env` or secrets manager. `DAGSTER_HOME` for persistent storage.

---

## Security Considerations

See `SECURITY_AUDIT.md` for the full audit. Key points:

- **SQL injection** — Analytics engine validates column names against config whitelist. Chat SQL validator blocks mutations and restricts table access.
- **No authentication** — Currently no auth on any endpoint. Suitable for local/VPN-only deployment.
- **CORS** — Wildcard (`*`) in development. Should be restricted to `http://localhost:8193` in production.
- **API keys** — Stored in `~/.hs2ch/config.json` with `0600` permissions. Returned masked via API.
- **LLM data isolation** — The LLM never sees query results or business data. Only schema metadata and user questions.
- **ClickHouse credentials** — Default `hs2ch`/`hs2ch` in development. Should use a read-only user in production.
