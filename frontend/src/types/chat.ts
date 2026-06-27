export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sql?: string;
  results?: Record<string, unknown>[];
  columns?: string[];
  rowCount?: number;
  viz?: "number" | "table" | "bar" | "line" | "funnel" | "comparison";
  title?: string;
  llmMs?: number;
  queryMs?: number;
  context?: ContextKPI[];
  error?: string;
}

export interface ChatRequest {
  message: string;
  history: { role: string; content: string; sql?: string }[];
  // Groups this chat's turns into one Langfuse session (server-side, optional).
  conversation_id?: string;
}

export interface ContextKPI {
  label: string;
  value: string | number | null;
  sql: string;
  previous_sql?: string | null;
  previous_value?: string | number | null;
  delta_percent?: number | null;
  // Non-numeric delta label (e.g. "New") when a percentage is undefined —
  // notably a zero baseline. Mutually exclusive with delta_percent (CLI-42).
  delta_label?: string | null;
}

export interface ChatResponse {
  explanation: string;
  sql: string;
  results: Record<string, unknown>[];
  columns: string[];
  row_count: number;
  viz: "number" | "table" | "bar" | "line" | "funnel" | "comparison";
  title: string;
  llm_ms: number;
  query_ms: number;
  context: ContextKPI[];
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}
