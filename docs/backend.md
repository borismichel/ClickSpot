# Backend

The backend is a **FastAPI** application that serves several distinct surfaces:

1. **Analytics Engine** — Associative graph-based query builder (Qlik-inspired selection propagation)
2. **Chat API** — LLM-powered natural language to ClickHouse SQL
3. **Data API** — Direct SQL execution with dashboard filter injection
4. **Object / Dashboard / Conversation APIs** — Server-side persistence for saved query objects, dashboards, and chat history (backed by SQLite in `app/store.py`)
5. **Data Spaces API** — Scoped views over the warehouse with their own discovery, preview, chat, and dashboards (`/api/v1/spaces/*`)
6. **SQL Filter Engine** — Rule-based AST rewriting for dashboard global filters
7. **MCP server** (separate process, `python -m app.mcp.server`) — Exposes the anonymized warehouse to Claude Desktop / other MCP clients with the same schema prompt and SQL validator as in-app chat

All share the same ClickHouse connection and table configuration. The in-process app also initializes a SQLite store and loads saved data spaces on startup (`lifespan` in `app/main.py`).

---

## Running

```bash
source .venv/bin/activate
uvicorn app.main:app --port 8192 --reload
```

API docs: http://localhost:8192/docs

---

## Analytics Engine

### Associative Model

The analytics engine implements a **Qlik-like associative model**. When a user selects a value in one table (e.g., `dim_deals.stage_label = 'Proposal'`), the engine automatically propagates that selection through the relationship graph to compute reachable record sets in all connected tables.

```
User selects: dim_deals.stage_label = 'Proposal'
                    |
                    v
          AssociativeGraph.bfs_paths()
                    |
        +-----------+-----------+
        |           |           |
        v           v           v
   dim_contacts  dim_companies  fact_activities
   (via bridge)  (via bridge)   (via bridge)
```

### Components

#### AssociativeGraph (`app/engine/graph.py`)

A bidirectional graph of all queryable tables and their relationships.

**Nodes:** Silver dimensions, facts, and gold aggregates

**Edge types:**
- **Bridge edges:** N:M relationships via bridge tables (e.g., contacts <-> deals via `bridge_contact_deal`)
- **Reference edges:** Direct FK joins (e.g., deals -> pipelines via `pipeline = pipeline_id`)

**Key methods:**
- `neighbors(table)` — Adjacent tables
- `bfs_paths(start)` — Shortest path to all reachable tables
- `all_tables()` — All queryable tables
- `primary_key(table)` — Primary key column name

#### SelectionState (`app/engine/state.py`)

Parses user selections from the `{table.column: [values]}` format into a structured `{table: {column: [values]}}` dict.

#### Propagator (`app/engine/propagator.py`)

Computes reachable ID sets for every table given the current selections.

**Algorithm:**
1. Build direct ID subqueries for each table with selections
2. BFS from each selected table to all reachable tables
3. Chain bridge/FK traversals to build SQL subqueries for reachable IDs
4. Combine results from multiple selection sources

**Output:** `{table: sql_subquery | None}` where `None` means "no filter" (all records reachable).

#### SQL Builder (`app/engine/sql_builder.py`)

Generates ClickHouse SQL for all query types. Handles the differences between silver tables (use `FINAL`, filter `archived = 0`) and gold tables (no `FINAL`, no archived column).

**Query types:**
- Count queries: `SELECT count(DISTINCT pk) FROM ...`
- Field value queries: `SELECT DISTINCT column, count() FROM ...`
- Measure queries: `SELECT agg(column) FROM ...`
- Grouped measures: `SELECT group_col, agg(column) ... GROUP BY ...`
- Time series: `SELECT toStartOfMonth(date_col), agg(measure_col) ... GROUP BY ...`
- List queries: `SELECT columns FROM ... LIMIT ... OFFSET ...`

#### Metrics Registry (`app/engine/metrics.py`)

22 pre-defined computed metrics with SQL expressions, labels, and format hints.

```python
COMPUTED_METRICS = {
    "win_rate": {
        "label": "Win Rate",
        "format": "percent",
        "table": "dim_deals",
        "sql": "countIf(hs_is_closed_won = 'true') * 1.0 / nullIf(countIf(hs_is_closed = 'true'), 0)",
    },
    # ... 21 more
}
```

