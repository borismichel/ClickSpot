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
