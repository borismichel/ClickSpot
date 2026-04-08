# Frontend

A **React 19** single-page application for querying HubSpot analytics data using natural language, with persistent dashboards and a data explorer.

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

---

## Routing

```
/                → App (main chat interface)
/dashboard       → DashboardPage (persistent dashboards with global filters)
/library         → ObjectLibraryPage (saved query/viz objects)
/data            → DataExplorerPage (interactive table/query browser)
/architecture    → ArchitecturePage (system diagrams)
```

Set up in `main.tsx` with `BrowserRouter` from React Router.

Each page sets `document.title` to `"HubSpot Analytics | {page}"` via the `usePageTitle()` hook.

---

## Layout

### Main Chat Interface (`/`)

```
+-----------------------------------------------------+
| HubSpot Analytics [Library] [Dashboard] [Data] [Arch] [Settings]|
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

```
|  User:    What's our win rate by rep this quarter?    |
|                                                        |
|  Assistant:                                            |
|    Context KPIs:                                       |
|    [Total Closed: 47]  [Pipeline: EUR 2.4M]           |
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
|    |  ████████████ Alex Johnson    42.1%             |
|    |  ██████████   Maria Chen      35.8%             |
|    |  ████████     Sam Taylor    28.3%             |
|    |  ██████       Jordan Lee      19.2%             |
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

---

## Hooks

### `usePageTitle(subtitle?)`
Sets `document.title` to `"HubSpot Analytics | {subtitle}"` or just `"HubSpot Analytics"` if no subtitle. Called in each page component.

### `useDashboards()`
LocalStorage persistence for dashboards. Each dashboard stores items (object references + grid layout), filters, and metadata.

```typescript
const {
  dashboards, activeId, activeDashboard,
  setActiveId, createDashboard, deleteDashboard, renameDashboard,
  addItem, removeItem, updateLayouts, updateFilters,
} = useDashboards();
```

Storage key: `hs2ch_dashboards`. Filters (date range, owner IDs/names, pipeline IDs/labels) persist with the dashboard.

### `useObjectRepo()`
LocalStorage persistence for saved query/visualization objects. Objects are created from chat responses and can be added to dashboards.

```typescript
const { objects, getObject, addObject, removeObject } = useObjectRepo();
```

Storage key: `hs2ch_objects`. Each object stores `{id, title, sql, viz, contextKPIs, columns}`.

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
LocalStorage persistence for chat history. Conversations survive page refreshes and service restarts.

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

Storage key: `hs2ch_conversations`. Each conversation stores `{id, title, messages, createdAt, updatedAt}`. Messages include full response data (SQL, results, viz type, context KPIs) so conversations are fully restorable.

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

Types for the associative analytics engine: `QueryRequest`, `QueryResponse`, `SchemaResponse`, `FieldValueItem`, `MeasureRequest`, `GroupedMeasureRow`, `TimeSeriesPoint`, etc.

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
