# Frontend

> A **React 19** single-page application for querying HubSpot analytics data in natural language, with persistent dashboards and a data explorer.

---

## Contents

- [Running](#running)
- [Stack](#stack)
- [Routing](#routing)
- [Layout](#layout)
- [Components](#components)
- [Hooks](#hooks)
- [Types](#types)
- [Build Configuration](#build-configuration)
- [Formatting Conventions](#formatting-conventions)

---

## Running

```bash
cd frontend
npm install
npm run dev
```

Runs on http://localhost:8193. Proxies `/api` requests to the backend at http://localhost:8192.

---

## Stack

| Library | Version | Purpose |
|---------|---------|---------|
| React | 19.2 | UI framework |
| TypeScript | 5.9 | Type safety |
| Vite | 8.0 | Build tool and dev server |
| Ant Design | 6.3 | Component library (layout, forms, tables, drawers) |
| Recharts | 3.8 | Chart library (area, bar, funnel) |
| React Router | 7.14 | Client-side routing |
| TanStack Query | 5.96 | API data fetching and caching |
| @xyflow/react | 12.10 | Graph/diagram canvas (used by Data Spaces designer) |
| react-grid-layout | 2.2 | Draggable/resizable dashboard grid |
| xlsx + jspdf | 0.18 / 4.2 | Export helpers (table → XLSX / PDF) |

---

## Routing

| Route | Page | Purpose |
|-------|------|---------|
| `/` | `App` | Main chat interface |
| `/dashboard` | `DashboardPage` | Persistent dashboards with global filters |
| `/library` | `ObjectLibraryPage` | Saved query/viz objects |
| `/data` | `DataExplorerPage` | Interactive table/query browser |
| `/architecture` | `ArchitecturePage` | System diagrams |
| `/spaces` | `DataSpaceListPage` | Browse all spaces |
| `/spaces/new` | `DataSpaceDesignerPage` | Create a new space |
| `/spaces/:id/edit` | `DataSpaceDesignerPage` | Edit an existing space |
| `/spaces/:id` | `SpaceOverviewPage` | Live preview + filters for a space |
| `/spaces/:spaceId/dashboard` | `SpaceDashboardPage` | Dashboards scoped to a space |

Set up in `main.tsx` with `BrowserRouter` from React Router.

Each page sets `document.title` to `"ClickSpot | {page}"` via the `usePageTitle()` hook.

---

## Layout

### Main Chat Interface (`/`)

```text
+----------------------------------------------------------------------+
| ClickSpot [Library] [Dashboard] [Spaces] [Data] [Arch] [Settings]|
+----------+------------------------------------------+
| Sidebar  |                                          |
|          |   Welcome! Ask me anything about your    |
| Convos:  |   HubSpot data.                         |
| > Q2 pipe|                                          |
|   Rep rev|   Suggested:                             |
|   Deal h |   > "What's our pipeline coverage?"      |
|          |   > "Show me rep performance this Q"     |
|          |   > "Which deals are at risk?"           |
|          |                                          |
| [+ New]  |                                          |
|          +------------------------------------------+
|          | [Ask a question about your revenue...]   |
+----------+------------------------------------------+
```

### After a Chat Exchange

```text
|  User:    What's our win rate by rep this quarter?    |
|                                                        |
|  Assistant:                                            |
|    Context KPIs:                                       |
|    [Total Closed: 47]  [Pipeline: EUR 1.8M]           |
|                                                        |
|    Win rate by rep for Q2 2026, based on closed        |
|    deals with close dates in April-June.               |
|                                                        |
|    > SQL (collapsible)                                 |
|    +--------------------------------------------------+
|    | SELECT owner_name,                                |
|    |   countIf(hs_is_closed_won='true') ...            |
|    +--------------------------------------------------+
|                                                        |
|    +--------------------------------------------------+
|    |  ████████████ Alex Johnson      42.1%             |
|    |  ██████████   Maria Chen        35.8%             |
|    |  ████████     Sam Taylor        28.3%             |
|    |  ██████       Jordan Lee        19.2%             |
|    +--------------------------------------------------+
|                                                        |
|    1.2s LLM · 45ms query · 5 rows                      |
```

---

## Components

### Pages

#### `App.tsx`
Main application shell. Ant Design `Layout` with:
- **Header:** Title, nav links (Library, Dashboard, Data, Architecture, Settings)
- **Sider:** `ConversationSidebar` (chat history)
- **Content:** `ChatContainer` (messages + input)

Manages conversation state, auto-saves to localStorage on changes.

#### `DashboardPage.tsx`
Persistent dashboards with draggable/resizable card grid (`react-grid-layout`):
- Dashboard CRUD (create, rename, delete, switch)
- Global filter bar (date range, owner, pipeline) that applies to all cards
- Cards render saved objects using `DashboardCard` which re-executes SQL with filters
- Layouts persist to localStorage

#### `ObjectLibraryPage.tsx`
Browse and manage saved query/visualization objects. Objects are created from chat results via "Save to Library" and can be added to dashboards.

#### `DataExplorerPage.tsx`
Interactive table browser and SQL editor for all ClickHouse tables across bronze/silver/gold layers.

#### `ArchitecturePage.tsx`
Full-page system architecture view with:
- **Data Pipeline diagram** (SVG) — HubSpot to bronze to silver to gold
- **Query Flow diagram** (SVG) — Schema prompt assembly to LLM to validator to ClickHouse
- Detailed text descriptions per layer
- Design decision cards

#### `DataSpaceListPage.tsx`
Lists all Data Spaces with quick links to overview, edit, dashboards, and a "+ New Space" CTA.

#### `DataSpaceDesignerPage.tsx`
Visual designer for creating or editing a Data Space. Used at `/spaces/new` and `/spaces/:id/edit`. Drives `GET /api/v1/spaces/entities`, `GET /api/v1/spaces/dimensions/{grain}`, `POST /api/v1/spaces/preview`, and `POST/PUT /api/v1/spaces`. Components live under `components/spaces/` (column picker, dimension configurator, grain selector, filter input, preview panel).

#### `SpaceOverviewPage.tsx`
Interactive overview of a saved space: filter bar, live row preview, distinct-value lookups, and a chat drawer scoped to the space.

#### `SpaceDashboardPage.tsx`
Dashboards scoped to a single Data Space. Same `react-grid-layout` card grid as the global `DashboardPage`, but filters and saved cards are stored per-space via `/api/v1/spaces/{id}/dashboards/*` (see `useSpaceDashboards`).

### Chat Components

| Component | File | Purpose |
|-----------|------|---------|
| `ChatContainer` | `components/chat/ChatContainer.tsx` | Message list + input. Scrolls to bottom on new messages. Shows loading skeleton during LLM calls. |
| `ChatMessage` | `components/chat/ChatMessage.tsx` | Renders a single message. User messages show the question. Assistant messages show explanation, SQL preview, visualization, context KPIs, and timing metadata. |
| `ChatInput` | `components/chat/ChatInput.tsx` | Text input with send button. Enter to send, Shift+Enter for newline. Disabled during loading. |
| `SuggestedQuestions` | `components/chat/SuggestedQuestions.tsx` | Clickable prompt cards shown on empty chat state. 6 starter questions covering pipeline, reps, deals, trends, leads, and activities. |
| `SQLPreview` | `components/chat/SQLPreview.tsx` | Collapsible SQL code block. Collapsed by default. Syntax-highlighted `<pre>` with copy button. |

### Visualization Components

The LLM returns a `viz` field that determines which visualization to render.

| Type | Component | When Used |
|------|-----------|-----------|
| `number` | `NumberCard` | Single scalar value (win rate, total pipeline, etc.) |
| `table` | `ResultTable` | Multi-column data (deal lists, rep breakdowns) |
| `bar` | `BarChart` | Category comparisons (revenue by rep, deals by source) |
| `line` | `TimeSeriesViz` | Trends over time (monthly revenue, quarterly pipeline) |
| `funnel` | `FunnelViz` | Stage progressions (pipeline stages, lead lifecycle) |
| `comparison` | `ContextBar` (large) | Period-over-period analysis with delta badges |

#### `VizRouter.tsx`
Dispatches to the correct visualization based on the `viz` field.

#### `NumberCard.tsx`
Large formatted number with label. Auto-detects currency (EUR) and percent formatting from column names.

#### `ResultTable.tsx`
Ant Design `Table` with sortable columns. Auto-formats currency, percent, and date columns based on column name heuristics. Epoch dates (`1970-01-01`) are displayed as `"-"` since ClickHouse uses epoch as the default for empty DateTime values.

**HubSpot entity linking:** When both a name column and its corresponding ID column are present (e.g. `dealname` + `deal_id`), the name renders as a clickable link to the HubSpot record and the ID column is auto-hidden. Standalone ID columns also render as links. Uses a dynamic mapping to pair generic aliases to their ID counterparts.

#### `BarChart.tsx`
Recharts `BarChart`. First string column = category axis, first numeric column = bar values. Supports currency formatting.

#### `TimeSeriesViz.tsx`
Recharts `AreaChart` with two rendering modes:

1. **Multi-column:** When the LLM returns `{month, calls, meetings, emails}` — renders each numeric column as a separate colored area.
2. **Multi-series (pivoted):** When data is `{month, category, value}` with duplicate dates — auto-detects the pattern, pivots the data, and renders separate series per category.

Detection logic in `detectMultiSeries()`:
- Exactly 1 string column (not the date) + 1 numeric column
- Multiple distinct values in the string column
- Duplicate date values (confirming multiple series per period)

10-color palette for series differentiation.

#### `FunnelViz.tsx`
Horizontal bar chart ordered by value (largest to smallest). Used for stage-based progressions.

#### `ContextBar.tsx`
Renders 2-4 context KPI cards above the main visualization. Each KPI is a small query the LLM generates alongside the main query to provide surrounding context. Supports period-over-period deltas: when `previous_sql` is provided, shows colored trend badges (green arrow up / red arrow down) with percentage change. Also serves as the primary visualization for the `comparison` viz type (larger layout with 3-column grid).

#### `SaveToRepoButton.tsx`
Button on assistant messages to save the query, viz type, title, and context KPIs to the object library. Saved objects can then be added to dashboards.

### Settings

#### `SettingsDrawer.tsx`
Slide-out drawer from the right edge:

- **Provider selector** — Dropdown with readiness indicators (green "Ready" / grey "Not configured")
- **Anthropic API config** — API key input + model selector (Sonnet 4.6, Haiku 4.5)
- **OpenAI API config** — API key input + model selector (GPT-4o, GPT-4o mini)
- **Claude OAuth** — Token status display with expiry countdown, paste-to-save input, disconnect button
- **Schema cache** — Refresh button
- **Service links** — External links to Dagster UI (8194), FastAPI docs (8192/docs), ClickHouse Playground (8124/play), HubSpot CRM

### Sidebar

#### `ConversationSidebar.tsx`
Left sidebar showing conversation history:
- List of past conversations sorted by last updated
- Title = first user message (truncated to 60 chars)
- Click to load, hover to show delete button
- "+ New Chat" button at top

### Diagrams

#### `PipelineDiagram.tsx`
SVG diagram (900x520 viewBox) showing the data pipeline:
HubSpot API -> Dagster -> ClickHouse layers (Bronze, Silver with sub-boxes, Dictionaries, Gold)

#### `QueryFlowDiagram.tsx`
SVG diagram (900x440 viewBox) showing the query flow:
3 schema sources -> Schema Prompt -> LLM -> Validator (with reject path) -> ClickHouse -> API -> Frontend

---

### Dashboard Components

| Component | File | Purpose |
|-----------|------|---------|
| `DashboardCard` | `components/dashboard/DashboardCard.tsx` | Renders a single saved object in the dashboard grid. Fetches data via `POST /api/v1/sql` with optional filter payload. Executes main SQL, context KPIs, and previous_sql for delta computation. |
| `DashboardFilterBar` | `components/dashboard/DashboardFilterBar.tsx` | Global filter bar with DatePicker.RangePicker, owner multi-select, pipeline multi-select, and Clear button. Stores both IDs and names for silver/gold compatibility. |
| `AddObjectDrawer` | `components/dashboard/AddObjectDrawer.tsx` | Slide-out drawer for adding saved objects from the library to the current dashboard. |

### Data Space Components (`components/spaces/`)

| Component | Purpose |
|-----------|---------|
| `ColumnPicker` | Multi-select for the columns to expose in a space |
| `DimensionConfigurator` | Configure dimensions discovered from a grain entity |
| `FilterInput` | Add/edit fixed filters for a space |
| `GrainSelector` | Pick the space's grain entity (e.g. `dim_deals`) |
| `PreviewPanel` | Live preview of rows returned by the current space config |
| `SpaceChatDrawer` | Slide-out chat scoped to a single space |
| `SpaceDashboardCard` | Dashboard card variant scoped to a space (uses space SQL filter) |
| `SpaceFilterBar` | Filter bar specific to a space's configured filterable columns |

### Top-level shared components (`components/`)

| Component | Purpose |
|-----------|---------|
| `DataTable.tsx` | Generic table used in the data explorer + space previews |
| `FilterBar.tsx` | Generic filter bar shared by overview / dashboard contexts |
| `KPICards.tsx` | KPI tiles row used in space overview and dashboards |
| `PeriodSelector.tsx` | Date period picker (today, week, month, quarter, custom) |
| `PipelineSelector.tsx` | Pipeline picker |
| `SelectionBreadcrumbs.tsx` | Breadcrumb-style display of the current selection |
| `ConversationSidebar.tsx` | Sidebar with chat history (used in `App.tsx`) |

---

## Hooks

### `usePageTitle(subtitle?)`
Sets `document.title` to `"ClickSpot | {subtitle}"` or just `"ClickSpot"` if no subtitle. Called in each page component.

### `useDashboards()`
Persists dashboards via `/api/v1/dashboards/*` (backed by SQLite in `app/store.py`). Each dashboard stores items (object references + grid layout), filters, and metadata.

```typescript
const {
  dashboards, activeId, activeDashboard,
  setActiveId, createDashboard, deleteDashboard, renameDashboard,
  addItem, removeItem, updateLayouts, updateFilters,
} = useDashboards();
```

Filters (date range, owner IDs/names, pipeline IDs/labels) persist with the dashboard.

### `useObjectRepo()`
Persists saved query/visualization objects via `/api/v1/objects/*`. Objects are created from chat responses and can be added to dashboards.

```typescript
const { objects, getObject, addObject, removeObject } = useObjectRepo();
```

Each object stores `{id, title, sql, viz, contextKPIs, columns}`.

### `useFilterOptions()`
Fetches dropdown options for the dashboard filter bar from `GET /api/v1/filters/options`. Returns owners `{id, name}[]` and pipelines `{id, label}[]`. Cached at module level.

### `useChat()`
Core chat state management.

```typescript
const { messages, isLoading, error, sendMessage, newChat, loadMessages } = useChat();
```

- **`sendMessage(text)`** — Appends user message, calls `POST /api/v1/chat`, appends assistant response
- **`loadMessages(msgs)`** — Restores messages from a saved conversation (used when switching conversations in the sidebar)
- **`newChat()`** — Clears all messages for a fresh conversation
- **History management** — Sends conversation history as context (questions + SQL only, never results)
- **Error handling** — Catches API errors and displays them inline

### `useConversations()`
Persists chat history via `/api/v1/conversations` (backed by SQLite in `app/store.py`), with a localStorage fallback for offline state. Conversations survive page refreshes and service restarts.

```typescript
const {
  conversations,
  activeId,
  saveConversation,
  loadConversation,
  startNew,
  deleteConversation,
} = useConversations();
```

Each conversation stores `{id, title, messages, createdAt, updatedAt}`. Messages include full response data (SQL, results, viz type, context KPIs) so conversations are fully restorable.

### `useAnalyticsQuery()`
Wraps `POST /api/v1/query` (the analytics query endpoint) with TanStack Query for caching, deduplication, and loading state. Used wherever the frontend needs reachable counts, field values, measures, or grouped measures.

### `useSelectionState()`
Holds the current `{table.column: [values]}` selection state for the analytics query engine, with helpers to add/remove/clear selections and serialize them for `useAnalyticsQuery`.

### `useDataSpaces()`
CRUD over `/api/v1/spaces` plus discovery helpers (`/entities`, `/dimensions/{grain}`, `/dicts`, `/test-filter`, `/preview`). Returns the saved spaces list and mutators used by the designer and list pages.

### `useSpaceChat(spaceId)`
Per-space chat hook — analogue of `useChat` but talks to `/api/v1/spaces/{id}/chat` and `/api/v1/spaces/{id}/conversation`. Each space has a single persistent conversation.

### `useSpaceDashboards(spaceId)`
CRUD over a space's dashboards (`/api/v1/spaces/{id}/dashboards/*`). Mirrors `useDashboards` but scoped to one space.

---

## Types

### Chat Types (`types/chat.ts`)

```typescript
interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sql?: string;
  results?: Record<string, unknown>[];
  columns?: string[];
  viz?: "number" | "table" | "bar" | "line" | "funnel" | "comparison";
  title?: string;
  context?: ContextKPI[];
  llm_ms?: number;
  query_ms?: number;
  row_count?: number;
  error?: string;
}

interface ContextKPI {
  sql: string;
  label: string;
  value?: number | string;
  previous_sql?: string;
  previous_value?: number | string;
  delta_percent?: number;
}

interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}
```

### Dashboard Types (`types/dashboard.ts`)

```typescript
interface DashboardFilters {
  dateFrom: string | null;
  dateTo: string | null;
  ownerIds: string[];
  ownerNames: string[];
  pipelineIds: string[];
  pipelineLabels: string[];
}

interface SavedObject {
  id: string;
  title: string;
  sql: string;
  viz: VizType;
  contextKPIs: { sql: string; label: string; previous_sql?: string }[];
  columns: string[];
}

interface Dashboard {
  id: string;
  title: string;
  items: { objectId: string; layout: GridLayout }[];
  filters: DashboardFilters;
}
```

### API Types (`types/api.ts`)

Types for the analytics query engine: `QueryRequest`, `QueryResponse`, `SchemaResponse`, `FieldValueItem`, `MeasureRequest`, `GroupedMeasureRow`, `TimeSeriesPoint`, etc.

---

## Build Configuration

### Vite (`vite.config.ts`)

```typescript
export default defineConfig({
  plugins: [react()],
  server: {
    port: 8193,
    proxy: {
      "/api": {
        target: "http://localhost:8192",
        changeOrigin: true,
      },
    },
  },
});
```

The dev server proxies all `/api/*` requests to the FastAPI backend, avoiding CORS issues in development.

### Production Build

```bash
npm run build  # outputs to frontend/dist/
```

The FastAPI backend can serve the built frontend as static files for production deployment.

---

## Formatting Conventions

The frontend auto-detects value formatting from column names:

| Column Name Contains | Format | Example |
|---------------------|--------|---------|
| `amount`, `arr`, `revenue`, `value`, `tcv` | EUR currency | `EUR 45,000` |
| `rate` | Percentage | `35.2%` |
| `days` | Days | `42 days` |
| `date` (value = `1970-01-01*`) | Empty | `-` |
| Everything else | Locale string | `1,234.56` |

This heuristic-based approach means the LLM doesn't need to specify formatting — column names carry enough semantic information.

---

<sub>[← README](https://github.com/borismichel/ClickSpot/blob/main/README.md) · [Architecture](architecture.md) · [Data Pipeline](data-pipeline.md) · [Backend](backend.md) · **Frontend** · [ClickHouse Evaluation](clickhouse-evaluation.md)</sub>
