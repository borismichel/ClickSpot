export type VizType = "number" | "table" | "bar" | "line" | "funnel" | "comparison";

export interface SavedObject {
  id: string;
  title: string;
  sql: string;
  viz: VizType;
  contextKPIs: { label: string; sql: string; previous_sql?: string }[];
  savedAt: string;
}

export interface DashboardItem {
  objectId: string;
  layout: { x: number; y: number; w: number; h: number };
}

export interface DashboardFilters {
  dateFrom: string | null;
  dateTo: string | null;
  ownerIds: string[];
  ownerNames: string[];
  pipelineIds: string[];
  pipelineLabels: string[];
}

export const EMPTY_FILTERS: DashboardFilters = {
  dateFrom: null,
  dateTo: null,
  ownerIds: [],
  ownerNames: [],
  pipelineIds: [],
  pipelineLabels: [],
};

export interface Dashboard {
  id: string;
  title: string;
  items: DashboardItem[];
  filters: DashboardFilters;
  createdAt: string;
  updatedAt: string;
}

// ---------------------------------------------------------------------------
// Space dashboard types
// ---------------------------------------------------------------------------

export interface SpaceColumnMeta {
  name: string;
  type: string;
  display: string;
}

export interface SpaceFilter {
  column: string;
  operator: "eq" | "neq" | "in" | "gt" | "gte" | "lt" | "lte" | "between" | "like";
  values: string[];
}

export interface SpaceDashboardItem {
  id: string;
  title: string;
  /** The one-sentence business question this widget answers (OSD provenance, A5). */
  intent?: string;
  sql: string;
  viz: VizType;
  contextKPIs: { label: string; sql: string; previous_sql?: string }[];
  layout: { x: number; y: number; w: number; h: number };
}

export interface SpaceDashboard {
  id: string;
  space_id: string;
  title: string;
  /** The original prompt that generated this dashboard (OSD provenance, A5). */
  source_description?: string;
  items: SpaceDashboardItem[];
  filters: SpaceFilter[];
  pinned_columns: string[];
  created_at: string;
  updated_at: string;
  space_name?: string;  // populated by /dashboards/all endpoint
}

// ---------------------------------------------------------------------------
// Unified dashboard — wraps either a library or space dashboard
// ---------------------------------------------------------------------------

export type UnifiedDashboard =
  | { kind: "library"; data: Dashboard }
  | { kind: "space"; data: SpaceDashboard };
