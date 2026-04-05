export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  sql?: string;
  results?: Record<string, unknown>[];
  columns?: string[];
  rowCount?: number;
  viz?: "number" | "table" | "bar" | "line" | "funnel";
  title?: string;
  llmMs?: number;
  queryMs?: number;
  context?: ContextKPI[];
  error?: string;
}

export interface ChatRequest {
  message: string;
  history: { role: string; content: string; sql?: string }[];
}

export interface ContextKPI {
  label: string;
  value: string | number | null;
  sql: string;
}

export interface ChatResponse {
  explanation: string;
  sql: string;
  results: Record<string, unknown>[];
  columns: string[];
  row_count: number;
  viz: "number" | "table" | "bar" | "line" | "funnel";
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