### API Endpoints

#### `POST /api/v1/query`

The core analytics endpoint. Accepts selections and returns computed results.

**Request body (`QueryRequest`):**

```json
{
  "selections": {
    "dim_deals.stage_label": ["Proposal", "Negotiation"]
  },
  "counts": true,
  "field_values": ["dim_deals.owner_name"],
  "measures": [
    {"table": "dim_deals", "column": "amount", "agg": "sum"}
  ],
  "grouped_measures": [
    {"table": "dim_deals", "column": "amount", "agg": "sum", "group_by": ["owner_name"], "limit": 10}
  ],
  "time_series": [
    {"table": "dim_deals", "measure_column": "amount", "date_column": "closedate", "granularity": "month"}
  ],
  "computed_metrics": ["win_rate", "pipeline_value"],
  "lists": {
    "dim_deals": {"columns": ["dealname", "amount", "owner_name"], "limit": 50, "offset": 0}
  },
  "date_from": "2026-01-01",
  "date_to": "2026-06-30"
}
```

All fields are optional. The engine computes only what is requested.

**Response body (`QueryResponse`):**

```json
{
  "reachable_counts": {"dim_deals": 42, "dim_contacts": 128, "dim_companies": 31},
  "field_values": {
    "dim_deals.owner_name": {
      "possible": [{"value": "Alex Johnson", "count": 15}, ...],
      "excluded": [{"value": "Inactive Rep", "count": 3}]
    }
  },
  "measures": {"dim_deals.amount.sum": 1250000.0},
  "grouped_measures": {
    "dim_deals.amount.sum.by.owner_name": [
      {"groups": {"owner_name": "Alex Johnson"}, "value": 450000.0}
    ]
  },
  "time_series": {
    "dim_deals.amount.month": [
      {"period": "2026-01", "value": 200000.0}
    ]
  },
  "computed_metrics": {"win_rate": 0.35, "pipeline_value": 2400000.0},
  "lists": {
    "dim_deals": {
      "rows": [{"dealname": "Example Corp", "amount": 45000, "owner_name": "Alex Johnson"}],
      "total": 42
    }
  }
}
```

#### `GET /api/v1/schema`

Returns the full system metadata: table definitions, fields with types and display names, graph edges, and reference joins.

#### `GET /api/v1/metrics-catalog`

Returns the 22 computed metrics with labels, formats, and SQL.

#### `GET /api/v1/metadata`

Returns row counts and last-loaded timestamps for all tables.

---

## Chat API

### LLM-Powered SQL Generation

Users type natural language questions. The LLM generates ClickHouse SQL, which is validated and executed.

```
"What's our win rate by rep?"
         |
         v
  Schema Prompt (tables + semantics + examples)
  + Conversation History (questions + SQL, no results)
  + User Question
         |
         v
    LLM Provider (Claude / GPT-4o)
         |
         v
  Structured Response: {sql, viz, title, explanation}
         |
         v
    SQL Validator (whitelist tables, reject mutations)
         |
         v
    ClickHouse Execution
         |
         v
  Results + Timing Metadata
```

### Providers (`app/llm/providers.py`)

Four LLM providers with automatic fallback:

| Provider | Model | Authentication | Notes |
|----------|-------|---------------|-------|
| **Anthropic API** | `claude-sonnet-4-6` | `ANTHROPIC_API_KEY` or config file | Primary. Prompt caching via `cache_control`. |
| **OpenAI API** | `gpt-4o` | `OPENAI_API_KEY` or config file | Fallback. JSON schema response format. |
| **Claude OAuth** | Claude (via OAuth) | `~/.hs2ch/claude-oauth.json` | For Claude Pro/Max subscribers. Auto-refresh. |
| **Claude CLI** | Claude (via CLI) | `claude` binary in PATH | Zero-config local development. |

**Auto-detection order:** Anthropic API > OpenAI > Claude OAuth > Claude CLI. Uses the first available provider.

All providers use **structured output** (tool use / JSON schema) to force the LLM to return a strict JSON shape, eliminating parsing ambiguity.

