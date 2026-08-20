export interface FieldMeta {
  type: string;
  display: string;
}

export interface TableSchema {
  primary_key: string;
  display_name: string;
  fields: Record<string, FieldMeta>;
}

export interface GraphEdge {
  from: string;
  to: string;
  bridge: string;
  from_key: string;
  to_key: string;
}

export interface ReferenceJoin {
  from: string;
  to: string;
  from_col: string;
  to_col: string;
}

export interface SchemaResponse {
  tables: Record<string, TableSchema>;
  edges: GraphEdge[];
  reference_joins: ReferenceJoin[];
}

export interface FieldValueItem {
  value: string;
  count: number;
}

export interface FieldValuesResponse {
  possible: FieldValueItem[];
  excluded: FieldValueItem[];
}

export interface MeasureRequest {
  table: string;
  column: string;
  agg: string;
}

export interface ListRequest {
  columns: string[];
  limit?: number;
  offset?: number;
}

export interface ListResponse {
  rows: Record<string, unknown>[];
  total: number;
}

export interface QueryRequest {
  selections: Record<string, string[]>;
  counts?: boolean;
  field_values?: string[];
  measures?: MeasureRequest[];
  lists?: Record<string, ListRequest>;
}

export interface GroupedMeasureRow {
  groups: Record<string, string>;
  value: number | null;
}

export interface TimeSeriesPoint {
  period: string;
  value: number | null;
}

export interface QueryResponse {
  reachable_counts: Record<string, number>;
  field_values: Record<string, FieldValuesResponse>;
  measures: Record<string, number | null>;
  grouped_measures: Record<string, GroupedMeasureRow[]>;
  time_series: Record<string, TimeSeriesPoint[]>;
  computed_metrics: Record<string, number | null>;
  lists: Record<string, ListResponse>;
}

export interface MetadataResponse {
  row_counts: Record<string, number>;
  silver_loaded_at: Record<string, string>;
}

// --- Sync / apply surface (Settings → Data sync + pending-changes banner) ---

export interface SyncStage {
  stage: string;
  label: string;
  status: "pending" | "running" | "success" | "failure";
  run_id: string | null;
  run_url: string | null;
}

export interface SyncErrorInfo {
  stage: string;
  stage_label: string;
  message: string;
  failed_step: string | null;
  run_id: string;
  run_url: string;
}

export interface SyncInfo {
  sync_id: string;
  /** "sync" fetches from HubSpot (4 stages); "apply" rebuilds from stored data (3). */
  kind: "sync" | "apply";
  state: "running" | "succeeded" | "failed";
  stages: SyncStage[];
  error: SyncErrorInfo | null;
}

export interface ScheduleInfo {
  enabled: boolean;
  /** Epoch seconds of the next tick; null while the schedule is off. */
  next_run_timestamp: number | null;
}

export interface SyncStatusResponse {
  hubspot_configured: boolean;
  not_configured_reason: string | null;
  dagster_ui_url: string;
  dagster_error: string | null;
  sync_running: boolean;
  /** A settings save is waiting for "Apply changes" to make it live. */
  pending_apply: boolean;
  sync: SyncInfo | null;
  /** null when the orchestrator can't say — the switch greys out. */
  schedule: ScheduleInfo | null;
}
