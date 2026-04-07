# Frontend

A **React 19** single-page application with a chat-based interface for querying HubSpot analytics data using natural language.

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
/architecture    → ArchitecturePage (system diagrams)
/data            → DataExplorerPage (interactive table/query browser)
```

Set up in `main.tsx` with `BrowserRouter` from React Router.

---

## Layout

### Main Chat Interface (`/`)

```
+-----------------------------------------------------+
|  HubSpot Analytics   [Data]  [Architecture]  [Settings]|
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
- **Header:** Title, schema refresh button, architecture link, settings button
- **Sider:** `ConversationSidebar` (chat history)
- **Content:** `ChatContainer` (messages + input)

Manages conversation state, auto-saves to localStorage on changes.

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

#### `VizRouter.tsx`
Dispatches to the correct visualization based on the `viz` field.

#### `NumberCard.tsx`
Large formatted number with label. Auto-detects currency (EUR) and percent formatting from column names.

#### `ResultTable.tsx`
Ant Design `Table` with sortable columns. Auto-formats currency, percent, and date columns based on column name heuristics. Epoch dates (`1970-01-01`) are displayed as `"-"` since ClickHouse uses epoch as the default for empty DateTime values.

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
Renders 2-4 context KPI cards above the main visualization. Each KPI is a small query the LLM generates alongside the main query to provide surrounding context.

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

## Hooks

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
  viz?: "number" | "table" | "bar" | "line" | "funnel";
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
}

interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
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