### Schema Prompt (`app/llm/schema_prompt.py`)

The system prompt sent to the LLM. Built from three sources:

1. **Table configuration** (`app/config.py`) — table names, columns, types
2. **Semantic layer** (`app/semantic/layer.py`) — HubSpot property labels, descriptions, enum options
3. **Business context** — handwritten revenue context, team structure, pipeline names

**Prompt sections:**
1. **Rules** — ClickHouse SQL dialect, FINAL usage, archived filtering, date handling
2. **Data model** — Entity descriptions and relationships
3. **Dictionaries** — Available `dictGet()` lookups (auto-generated from `DICT_CONFIGS`)
4. **Tables** — Full column schema with types and descriptions (~197 columns)
5. **Relationships** — Bridge tables with key columns
6. **Metrics** — 22 pre-defined metric SQL patterns
7. **Business context** — Company details, pipeline names, team, currency
8. **Examples** — Few-shot SQL examples for common question patterns
9. **Output format** — JSON schema specification

**Prompt caching:** With Anthropic, the static schema blocks are marked with `cache_control: {"type": "ephemeral"}`. This avoids re-tokenizing ~3K tokens on every request within a 5-minute window.

### SQL Validator (`app/llm/sql_validator.py`)

Validates LLM-generated SQL before execution:

- Must start with `SELECT` or `WITH` (CTEs allowed)
- Rejects mutation keywords: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `GRANT`, `REVOKE`, `SYSTEM`, `ATTACH`, `DETACH`, `RENAME`
- All table references must be in the whitelist (silver + gold tables)
- Blocks `system.*` and `information_schema.*`
- Auto-injects `LIMIT 10000` if missing

### Semantic Layer (`app/semantic/layer.py`)

Fetches HubSpot property metadata to enrich the schema prompt with human-readable labels and descriptions.

**Scope:** Only properties that match columns in `silver_config.py` — ~197 columns across all dimensions. This prevents the LLM from hallucinating columns that don't exist in ClickHouse.

**Cache:** Written to `~/.hs2ch/schema_cache.json`. Rebuilt via `POST /api/v1/schema/refresh`. Loaded from cache on startup — no HubSpot API calls on the hot path.

### OAuth Manager (`app/llm/oauth.py`)

Manages Claude OAuth tokens for users with Claude Pro/Max subscriptions.

- Token storage: `~/.hs2ch/claude-oauth.json` (permissions: `0600`)
- Token lifetime: 8 hours with 5-minute refresh buffer
- Auto-refresh via Anthropic's token endpoint
- Thread-safe with `asyncio.Lock`

### Chat Endpoints

#### `POST /api/v1/chat`

```json
// Request
{
  "message": "What's our win rate by rep this quarter?",
  "history": [
    {"role": "user", "content": "Show me pipeline coverage"},
    {"role": "assistant", "content": "Pipeline coverage is...", "sql": "SELECT ..."}
  ]
}

// Response
{
  "explanation": "Win rate by rep for Q2 2026",
  "sql": "SELECT owner_name, countIf(hs_is_closed_won = 'true') ...",
  "results": [{"owner_name": "Alex Johnson", "win_rate": 0.35}],
  "columns": ["owner_name", "win_rate"],
  "row_count": 5,
  "viz": "bar",
  "title": "Win Rate by Rep — Q2 2026",
  "llm_ms": 1200,
  "query_ms": 45,
  "context": [
    {"sql": "SELECT count() FROM ...", "label": "Total Closed Deals"}
  ]
}
```

**Context KPIs:** The LLM can return 2-4 supplementary queries that provide surrounding context for the main result (e.g., "Total Closed Deals" alongside a win rate breakdown). Each KPI can optionally include `previous_sql` for period-over-period comparison — the backend executes both queries and computes `delta_percent`.

**Relative dates:** The schema prompt instructs the LLM to always use ClickHouse date functions (`today()`, `toStartOfMonth()`, etc.) instead of hardcoded dates, so queries remain valid when saved to dashboards.

#### `POST /api/v1/sql` — Execute SQL with optional dashboard filters

```json
// Request
{
  "sql": "SELECT deal_id FROM silver.dim_deals WHERE archived = 0",
  "filters": {
    "date_from": "2026-01-01",
    "date_to": "2026-04-01",
    "owner_ids": ["123"],
    "owner_names": ["Test User"],
    "pipeline_ids": ["abc"],
    "pipeline_labels": ["Sales Pipeline"]
  }
}
```

When `filters` is provided, the SQL is rewritten via the SQL filter engine before execution. See **SQL Filter Engine** below.

#### `GET /api/v1/filters/options` — Dropdown data for dashboard filter bar

Returns `{owners: [{id, name}], pipelines: [{id, label}]}` from `dim_owners` and `dim_pipelines`.

#### `GET /api/v1/tables` — List all ClickHouse tables
#### `GET /api/v1/tables/{database}/{table}` — Table details (columns, sample data)

#### `GET /api/v1/settings` — Current config (API keys masked)
#### `PUT /api/v1/settings` — Update config
#### `GET /api/v1/settings/providers` — Available providers with readiness status
#### `POST /api/v1/oauth/save` — Save Claude OAuth token
#### `GET /api/v1/oauth/status` — Token status and expiry
#### `POST /api/v1/oauth/logout` — Clear OAuth tokens
#### `POST /api/v1/schema/refresh` — Rebuild semantic layer from HubSpot
#### `GET /api/v1/schema/semantic` — Current semantic layer cache

---

## SQL Filter Engine (`app/engine/sql_filter.py`)

Rule-based SQL rewriting for dashboard global filters. No AI involved — purely AST-based manipulation using **sqlglot** with the ClickHouse dialect.

### How It Works

```
Dashboard filter state (date, owner, pipeline)
    |
    v
sqlglot.parse(sql, dialect="clickhouse")
    |
    v
Walk AST → find Table nodes → lookup in FILTER_COLUMNS registry
    |
    v
Build AST conditions (safe — values are never parsed as SQL)
    |
    v
Inject into enclosing Select WHERE clause
    |
    v
sqlglot.generate(tree, dialect="clickhouse")
```

### Filter Column Registry

Static mapping from `database.table` to filterable column names per dimension:

| Table | Date Column | Owner Column | Pipeline Column |
|-------|-------------|-------------|----------------|
| `silver.dim_deals` | `closedate` | `hubspot_owner_id` | `pipeline` |
| `silver.dim_contacts` | `createdate` | *(none)* | *(none)* |
| `silver.dim_companies` | `createdate` | `hubspot_owner_id` | *(none)* |
| `silver.dim_leads` | `createdate` | `hubspot_owner_id` | `hs_pipeline` |
| `gold.agg_rep_performance` | `period_start` | `owner_name` | *(none)* |
| `gold.agg_deal_health` | *(none)* | `owner_name` | `pipeline_label` |

Silver tables use IDs (`hubspot_owner_id`, `pipeline`). Gold tables use pre-denormalized names (`owner_name`, `pipeline_label`). The frontend sends both forms; the rewriter picks the correct one per table.

### Safety

- Values are constructed as AST literal nodes (`exp.Literal.string()`), never parsed as SQL
- If sqlglot fails to parse, the original SQL is returned unchanged
- Tables not in the registry are silently skipped
- CTE aliases and unqualified tables are ignored (only `database.table` references are processed)

### Tests

24 unit tests in `tests/test_sql_filter.py` covering: date filters, owner ID vs name, pipeline ID vs label, aliases, JOINs, CTEs, empty filters, unknown tables, combined filters, SQL injection safety, malformed SQL fallback.

---

## Configuration

### Table Config (`app/config.py`)

Central registry of all queryable tables, their columns, display names, graph edges, and reference joins.

```python
TABLES = {
    "dim_deals": {
        "primary_key": "deal_id",
        "display_name": "Deals",
        "database": "silver",
        "fields": {
            "dealname": {"type": "String", "display": "Deal Name"},
            "amount": {"type": "Nullable(Float64)", "display": "Amount"},
            # ...
        },
    },
    # ...
}

GRAPH_EDGES = [
    {"from": "dim_contacts", "to": "dim_deals", "bridge": "bridge_contact_deal", "from_key": "contact_id", "to_key": "deal_id"},
    # ...
]

REFERENCE_JOINS = [
    {"from": "dim_deals", "to": "dim_pipelines", "from_col": "pipeline", "to_col": "pipeline_id"},
    # ...
]
```

### LLM Config (`app/llm/config.py`)

File-based config at `~/.hs2ch/config.json`:

```json
{
  "ai_provider": "auto",
  "anthropic_api_key": "sk-ant-...",
  "openai_api_key": "sk-...",
  "anthropic_model": "claude-sonnet-4-6",
  "openai_model": "gpt-4o"
}
```

Environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) override file config.

### Database (`app/db.py`)

Single shared `clickhouse_connect` client, reused across requests for connection pooling. Sessions are explicitly disabled (`autogenerate_session_id=False` globally, `cancel_http_readonly_queries_on_client_close=0`) so concurrent requests never collide on a session ID — without this, parallel requests trigger `"concurrent queries within the same session"` errors in ClickHouse. Configuration from environment:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLICKHOUSE_HOST` | `localhost` | ClickHouse server hostname |
| `CLICKHOUSE_PORT` | `8123` (project standard is `8124` — set explicitly via `.env`) | HTTP interface port |
| `CLICKHOUSE_USER` | `default` | Username |
| `CLICKHOUSE_PASSWORD` | (empty) | Password |

### Persistence (`app/store.py`)

A SQLite database (initialized on FastAPI startup via `lifespan`) backs `object_routes`, `dashboard_routes`, and `conversation_routes`. The frontend hooks (`useObjectRepo`, `useDashboards`, `useConversations`) sync to/from these endpoints rather than living in `localStorage` alone.

---

## Data Spaces (`app/spaces/`)

A Data Space is a user-defined slice of the warehouse: a *grain entity* (e.g. `dim_deals`), a set of dimensions discovered from that entity, optional fixed filters, and its own scoped chat + dashboards.

| Module | Purpose |
|--------|---------|
| `app/spaces/config.py` | `DataSpaceConfig` Pydantic schema |
| `app/spaces/discovery.py` | Introspects available grain entities, dimensions, dicts |
| `app/spaces/registry.py` | CRUD + `preview_space()` + startup `load_saved_spaces()` |
| `app/spaces/space_filter.py` | Per-space SQL rewriting (analogous to `engine/sql_filter.py` but scoped) |
| `app/spaces/space_prompt.py` | Schema prompt scoped to a single space |
| `app/spaces/generator.py` | Generation helpers for derived assets |
| `app/spaces/routes.py` | All `/api/v1/spaces/*` endpoints (~26) |

Spaces are persisted via `app/store.py` and re-loaded into memory at FastAPI startup.

---

## MCP Server (`app/mcp/`)

Standalone process (`python -m app.mcp.server`) that wraps the `silver_anon` and `gold_anon` databases for external Claude clients (Claude Desktop, etc.) using `FastMCP`.

- Reuses `app.llm.schema_prompt.build_schema_prompt` so MCP clients see the same dict hints, ILIKE guidance, and table whitelist as in-app chat.
- Reuses `app.llm.sql_validator.ensure_limit` for the same LIMIT auto-injection behavior.
- `app/mcp/guardrails.py` enforces an explicit `MCP_ALLOWED_TABLES` allowlist + `EXCLUDED_TABLES` denylist on top of the validator and strips raw activity payloads (`ACTIVITY_STRIP_RE`).
- `app/mcp/pii.py` provides the PII filters specific to MCP-exposed responses.
- **No LLM lives in this server** — the MCP client drives SQL generation; this process just exposes grounded context and a guarded execution path against the anon databases.

---

## Endpoint Summary

### Core analytics + chat + data

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health check |
| POST | `/api/v1/query` | Associative analytics query |
| GET | `/api/v1/schema` | Table and graph metadata |
| GET | `/api/v1/metrics-catalog` | Computed metrics registry |
| GET | `/api/v1/metadata` | Data load status |
| POST | `/api/v1/chat` | Natural language to SQL |
| GET | `/api/v1/tables` | List all ClickHouse tables |
| GET | `/api/v1/tables/{db}/{table}` | Table details + sample data |
| POST | `/api/v1/sql` | Execute SQL (with optional dashboard filters) |
| POST | `/api/v1/test-filter` | Debug endpoint: preview filter-rewritten SQL |
| GET | `/api/v1/filters/options` | Owner/pipeline dropdown data |
| GET | `/api/v1/settings` | LLM configuration |
| PUT | `/api/v1/settings` | Update LLM configuration |
| GET | `/api/v1/settings/providers` | Available LLM providers |
| POST | `/api/v1/oauth/save` | Save Claude OAuth token |
| GET | `/api/v1/oauth/status` | OAuth token status |
| POST | `/api/v1/oauth/logout` | Clear OAuth tokens |
| POST | `/api/v1/schema/refresh` | Rebuild semantic layer |
| GET | `/api/v1/schema/semantic` | Semantic layer cache |

### Saved objects / dashboards / conversations (server-side persistence)

| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/api/v1/objects` | List / create saved query+viz objects |
| GET/DELETE | `/api/v1/objects/{object_id}` | Read / delete one object |
| POST | `/api/v1/objects/import` | Bulk import (frontend localStorage migration) |
| GET/POST | `/api/v1/dashboards` | List / create dashboards |
| GET/PUT/DELETE | `/api/v1/dashboards/{dash_id}` | CRUD on a dashboard |
| POST | `/api/v1/dashboards/{dash_id}/items` | Add a saved object to a dashboard |
| DELETE | `/api/v1/dashboards/{dash_id}/items/{object_id}` | Remove item |
| PUT | `/api/v1/dashboards/{dash_id}/layouts` | Persist grid layout |
| POST | `/api/v1/dashboards/import` | Bulk import |
| GET/POST | `/api/v1/conversations` | List / create chat conversations |
| GET/PUT/DELETE | `/api/v1/conversations/{conv_id}` | CRUD on one conversation |
| POST | `/api/v1/conversations/{conv_id}/messages` | Append a message |
| POST | `/api/v1/conversations/import` | Bulk import |

### Data Spaces (`/api/v1/spaces`)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/spaces` | List spaces |
| GET | `/api/v1/spaces/entities` | Available grain entities (e.g. `dim_deals`) |
| GET | `/api/v1/spaces/dimensions/{grain_entity}` | Dimensions discoverable from a grain entity |
| GET | `/api/v1/spaces/dicts` | Available dictionaries |
| GET | `/api/v1/spaces/dashboards/all` | All dashboards across all spaces |
| GET | `/api/v1/spaces/{space_id}` | Get one space |
| POST | `/api/v1/spaces` | Create space |
| PUT | `/api/v1/spaces/{space_id}` | Update space |
| DELETE | `/api/v1/spaces/{space_id}` | Delete space |
| POST | `/api/v1/spaces/test-filter` | Preview filter SQL for an unsaved space config |
| POST | `/api/v1/spaces/preview` | Preview rows for an unsaved space config |
| GET | `/api/v1/spaces/{space_id}/columns` | Columns for the saved space |
| GET | `/api/v1/spaces/{space_id}/stats` | Row counts / metadata for the saved space |
| GET | `/api/v1/spaces/{space_id}/columns/{col_name}/values` | Distinct values for one column |
| POST | `/api/v1/spaces/{space_id}/chat` | Scoped LLM chat |
| GET/POST/DELETE | `/api/v1/spaces/{space_id}/conversation` | Get / append-message / clear the space's single conversation |
| GET/POST | `/api/v1/spaces/{space_id}/dashboards` | List / create dashboards inside a space |
| GET/PUT/DELETE | `/api/v1/spaces/{space_id}/dashboards/{dash_id}` | CRUD on a space dashboard |
| POST | `/api/v1/spaces/{space_id}/dashboards/{dash_id}/items` | Add item |
| DELETE | `/api/v1/spaces/{space_id}/dashboards/{dash_id}/items/{item_id}` | Remove item |
| PUT | `/api/v1/spaces/{space_id}/dashboards/{dash_id}/layouts` | Persist layout |
